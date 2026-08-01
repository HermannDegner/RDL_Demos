"""ノード検索・ライフサイクル・永続化（node_graph.py）"""

import json
import os
import tempfile
import unittest

from node_graph import ALIGNMENT_CEILING, Node, NodeGraph, _char_ngrams, _ngram_similarity


class GraphTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = os.path.join(self.tmpdir.name, "graph.json")

    def graph(self, *nodes) -> NodeGraph:
        g = NodeGraph(self.path)
        for n in nodes:
            g.add(n)
        return g


class TestSimilarity(unittest.TestCase):
    def test_japanese_text_has_nonzero_similarity(self):
        """分かち書きされない日本語でも近傍比較できること（空白splitでは0になる）。"""
        a = _char_ngrams("今日は疲れた")
        b = _char_ngrams("今日はとても疲れた")
        self.assertGreater(_ngram_similarity(a, b), 0.0)

    def test_identical_text_is_one(self):
        a = _char_ngrams("こんにちは")
        self.assertEqual(_ngram_similarity(a, a), 1.0)

    def test_disjoint_text_is_zero(self):
        self.assertEqual(
            _ngram_similarity(_char_ngrams("あいうえ"), _char_ngrams("かきくけ")), 0.0
        )

    def test_empty_inputs(self):
        self.assertEqual(_char_ngrams(""), set())
        self.assertEqual(_ngram_similarity(set(), set()), 0.0)

    def test_single_char_shorter_than_n(self):
        self.assertEqual(_char_ngrams("あ"), {"あ"})


class TestSearch(GraphTestCase):
    def test_exact_match(self):
        n = Node(inputs=["こんにちは"], response="やあ")
        g = self.graph(n)
        node, kind, _ = g.search("こんにちは")
        self.assertEqual(kind, "exact")
        self.assertEqual(node.id, n.id)

    def test_partial_match(self):
        n = Node(inputs=["疲れた"], response="休もう")
        g = self.graph(n)
        node, kind, _ = g.search("今日はとても疲れた")
        self.assertEqual(kind, "partial")
        self.assertEqual(node.id, n.id)

    def test_miss_returns_nearest(self):
        n = Node(inputs=["今日は疲れた"])
        g = self.graph(n)
        node, kind, nearest = g.search("今日は眠い")
        self.assertEqual(kind, "miss")
        self.assertIsNone(node)
        self.assertEqual(nearest.id, n.id)

    def test_miss_on_empty_graph_has_no_nearest(self):
        g = self.graph()
        node, kind, nearest = g.search("何か")
        self.assertEqual(kind, "miss")
        self.assertIsNone(nearest)

    def test_unrelated_input_has_no_nearest(self):
        """
        回帰テスト: max_similarity を -1.0 から始めていたため、どのパターンとも
        文字が重ならない入力でも「最初に走査されたノード」が最近傍になり、
        無関係なノードに miss の H_pre が積み上がっていた。
        """
        g = self.graph(Node(inputs=["ABCDEF"]), Node(inputs=["GHIJKL"]))
        node, kind, nearest = g.search("ぬめり")
        self.assertEqual(kind, "miss")
        self.assertIsNone(nearest)

    def test_slightly_similar_input_still_has_nearest(self):
        n = Node(inputs=["今日は疲れた"])
        g = self.graph(n)
        _, kind, nearest = g.search("今日は眠い")
        self.assertEqual(kind, "miss")
        self.assertEqual(nearest.id, n.id)

    def test_partial_score_prefers_closer_length(self):
        """
        回帰テスト: 以前のスコアは len(pattern)/len(text) だったため、
        登録パターンが長いほど過剰に高得点になる逆転があった。
        """
        close = Node(inputs=["疲れたので休みたい"], response="近い")
        far = Node(inputs=["疲"], response="遠い")
        g = self.graph(close, far)
        node, kind, _ = g.search("疲れたので休みたいです")
        self.assertEqual(kind, "partial")
        self.assertEqual(node.id, close.id)

    def test_exact_prefers_higher_confidence(self):
        low = Node(inputs=["やあ"], response="低", confidence=0.2)
        high = Node(inputs=["やあ"], response="高", confidence=0.9)
        g = self.graph(low, high)
        node, kind, _ = g.search("やあ")
        self.assertEqual(node.response, "高")

    def test_user_node_wins_over_llm_seed(self):
        seed = Node(inputs=["ありがとう"], response="seed", source="llm_seed", confidence=0.5)
        learned = Node(inputs=["ありがとう"], response="learned", source="llm_learned", confidence=0.9)
        g = self.graph(seed, learned)
        node, kind, _ = g.search("ありがとう")
        self.assertEqual(node.response, "learned")

    def test_user_node_wins_over_bootstrap_seed(self):
        """同梱seedもユーザー由来ノードに置換される（設計書 §3.7）。"""
        seed = Node(inputs=["ありがとう"], response="seed", source="bootstrap_seed", confidence=0.5)
        learned = Node(inputs=["ありがとう"], response="learned", source="llm_learned", confidence=0.9)
        g = self.graph(seed, learned)
        node, _, _ = g.search("ありがとう")
        self.assertEqual(node.response, "learned")


class TestStatusResolution(GraphTestCase):
    def test_quarantined_node_does_not_shadow_an_active_one(self):
        """
        回帰テスト: 候補を最良1件だけ確定させていたため、同じ入力を持つ
        高confidenceの quarantined ノードが、低confidenceでも active な
        ノードを覆い隠して miss になっていた。
        """
        blocked = Node(inputs=["ありがとう"], response="隔離された応答", confidence=0.9)
        blocked.status = "quarantined"
        usable = Node(inputs=["ありがとう"], response="正常な応答", confidence=0.8)
        g = self.graph(blocked, usable)
        node, kind, _ = g.search("ありがとう")
        self.assertEqual(kind, "exact")
        self.assertEqual(node.id, usable.id)

    def test_quarantined_does_not_shadow_on_partial_match(self):
        blocked = Node(inputs=["疲れた"], response="隔離", confidence=0.9)
        blocked.status = "quarantined"
        usable = Node(inputs=["疲れた"], response="正常", confidence=0.8)
        g = self.graph(blocked, usable)
        node, kind, _ = g.search("今日はとても疲れた")
        self.assertEqual(kind, "partial")
        self.assertEqual(node.id, usable.id)

    def test_deprecated_shadowing_redirects_instead_of_missing(self):
        successor = Node(inputs=["新"], response="後継")
        old = Node(inputs=["ありがとう"], response="旧", confidence=0.9)
        old.status = "deprecated"
        old.relations.append(successor.id)
        other = Node(inputs=["ありがとう"], response="別の正常ノード", confidence=0.5)
        g = self.graph(old, successor, other)
        node, kind, _ = g.search("ありがとう")
        self.assertEqual(kind, "exact")
        self.assertEqual(node.id, successor.id)

    def test_all_candidates_unusable_is_miss(self):
        a = Node(inputs=["ありがとう"], confidence=0.9)
        b = Node(inputs=["ありがとう"], confidence=0.8)
        a.status = b.status = "quarantined"
        g = self.graph(a, b)
        _, kind, _ = g.search("ありがとう")
        self.assertEqual(kind, "miss")

    def test_quarantined_node_is_treated_as_miss(self):
        n = Node(inputs=["だめな応答"], response="否定された")
        n.status = "quarantined"
        g = self.graph(n)
        node, kind, _ = g.search("だめな応答")
        self.assertEqual(kind, "miss")
        self.assertIsNone(node)

    def test_deprecated_node_redirects_to_successor(self):
        successor = Node(inputs=["新"], response="修正版")
        old = Node(inputs=["旧い応答"], response="古い")
        old.status = "deprecated"
        old.relations.append(successor.id)
        g = self.graph(old, successor)
        node, kind, _ = g.search("旧い応答")
        self.assertEqual(kind, "exact")
        self.assertEqual(node.id, successor.id)

    def test_deprecated_without_successor_is_miss(self):
        old = Node(inputs=["旧い応答"], response="古い")
        old.status = "deprecated"
        g = self.graph(old)
        node, kind, _ = g.search("旧い応答")
        self.assertEqual(kind, "miss")

    def test_deprecated_cycle_does_not_hang(self):
        a = Node(inputs=["A"], response="a")
        b = Node(inputs=["B"], response="b")
        a.status = b.status = "deprecated"
        a.relations.append(b.id)
        b.relations.append(a.id)
        g = self.graph(a, b)
        node, kind, _ = g.search("A")
        self.assertEqual(kind, "miss")

    def test_deprecated_chain_reaches_active(self):
        active = Node(inputs=["C"], response="最終")
        mid = Node(inputs=["B"], response="中")
        first = Node(inputs=["A"], response="初")
        mid.status = first.status = "deprecated"
        first.relations.append(mid.id)
        mid.relations.append(active.id)
        g = self.graph(first, mid, active)
        node, kind, _ = g.search("A")
        self.assertEqual(node.id, active.id)


class TestTopKSimilar(GraphTestCase):
    def test_excludes_non_active_nodes(self):
        active = Node(inputs=["今日は疲れた"], spatial_tag="身体")
        quarantined = Node(inputs=["今日は疲れた"], spatial_tag="概念")
        quarantined.status = "quarantined"
        g = self.graph(active, quarantined)
        top = g.top_k_similar("今日は疲れた", k=5)
        self.assertEqual([n.id for n, _ in top], [active.id])

    def test_sorted_descending_and_limited(self):
        g = self.graph(
            Node(inputs=["今日は疲れた"]),
            Node(inputs=["今日は疲れたね"]),
            Node(inputs=["まったく別の話"]),
        )
        top = g.top_k_similar("今日は疲れた", k=2)
        self.assertEqual(len(top), 2)
        self.assertGreaterEqual(top[0][1], top[1][1])


class TestLifecycle(GraphTestCase):
    def test_promotion_to_m_act(self):
        n = Node(inputs=["x"])
        self.assertEqual(n.phase, "M_lat")
        for _ in range(3):
            n.increment_usage()
        self.assertEqual(n.phase, "M_act")

    def test_touch_refreshes_ttl(self):
        n = Node(inputs=["x"])
        for _ in range(50):
            n.decay_confidence()
        self.assertEqual(n.ttl, 50)
        n.touch()
        self.assertEqual(n.ttl, 100)

    def test_reinforce_approaches_the_ceiling_without_exceeding_it(self):
        """
        Core §6.1 の整合側 dM_B/dt。使われ続けるだけでは天井までしか
        上がらない（1.0 到達は明示的な同意でのみ）。
        """
        n = Node(inputs=["x"], confidence=0.5)
        for _ in range(500):
            n.reinforce(0.04)
        self.assertLessEqual(n.confidence, ALIGNMENT_CEILING)
        self.assertAlmostEqual(n.confidence, ALIGNMENT_CEILING, places=3)

    def test_reinforce_is_monotonic_and_small(self):
        n = Node(inputs=["x"], confidence=0.5)
        n.reinforce(0.04)
        self.assertGreater(n.confidence, 0.5)
        self.assertLess(n.confidence - 0.5, 0.05)

    def test_reinforce_does_not_pull_high_confidence_down(self):
        """承認で天井を超えたノードを、整合が引き下げないこと。"""
        n = Node(inputs=["x"], confidence=1.0)
        n.reinforce(0.04)
        self.assertEqual(n.confidence, 1.0)

    def test_zero_rate_is_a_no_op(self):
        n = Node(inputs=["x"], confidence=0.5)
        n.reinforce(0.0)
        self.assertEqual(n.confidence, 0.5)

    def test_confidence_decays_only_after_ttl_expires(self):
        n = Node(inputs=["x"], ttl=1, confidence=1.0)
        n.decay_confidence()
        self.assertEqual(n.confidence, 1.0)
        n.decay_confidence()
        self.assertAlmostEqual(n.confidence, 0.9)

    def test_counterexamples_are_capped(self):
        n = Node(inputs=["x"])
        for i in range(60):
            n.record_counterexample(f"入力{i}", "deny")
        self.assertEqual(len(n.counterexamples), 50)
        self.assertEqual(n.counterexamples[-1]["input"], "入力59")

    def test_retire_only_removes_dead_and_unconfident(self):
        dead = Node(inputs=["dead"], ttl=0, confidence=0.05)
        low_conf_alive = Node(inputs=["alive"], ttl=10, confidence=0.05)
        expired_confident = Node(inputs=["confident"], ttl=0, confidence=0.9)
        g = self.graph(dead, low_conf_alive, expired_confident)
        g.retire_dead_nodes()
        self.assertEqual(set(g.nodes), {low_conf_alive.id, expired_confident.id})


class TestPersistence(GraphTestCase):
    def test_save_and_reload_round_trip(self):
        n = Node(inputs=["こんにちは"], rdl_type="挨拶", spatial_tag="人",
                 response="やあ", source="manual", confidence=0.8)
        n.approval_count = 4
        g = self.graph(n)
        g.save()

        reloaded = NodeGraph(self.path)
        self.assertEqual(len(reloaded.nodes), 1)
        got = reloaded.get_by_id(n.id)
        self.assertEqual(got.inputs, ["こんにちは"])
        self.assertEqual(got.spatial_tag, "人")
        self.assertEqual(got.approval_count, 4)
        self.assertAlmostEqual(got.confidence, 0.8)

    def test_corrupt_file_is_backed_up_not_discarded(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{壊れたJSON")
        g = NodeGraph(self.path)
        self.assertEqual(len(g.nodes), 0)
        self.assertTrue(os.path.exists(self.path + ".corrupt"))

    def test_missing_file_starts_empty(self):
        g = NodeGraph(os.path.join(self.tmpdir.name, "nope", "graph.json"))
        self.assertEqual(len(g.nodes), 0)

    def test_save_creates_missing_directory(self):
        nested = os.path.join(self.tmpdir.name, "deep", "graph.json")
        g = NodeGraph(nested)
        g.add(Node(inputs=["x"]))
        g.save()
        with open(nested, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 1)


class TestStats(GraphTestCase):
    def test_counts_by_source_and_phase(self):
        a = Node(inputs=["a"], source="manual")
        b = Node(inputs=["b"], source="llm_seed")
        for _ in range(3):
            b.increment_usage()
        g = self.graph(a, b)
        s = g.stats()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["by_source"], {"manual": 1, "llm_seed": 1})
        self.assertEqual(s["by_phase"], {"M_lat": 1, "M_act": 1})


class TestRelations(GraphTestCase):
    def test_update_relations_is_idempotent(self):
        a = Node(inputs=["a"])
        b = Node(inputs=["b"])
        g = self.graph(a, b)
        g.update_relations(a.id, [b.id])
        g.update_relations(a.id, [b.id])
        self.assertEqual(a.relations, [b.id])


if __name__ == "__main__":
    unittest.main()
