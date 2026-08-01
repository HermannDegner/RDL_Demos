"""ドメイン別LLM信用度（llm_trust.py）"""

import os
import tempfile
import unittest

from llm_trust import LLMTrust, LLMTrustConfig
from node_graph import Node, NodeGraph


class TrustTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.trust = LLMTrust()

    def graph(self, *nodes) -> NodeGraph:
        g = NodeGraph(os.path.join(self.tmpdir.name, "graph.json"))
        for n in nodes:
            g.add(n)
        return g


class TestTrustCurve(TrustTestCase):
    def test_empty_domain_is_maximally_trusting(self):
        g = self.graph()
        self.assertEqual(self.trust.trust_for(g, "概念"), self.trust.config.max_trust)

    def test_trust_falls_as_experience_grows(self):
        g = self.graph()
        before = self.trust.trust_for(g, "概念")
        for i in range(5):
            g.add(Node(inputs=[f"p{i}"], spatial_tag="概念", source="manual"))
        after = self.trust.trust_for(g, "概念")
        self.assertLess(after, before)

    def test_trust_stays_within_bounds(self):
        g = self.graph()
        for i in range(500):
            n = Node(inputs=[f"p{i}"], spatial_tag="概念", source="manual")
            n.approval_count = 10
            g.add(n)
        t = self.trust.trust_for(g, "概念")
        self.assertGreaterEqual(t, self.trust.config.min_trust)
        self.assertLessEqual(t, self.trust.config.max_trust)

    def test_domains_mature_independently(self):
        """概念空間が成熟していても身体空間はまだ幼いままであること。"""
        g = self.graph()
        for i in range(10):
            g.add(Node(inputs=[f"p{i}"], spatial_tag="概念", source="manual"))
        self.assertLess(self.trust.trust_for(g, "概念"), self.trust.trust_for(g, "身体"))


class TestExperienceWeighting(TrustTestCase):
    def test_llm_seed_counts_less_than_manual(self):
        """
        LLMに教わっただけの知識を大量に持っても「経験豊富」と誤判定しないこと。
        """
        seeded = self.graph(*[
            Node(inputs=[f"s{i}"], spatial_tag="概念", source="llm_seed") for i in range(10)
        ])
        manual = self.graph(*[
            Node(inputs=[f"m{i}"], spatial_tag="概念", source="manual") for i in range(10)
        ])
        self.assertGreater(
            self.trust.trust_for(seeded, "概念"), self.trust.trust_for(manual, "概念")
        )

    def test_user_approval_converts_seed_into_own_experience(self):
        unapproved = self.graph(Node(inputs=["x"], spatial_tag="概念", source="llm_seed"))
        approved_node = Node(inputs=["x"], spatial_tag="概念", source="llm_seed")
        approved_node.approval_count = 10
        approved = self.graph(approved_node)
        self.assertGreater(
            self.trust.internal_experience(approved, "概念"),
            self.trust.internal_experience(unapproved, "概念"),
        )

    def test_approval_saturates_at_full_weight(self):
        cfg = LLMTrustConfig()
        node = Node(inputs=["x"], spatial_tag="概念", source="llm_seed")
        node.approval_count = int(cfg.approval_saturation)
        self.assertAlmostEqual(self.trust._node_experience_weight(node), 1.0)

    def test_quarantined_and_deprecated_are_not_experience(self):
        """否定され続けている経験は内部経験に数えない。"""
        g = self.graph()
        for status in ("quarantined", "deprecated"):
            n = Node(inputs=[status], spatial_tag="概念", source="manual")
            n.status = status
            g.add(n)
        self.assertEqual(self.trust.internal_experience(g, "概念"), 0.0)

    def test_usage_count_increases_experience(self):
        idle = self.graph(Node(inputs=["x"], spatial_tag="概念", source="manual"))
        used_node = Node(inputs=["x"], spatial_tag="概念", source="manual")
        used_node.usage_count = 20
        used = self.graph(used_node)
        self.assertGreater(
            self.trust.internal_experience(used, "概念"),
            self.trust.internal_experience(idle, "概念"),
        )

    def test_bootstrap_seed_weighs_the_same_as_llm_seed(self):
        """同梱seedもLLM由来seedも「仮置きの足場」なので内部経験は同じ重み。"""
        bootstrap = Node(inputs=["x"], spatial_tag="概念", source="bootstrap_seed")
        llm_seed = Node(inputs=["x"], spatial_tag="概念", source="llm_seed")
        self.assertAlmostEqual(
            self.trust._node_experience_weight(bootstrap),
            self.trust._node_experience_weight(llm_seed),
        )

    def test_bootstrap_seed_weighs_far_less_than_manual(self):
        seed = Node(inputs=["x"], spatial_tag="概念", source="bootstrap_seed")
        manual = Node(inputs=["x"], spatial_tag="概念", source="manual")
        self.assertLess(
            self.trust._node_experience_weight(seed),
            self.trust._node_experience_weight(manual),
        )

    def test_unknown_source_uses_default_weight(self):
        node = Node(inputs=["x"], spatial_tag="概念", source="謎の出自")
        self.assertAlmostEqual(
            self.trust._node_experience_weight(node), self.trust.config.default_source_weight
        )


class TestConfig(TrustTestCase):
    def test_from_dict_ignores_unknown_keys(self):
        cfg = LLMTrustConfig.from_dict({"trust_decay_scale": 0.5, "存在しない設定": 1})
        self.assertEqual(cfg.trust_decay_scale, 0.5)

    def test_round_trip(self):
        cfg = LLMTrustConfig(trust_decay_scale=0.7, usage_weight=0.5)
        restored = LLMTrustConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored.trust_decay_scale, 0.7)
        self.assertEqual(restored.usage_weight, 0.5)
        self.assertEqual(restored.source_weights, cfg.source_weights)

    def test_larger_decay_scale_keeps_trust_higher(self):
        g = self.graph(*[
            Node(inputs=[f"m{i}"], spatial_tag="概念", source="manual") for i in range(5)
        ])
        slow = LLMTrust(LLMTrustConfig(trust_decay_scale=3.0))
        fast = LLMTrust(LLMTrustConfig(trust_decay_scale=0.3))
        self.assertGreater(slow.trust_for(g, "概念"), fast.trust_for(g, "概念"))

    def test_trust_by_domain_covers_all_tags(self):
        tags = ["人", "概念", "物語", "制度", "身体"]
        result = self.trust.trust_by_domain(self.graph(), tags)
        self.assertEqual(set(result), set(tags))

    def test_source_weights_are_not_shared_between_configs(self):
        a = LLMTrustConfig()
        b = LLMTrustConfig()
        a.source_weights["manual"] = 0.01
        self.assertNotEqual(b.source_weights["manual"], 0.01)


if __name__ == "__main__":
    unittest.main()
