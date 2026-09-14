"""Parallel legacy/canonical decision observation for Step 6."""

import unittest

from authority_v23 import CanonicalLeapAuthority
from h_state import HState
from parallel_v23 import CanonicalParallelObserver
from runtime_v23 import V23ConversationShadow


class _Node:
    def __init__(self):
        self.id = "node-known"
        self.status = "active"
        self.phase = "act"
        self.confidence = 0.8
        self.usage_count = 0


class _Graph:
    def __init__(self):
        self.node = _Node()
        self.nodes = {self.node.id: self.node}

    def search(self, text):
        if text == "known":
            return self.node, "exact", self.node
        return None, "miss", self.node


def shadow_pair():
    graph = _Graph()
    shadow = V23ConversationShadow()
    shadow.capture_input("known", graph)
    shadow.capture_input("unknown", graph)
    return graph, shadow


class ParallelAuthorityTests(unittest.TestCase):
    def test_legacy_hot_canonical_resolved_divergence_is_visible(self):
        _, shadow = shadow_pair()
        legacy = HState(theta=0.5)
        legacy.on_deny("node-known")
        observer = CanonicalParallelObserver(CanonicalLeapAuthority(theta=0.5))

        record = observer.observe_pair(
            shadow=shadow,
            legacy_state=legacy,
            earlier_index=1,
            later_index=2,
            unresolved=False,
        )

        self.assertTrue(record.legacy_should_leap)
        self.assertFalse(record.canonical_should_reconstruct)
        self.assertFalse(record.agrees)
        self.assertEqual(record.canonical_status, "observed-resolved")

    def test_canonical_unresolved_legacy_cold_divergence_is_visible(self):
        _, shadow = shadow_pair()
        legacy = HState(theta=2.0)
        observer = CanonicalParallelObserver(CanonicalLeapAuthority(theta=0.5))

        record = observer.observe_pair(
            shadow=shadow,
            legacy_state=legacy,
            earlier_index=1,
            later_index=2,
            unresolved=True,
        )

        self.assertFalse(record.legacy_should_leap)
        self.assertTrue(record.canonical_should_reconstruct)
        self.assertFalse(record.agrees)

    def test_parallel_observation_does_not_consume_legacy_load(self):
        _, shadow = shadow_pair()
        legacy = HState(theta=0.5)
        legacy.on_deny("node-known")
        before = legacy.merged_h("node-known")
        observer = CanonicalParallelObserver(CanonicalLeapAuthority(theta=0.5))

        observer.observe_pair(
            shadow=shadow,
            legacy_state=legacy,
            earlier_index=1,
            later_index=2,
            unresolved=False,
        )

        self.assertEqual(legacy.merged_h("node-known"), before)

    def test_model_change_is_recorded_without_false_canonical_action(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("known", graph)
        graph.node.confidence = 0.3
        shadow.capture_input("unknown", graph)
        observer = CanonicalParallelObserver(CanonicalLeapAuthority(theta=0.5))

        record = observer.observe_pair(
            shadow=shadow,
            legacy_state=HState(theta=2.0),
            earlier_index=1,
            later_index=2,
            unresolved=True,
        )

        self.assertEqual(record.canonical_status, "model-changed-no-E")
        self.assertFalse(record.canonical_should_reconstruct)

    def test_records_accumulate_for_external_comparison(self):
        _, shadow = shadow_pair()
        observer = CanonicalParallelObserver(CanonicalLeapAuthority(theta=5.0))
        legacy = HState(theta=5.0)

        first = observer.observe_pair(
            shadow=shadow,
            legacy_state=legacy,
            earlier_index=1,
            later_index=2,
            unresolved=False,
        )
        second = observer.observe_pair(
            shadow=shadow,
            legacy_state=legacy,
            earlier_index=1,
            later_index=2,
            unresolved=False,
        )

        self.assertEqual(observer.records, [first, second])
        self.assertTrue(first.agrees)
        self.assertTrue(second.agrees)


if __name__ == "__main__":
    unittest.main()
