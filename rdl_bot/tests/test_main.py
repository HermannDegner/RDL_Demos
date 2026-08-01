"""応答ループ・leapフロー・代謝（main.py）"""

import os
import tempfile
import unittest
from unittest import mock

import main
from h_state import HState
from llm_bridge import LLMBridge
from llm_trust import LLMTrust
from node_graph import Node, NodeGraph
from sfo_profile import AI_SFO


class RespondTestCase(unittest.TestCase):
    """LLMを持たない（APIキー無し）状態での応答経路を検証する。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = os.path.join(self.tmpdir.name, "graph.json")

        env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
        env.start()
        self.addCleanup(env.stop)

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

    def respond(self, text, graph, h):
        return main.respond(text, graph, h, self.llm, self.sfo, self.xi, self.trust)


class StubLLM(LLMBridge):
    """
    LLM:on を模したスタブ。API を呼ばずに、修正・学習の呼び出し内容を記録する。
    """

    def __init__(self, sfo):
        super().__init__(sfo)
        self.mode = "on"
        self.revision_calls = []   # (hot_node, user_input)
        self.learned_inputs = []
        self.node_failure = False

    def available(self):
        return True

    def ask_for_node_revision(self, hot_node, user_input=None):
        self.revision_calls.append((hot_node, user_input))
        return Node(inputs=list(hot_node.inputs), rdl_type="修正",
                    response=f"[{hot_node.inputs[0]}の修正版]", source="llm_learned")

    def ask_for_node(self, user_input):
        self.learned_inputs.append(user_input)
        if self.node_failure:
            return None
        return Node(inputs=[user_input], rdl_type="新規",
                    response=f"[{user_input}を学習]", source="llm_learned")

    def ask(self, user_input, context=""):
        return f"[生応答: {user_input}]"


class LeapCausalityTestCase(RespondTestCase):
    """LLM:on を模したスタブで leap の因果を検証する。"""

    def setUp(self):
        super().setUp()
        self.llm = StubLLM(self.sfo)


class TestLeapScopeSeparation(LeapCausalityTestCase):
    def test_background_correction_is_not_returned_as_the_answer(self):
        """
        回帰テスト: 今回の入力と無関係なノードが熱いだけで、その修正版が
        今回の応答として返っていた（Hの発生位置と作用Fの適用先の分離漏れ）。
        """
        greet = Node(inputs=["こんにちは"], response="やあ", spatial_tag="人")
        g = self.graph(greet)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(greet.id)

        resp, _ = self.respond("量子もつれについて考えたい", g, h)

        self.assertNotIn("こんにちは", resp)
        self.assertEqual(greet.status, "deprecated")  # 裏での修正自体は行われる

    def test_background_correction_does_not_see_the_current_input(self):
        """
        回帰テスト: 背景ノードの修正プロンプトに今回の無関係な入力が
        混入し、修正内容そのものが汚染されていた。
        """
        greet = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(greet)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(greet.id)

        self.respond("量子もつれについて考えたい", g, h)

        self.assertEqual(len(self.llm.revision_calls), 1)
        _, passed_input = self.llm.revision_calls[0]
        self.assertIsNone(passed_input)

    def test_current_node_correction_is_returned_with_the_input(self):
        """今回一致したノード自身が熱い場合は、修正版を応答に使い現在入力も渡す。"""
        greet = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(greet)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(greet.id)

        resp, _ = self.respond("こんにちは", g, h)

        self.assertIn("修正版", resp)
        _, passed_input = self.llm.revision_calls[0]
        self.assertEqual(passed_input, "こんにちは")

    def test_scope_is_classified_correctly(self):
        greet = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(greet)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(greet.id)

        current = main._decide_leap(h, g, "exact", greet, "こんにちは")
        self.assertEqual(current.scope, "current")
        self.assertEqual(current.cause, "deny")
        self.assertEqual(current.trigger_input, "こんにちは")

        background = main._decide_leap(h, g, "miss", None, "無関係")
        self.assertEqual(background.scope, "background")
        self.assertIsNone(background.trigger_input)

    def test_phantom_and_unresolved_are_distinguished(self):
        g = self.graph()
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny("__llm__")
        self.assertEqual(main._decide_leap(h, g, "miss", None, "x").scope, "phantom")

        h2 = HState(theta=2.0)
        for _ in range(11):
            h2.on_miss(None)          # 最近傍が無い未知入力
        self.assertEqual(main._decide_leap(h2, g, "miss", None, "x").scope, "unresolved")

    def test_no_leap_returns_none(self):
        g = self.graph(Node(inputs=["こんにちは"], response="やあ"))
        self.assertIsNone(main._decide_leap(HState(theta=2.0), g, "miss", None, "x"))


class TestUnresolvedMissLeap(LeapCausalityTestCase):
    def test_accumulated_misses_trigger_learning(self):
        g = self.graph()
        h = HState(theta=2.0)
        for _ in range(11):
            h.on_miss(None)

        resp, _ = self.respond("まったく新しい話題", g, h)

        self.assertIn("まったく新しい話題", resp)
        self.assertIn("まったく新しい話題", self.llm.learned_inputs)

    def test_unresolved_h_is_decayed_even_when_learning_fails(self):
        """
        回帰テスト: 消化されなかった蓄積が毎ターン should_leap() の最大値を
        占め続けると、実ノードのleapが永久に起きなくなる（疑似IDと同じ停止）。
        """
        self.llm.node_failure = True
        g = self.graph()
        h = HState(theta=2.0)
        for _ in range(11):
            h.on_miss(None)
        before = h.H_pre[HState.PENDING_MISS_ID]

        self.respond("まったく新しい話題", g, h)

        self.assertLess(h.H_pre[HState.PENDING_MISS_ID], before)

    def test_unresolved_h_is_decayed_when_this_turn_matched(self):
        greet = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(greet)
        h = HState(theta=2.0)
        for _ in range(11):
            h.on_miss(None)
        before = h.H_pre[HState.PENDING_MISS_ID]

        self.respond("こんにちは", g, h)

        self.assertLess(h.H_pre[HState.PENDING_MISS_ID], before)


class TestRespondRouting(RespondTestCase):
    def test_exact_match_returns_node_response(self):
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        resp, nid = self.respond("こんにちは", g, HState())
        self.assertEqual(resp, "やあ")
        self.assertEqual(nid, n.id)

    def test_exact_match_records_usage(self):
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        self.respond("こんにちは", g, HState())
        self.assertEqual(n.usage_count, 1)

    def test_unknown_input_falls_back(self):
        g = self.graph(Node(inputs=["こんにちは"], response="やあ"))
        resp, nid = self.respond("まったく無関係な話題", g, HState())
        self.assertEqual(nid, "__none__")
        self.assertIn("未知の入力", resp)

    def test_quarantined_node_is_not_reused(self):
        n = Node(inputs=["だめな応答"], response="否定された内容")
        n.status = "quarantined"
        g = self.graph(n)
        resp, _ = self.respond("だめな応答", g, HState())
        self.assertNotIn("否定された内容", resp)


class TestPhantomHotNode(RespondTestCase):
    def test_phantom_id_does_not_freeze_learning(self):
        """
        回帰テスト: LLM生応答("__llm__")のような実ノードに対応しないIDへ
        Hが溜まると、修正対象が存在せずleapで消化できないまま
        should_leap() の最大値を占め続け、実在ノードのleapが永久に
        起きなくなっていた（＝学習の停止）。
        """
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny("__llm__")
        self.assertEqual(h.should_leap()[1], "__llm__")

        resp, nid = self.respond("こんにちは", g, h)

        self.assertEqual(nid, n.id)
        self.assertNotIn("__llm__", h.H_post)
        self.assertNotEqual(h.should_leap()[1], "__llm__")

    def test_retired_node_id_does_not_freeze_learning(self):
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny("退場済みノードのID")

        self.respond("こんにちは", g, h)
        self.assertNotIn("退場済みノードのID", h.H_post)

    def test_real_hot_node_is_still_quarantined_with_llm_off(self):
        """疑似IDの破棄が、実ノードに対する通常のleapを壊していないこと。"""
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(n.id)

        self.respond("こんにちは", g, h)
        self.assertEqual(n.status, "quarantined")


class TestComposeFromGraph(RespondTestCase):
    def test_borrows_nearest_response(self):
        g = self.graph(Node(inputs=["疲れた"], response="休もう", confidence=0.9))
        resp, nid = main.compose_from_graph("疲れた", g)
        self.assertIn("休もう", resp)
        self.assertIn("近傍合成", resp)

    def test_skips_quarantined_nodes(self):
        """
        回帰テスト: 否定されて隔離した応答を近傍合成で借用し直していた。
        """
        n = Node(inputs=["疲れた"], response="否定された内容", confidence=0.9)
        n.status = "quarantined"
        g = self.graph(n)
        resp, nid = main.compose_from_graph("疲れた", g)
        self.assertNotIn("否定された内容", resp)
        self.assertEqual(nid, "__none__")

    def test_empty_graph_returns_unknown(self):
        resp, nid = main.compose_from_graph("何か", self.graph())
        self.assertEqual(nid, "__none__")


class TestFeedback(RespondTestCase):
    def test_deny_lowers_confidence_and_records_counterexample(self):
        n = Node(inputs=["x"], response="r", confidence=1.0)
        g = self.graph(n)
        h = HState()
        main.apply_feedback("n", n.id, "だめだった", g, h)
        self.assertLess(n.confidence, 1.0)
        self.assertEqual(n.counterexamples[-1]["reason"], "deny")
        self.assertEqual(h.H_post[n.id], 1.0)

    def test_agree_raises_confidence_and_approval(self):
        n = Node(inputs=["x"], response="r", confidence=0.5)
        g = self.graph(n)
        h = HState()
        main.apply_feedback("y", n.id, "よかった", g, h)
        self.assertGreater(n.confidence, 0.5)
        self.assertEqual(n.approval_count, 1)

    def test_confidence_never_reaches_zero(self):
        n = Node(inputs=["x"], response="r", confidence=1.0)
        g = self.graph(n)
        h = HState()
        for _ in range(200):
            main.apply_feedback("n", n.id, "だめ", g, h)
        self.assertGreaterEqual(n.confidence, 0.05)

    def test_confidence_is_capped_at_one(self):
        n = Node(inputs=["x"], response="r", confidence=0.99)
        g = self.graph(n)
        h = HState()
        for _ in range(50):
            main.apply_feedback("y", n.id, "よい", g, h)
        self.assertLessEqual(n.confidence, 1.0)

    def test_unknown_node_id_is_harmless(self):
        g = self.graph()
        h = HState()
        main.apply_feedback("n", "__llm__", "だめ", g, h)  # 例外を出さないこと
        self.assertEqual(h.H_post["__llm__"], 1.0)

    def test_blank_feedback_does_nothing(self):
        n = Node(inputs=["x"], response="r", confidence=1.0)
        g = self.graph(n)
        h = HState()
        main.apply_feedback("", n.id, "x", g, h)
        self.assertEqual(n.confidence, 1.0)
        self.assertEqual(h.H_post, {})


class TestMetabolize(RespondTestCase):
    def test_prunes_h_of_retired_nodes(self):
        dead = Node(inputs=["dead"], ttl=0, confidence=0.05)
        alive = Node(inputs=["alive"], ttl=50, confidence=0.9)
        g = self.graph(dead, alive)
        h = HState()
        h.on_deny(dead.id)
        h.on_deny(alive.id)

        main.metabolize(g, self.sfo, self.xi, h, retire=True)

        self.assertNotIn(dead.id, g.nodes)
        self.assertNotIn(dead.id, h.H_post)
        self.assertIn(alive.id, h.H_post)

    def test_relaxes_theta_toward_base(self):
        g = self.graph()
        h = HState(theta=2.0)
        for _ in range(50):
            h.leap_done("A")
        raised = h.theta
        main.metabolize(g, self.sfo, self.xi, h, retire=True)
        self.assertLess(h.theta, raised)
        self.assertGreaterEqual(h.theta, h.theta_base)

    def test_unused_llm_seed_is_marked_for_retirement(self):
        seed = Node(inputs=["s"], source="llm_seed", confidence=0.2)
        g = self.graph(seed)
        main.metabolize(g, self.sfo, self.xi, h_state=HState(), retire=False)
        self.assertEqual(seed.ttl, 0)

    def test_used_llm_seed_survives(self):
        seed = Node(inputs=["s"], source="llm_seed", confidence=0.2)
        seed.increment_usage()
        g = self.graph(seed)
        main.metabolize(g, self.sfo, self.xi, h_state=HState(), retire=True)
        self.assertIn(seed.id, g.nodes)

    def test_xi_pool_entries_become_nodes_when_matchable(self):
        g = self.graph(Node(inputs=["疲れた"], response="休もう", spatial_tag="身体"))
        xi = ["疲れた"]
        main.metabolize(g, self.sfo, xi, HState(), retire=True)
        self.assertEqual(xi, [])
        self.assertTrue(any(n.source == "graph_composed" for n in g.nodes.values()))

    def test_unmatchable_xi_entries_stay_pooled(self):
        g = self.graph(Node(inputs=["疲れた"], response="休もう"))
        xi = ["まったく無関係な話題"]
        main.metabolize(g, self.sfo, xi, HState(), retire=True)
        self.assertEqual(xi, ["まったく無関係な話題"])


class TestSeedLoading(RespondTestCase):
    def test_seed_is_loaded_as_a_scaffold_not_internal_knowledge(self):
        """
        回帰テスト: 同梱seedを source="manual" / confidence=0.9 で入れていたため、
        内部経験の重みが最大(0.8)になり、起動しただけで外部LLMをほとんど
        信用しないAIになっていた（設計書 §3.7 はseedを仮置きの足場と定める）。
        """
        g = self.graph()
        n = main.load_seed_json(g, "data/seed_v0.1.json")
        self.assertGreater(n, 0)
        for node in g.nodes.values():
            self.assertEqual(node.source, "bootstrap_seed")
            self.assertAlmostEqual(node.confidence, 0.5)

    def test_startup_still_trusts_the_external_llm(self):
        """幼少期（起動直後）は外部LLMを足場として使える信用度であること。"""
        g = self.graph()
        main.load_seed_json(g, "data/seed_v0.1.json")
        for tag in main.DOMAIN_TAGS:
            with self.subTest(domain=tag):
                self.assertGreater(self.trust.trust_for(g, tag), 0.4)

    def test_trust_falls_once_the_user_actually_validates_the_domain(self):
        g = self.graph()
        main.load_seed_json(g, "data/seed_v0.1.json")
        before = self.trust.trust_for(g, "人")
        for node in g.nodes.values():
            if node.spatial_tag == "人":
                node.approval_count = 5
                node.usage_count = 3
        self.assertLess(self.trust.trust_for(g, "人"), before / 2)

    def test_unused_bootstrap_seed_is_retired(self):
        g = self.graph()
        main.load_seed_json(g, "data/seed_v0.1.json")
        for node in g.nodes.values():
            node.confidence = 0.2
        main.metabolize(g, self.sfo, self.xi, HState(), retire=False)
        self.assertTrue(all(n.ttl == 0 for n in g.nodes.values()))

    def test_missing_seed_file_is_harmless(self):
        g = self.graph()
        self.assertEqual(main.load_seed_json(g, "data/nope.json"), 0)


class TestSessionState(RespondTestCase):
    def test_round_trip(self):
        path = os.path.join(self.tmpdir.name, "session.json")
        h = HState(theta=2.0)
        h.on_deny("A")
        self.sfo.drift_factor = 0.3

        main.save_session_state(path, h, self.sfo, ["未処理のξ"], "on", 42)
        state = main.load_session_state(path)

        self.assertEqual(state["turn_count"], 42)
        self.assertEqual(state["xi_pool"], ["未処理のξ"])
        self.assertEqual(state["llm_mode"], "on")
        restored = HState.from_dict(state["h_state"])
        self.assertEqual(restored.H_post, h.H_post)
        self.assertEqual(AI_SFO.from_dict(state["sfo_profile"]).drift_factor, 0.3)

    def test_missing_file_returns_none(self):
        self.assertIsNone(
            main.load_session_state(os.path.join(self.tmpdir.name, "nope.json"))
        )

    def test_corrupt_file_returns_none_instead_of_raising(self):
        path = os.path.join(self.tmpdir.name, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{壊れた")
        self.assertIsNone(main.load_session_state(path))

    def test_creates_missing_directory(self):
        path = os.path.join(self.tmpdir.name, "deep", "session.json")
        main.save_session_state(path, HState(), self.sfo, [], "off", 0)
        self.assertTrue(os.path.exists(path))


class TestTrustConfigLoading(RespondTestCase):
    def test_missing_config_uses_defaults(self):
        cfg = main.load_llm_trust_config(os.path.join(self.tmpdir.name, "nope.json"))
        self.assertEqual(cfg.trust_decay_scale, 0.9)

    def test_corrupt_config_falls_back_to_defaults(self):
        path = os.path.join(self.tmpdir.name, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{壊れた")
        self.assertEqual(main.load_llm_trust_config(path).trust_decay_scale, 0.9)

    def test_config_file_overrides_defaults(self):
        path = os.path.join(self.tmpdir.name, "trust.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"trust_decay_scale": 0.4, "usage_weight": 0.5}')
        cfg = main.load_llm_trust_config(path)
        self.assertEqual(cfg.trust_decay_scale, 0.4)
        self.assertEqual(cfg.usage_weight, 0.5)


class TestInferDomain(RespondTestCase):
    def test_uses_weighted_vote_not_single_nearest(self):
        g = self.graph(
            Node(inputs=["今日は疲れた"], spatial_tag="身体"),
            Node(inputs=["今日は疲れたね"], spatial_tag="身体"),
            Node(inputs=["今日は疲"], spatial_tag="制度"),
        )
        self.assertEqual(main._infer_domain(g, "今日は疲れた", None), "身体")

    def test_empty_graph_defaults_to_concept(self):
        self.assertEqual(main._infer_domain(self.graph(), "何か", None), "概念")


if __name__ == "__main__":
    unittest.main()
