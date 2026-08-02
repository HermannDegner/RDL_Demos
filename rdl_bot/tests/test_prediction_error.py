"""
E = F(t+Δ) − M_B·F(t) の導入（Core §2.3）

Living Field（demos/relational-ecology-lab）の decision パターンを移したもの。
応答時に予測を書き留め、ユーザー反応で実測と突き合わせて差を取る。
"""

import os
import tempfile
import unittest
from unittest import mock

import dynamics
import main
from dynamics import DynamicsConfig
from h_state import HState
from llm_bridge import LLMBridge
from llm_trust import LLMTrust
from node_graph import Node, NodeGraph
from sfo_profile import AI_SFO


class ErrorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = os.path.join(self.tmpdir.name, "graph.json")

        env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
        env.start()
        self.addCleanup(env.stop)

        original = dynamics.CONFIG
        self.addCleanup(lambda: dynamics.configure(original))
        dynamics.configure(DynamicsConfig())

        self.sfo = AI_SFO()
        self.llm = LLMBridge(self.sfo)
        self.llm.set_mode("off")
        self.trust = LLMTrust()
        self.xi = []

    def graph(self, *nodes) -> NodeGraph:
        g = NodeGraph(self.path)
        for n in nodes:
            g.add(n)
        return g


class TestAcceptanceError(ErrorTestCase):
    """「この応答は受け入れられる」という予測と、実際の反応との差。"""

    def test_denying_a_confident_node_is_a_large_error(self):
        """
        回帰テスト: 以前は否定が常に +1.0 の定数だったため、確信していた
        応答を否定されても、自信の無い応答を否定されても同じ扱いだった。
        設計書 §1.5 が「誤差の大きさが問題になる場面で破断する」と
        宣言していた箇所。
        """
        confident = Node(inputs=["x"], response="r", confidence=0.9)
        g = self.graph(confident)
        h = HState()
        h.open_decision(confident.id, confident.confidence)
        main.apply_feedback("n", confident.id, "だめ", g, h)
        big = h.H_post[confident.id]

        unsure = Node(inputs=["y"], response="r", confidence=0.1)
        g2 = self.graph(unsure)
        h2 = HState()
        h2.open_decision(unsure.id, unsure.confidence)
        main.apply_feedback("n", unsure.id, "だめ", g2, h2)
        small = h2.H_post[unsure.id]

        self.assertGreater(big, small * 3)

    def test_agreeing_with_an_unsure_node_also_carries_information(self):
        """
        「通らないと思っていた応答が通った」も M_B の誤りなので H を積む。
        否定だけが学習を駆動する非対称を解消する。
        """
        unsure = Node(inputs=["x"], response="r", confidence=0.05)
        g = self.graph(unsure)
        h = HState()
        h.open_decision(unsure.id, unsure.confidence)
        main.apply_feedback("y", unsure.id, "よい", g, h)
        self.assertGreater(h.H_post.get(unsure.id, 0.0), 0.0)

    def test_agreeing_with_a_confident_node_barely_moves_h(self):
        """予測が当たった場合は驚きが無いので、ほとんど積まない。"""
        confident = Node(inputs=["x"], response="r", confidence=0.95)
        g = self.graph(confident)
        h = HState()
        h.open_decision(confident.id, confident.confidence)
        main.apply_feedback("y", confident.id, "よい", g, h)
        self.assertLess(h.H_post.get(confident.id, 0.0), 0.1)

    def test_falls_back_to_constants_without_an_open_decision(self):
        """決定が開いていない呼び出し（テストや復元直後）でも壊れないこと。"""
        n = Node(inputs=["x"], response="r", confidence=0.9)
        g = self.graph(n)
        h = HState()
        main.apply_feedback("n", n.id, "だめ", g, h)
        self.assertEqual(h.H_post[n.id], 1.0)

    def test_decision_is_consumed_once(self):
        h = HState()
        h.open_decision("A", 0.5)
        self.assertIsNotNone(h.close_decision(0.0))
        self.assertIsNone(h.close_decision(0.0))

    def test_response_without_a_node_uses_the_fallback_prediction(self):
        dynamics.configure(DynamicsConfig(fallback_predicted_acceptance=0.3))
        g = self.graph()
        self.assertEqual(main._predicted_acceptance(g, "__none__"), 0.3)

    def test_prediction_comes_from_node_confidence(self):
        n = Node(inputs=["x"], confidence=0.77)
        g = self.graph(n)
        self.assertAlmostEqual(main._predicted_acceptance(g, n.id), 0.77)


class TestMatchError(ErrorTestCase):
    """「次に来る入力を捉えられる」という予測と、実際の一致との差。"""

    def test_a_miss_after_a_run_of_hits_is_surprising(self):
        h = HState()
        for _ in range(40):
            h.observe_match(1.0)          # 当たり続けて予測が上がる
        surprising = h.observe_match(0.0)

        h2 = HState()
        for _ in range(40):
            h2.observe_match(0.0)         # 外し続けて予測が下がる
        expected = h2.observe_match(0.0)

        self.assertGreater(surprising, expected * 3)

    def test_prediction_tracks_observation(self):
        h = HState()
        before = h.predict_match()
        for _ in range(30):
            h.observe_match(1.0)
        self.assertGreater(h.predict_match(), before)

    def test_error_is_bounded(self):
        h = HState()
        for observed in (0.0, 1.0, 0.5, 1.0, 0.0):
            self.assertGreaterEqual(h.observe_match(observed), 0.0)
            self.assertLessEqual(h.last_error["match"], 1.0)

    def test_respond_feeds_the_match_error_into_h(self):
        """miss の H_pre が定数ではなく E 由来になっていること。"""
        g = self.graph(Node(inputs=["こんにちは"], response="やあ"))
        h = HState()
        for _ in range(40):
            h.observe_match(1.0)          # 「捉えられる」と強く予測した状態

        main.respond("まったく無関係な話題", g, h, self.llm, self.sfo, self.xi, self.trust)

        # 予測 1.0 に対し実測 0.0 なので E≈1.0、gain 0.8 で約 0.8 積まれる。
        # 従来の定数 0.5 より大きい＝驚きが反映されている。
        self.assertGreater(h.H_pre[HState.PENDING_MISS_ID], 0.5)


class TestReliability(ErrorTestCase):
    def test_reliability_rises_when_predictions_hold(self):
        h = HState()
        before = h.reliability["match"]
        for _ in range(100):
            h.observe_match(h.predict_match())   # 完全に当て続ける
        self.assertGreater(h.reliability["match"], before)

    def test_reliability_falls_when_predictions_fail(self):
        h = HState()
        before = h.reliability["match"]
        for _ in range(60):
            h.observe_match(1.0 if h.predict_match() < 0.5 else 0.0)  # 常に裏切る
        self.assertLess(h.reliability["match"], before)

    def test_reliability_stays_in_range(self):
        h = HState()
        for i in range(300):
            h.observe_match(float(i % 2))
            self.assertGreaterEqual(h.reliability["match"], 0.18)
            self.assertLessEqual(h.reliability["match"], 0.98)

    def test_summary_reports_error_and_reliability(self):
        text = HState().summary(0.0)
        self.assertIn("E:", text)
        self.assertIn("予測信頼度", text)


class TestConfig(ErrorTestCase):
    def test_gain_scales_the_injected_heat(self):
        def heat(gain):
            dynamics.configure(DynamicsConfig(e_gain_acceptance=gain))
            n = Node(inputs=["x"], response="r", confidence=1.0)
            g = self.graph(n)
            h = HState()
            h.open_decision(n.id, 1.0)
            main.apply_feedback("n", n.id, "だめ", g, h)
            return h.H_post[n.id]

        self.assertAlmostEqual(heat(2.0), heat(1.0) * 2)

    def test_observed_values_are_configurable(self):
        dynamics.configure(DynamicsConfig(observed_deny=0.5))
        h = HState()
        h.open_decision("A", 0.5)
        self.assertAlmostEqual(h.close_decision(0.5), 0.0)


if __name__ == "__main__":
    unittest.main()
