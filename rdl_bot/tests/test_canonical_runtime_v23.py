"""Tests for the conservative canonical runtime controller."""

import unittest

from authority_v23 import CanonicalLeapAuthority
from canonical_runtime_v23 import CanonicalRuntimeController
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


def make_shadow(first="known", second="unknown"):
    graph = _Graph()
    shadow = V23ConversationShadow()
    shadow.capture_input(first, graph)
    shadow.capture_input(second, graph)
    return graph, shadow


class CanonicalRuntimeControllerTests(unittest.TestCase):
    def test_nonzero_live_mismatch_stays_pending_and_does_not_touch_H(self):
        _, shadow = make_shadow()
        authority = CanonicalLeapAuthority(theta=0.5)
        controller = CanonicalRuntimeController(authority)

        record = controller.assess_pair(
            shadow=shadow,
            earlier_index=1,
            later_index=2,
        )

        self.assertEqual(record.status, "pending-review")
        self.assertIsNotNone(record.candidate)
        self.assertIsNone(record.authority_observation)
        self.assertEqual(authority.h_magnitude, 0.0)
        self.assertFalse(authority.should_reconstruct)

    def test_zero_live_mismatch_is_resolved_without_H(self):
        _, shadow = make_shadow(first="known", second="known")
        authority = CanonicalLeapAuthority(theta=0.5)
        controller = CanonicalRuntimeController(authority)

        record = controller.assess_pair(
            shadow=shadow,
            earlier_index=1,
            later_index=2,
        )

        self.assertEqual(record.status, "resolved-observed")
        self.assertIsNotNone(record.authority_observation)
        self.assertFalse(record.authority_observation.unresolved)
        self.assertEqual(authority.h_magnitude, 0.0)

    def test_explicit_promotion_is_the_only_controller_path_into_H(self):
        _, shadow = make_shadow()
        authority = CanonicalLeapAuthority(theta=0.5)
        controller = CanonicalRuntimeController(authority)
        record = controller.assess_pair(
            shadow=shadow,
            earlier_index=1,
            later_index=2,
        )

        observation = controller.promote_record(
            record,
            reason="finite re-evaluation left the canonical mismatch unresolved",
            assessor="test-reviewer",
            evidence_refs=("review-1",),
        )

        self.assertTrue(observation.unresolved)
        self.assertGreater(authority.h_magnitude, 0.0)
        self.assertTrue(authority.should_reconstruct)
        self.assertEqual(observation.assessment.assessor, "test-reviewer")

    def test_resolved_record_cannot_be_promoted(self):
        _, shadow = make_shadow(first="known", second="known")
        controller = CanonicalRuntimeController(CanonicalLeapAuthority(theta=0.5))
        record = controller.assess_pair(
            shadow=shadow,
            earlier_index=1,
            later_index=2,
        )

        with self.assertRaises(ValueError):
            controller.promote_record(
                record,
                reason="invalid promotion",
                assessor="test-reviewer",
            )

    def test_boundary_change_stops_comparison_without_H(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("known", graph)
        shadow.boundary_id = "rdl_bot:other-boundary"
        shadow.capture_input("unknown", graph)
        authority = CanonicalLeapAuthority(theta=0.5)
        controller = CanonicalRuntimeController(authority)

        record = controller.assess_pair(
            shadow=shadow,
            earlier_index=1,
            later_index=2,
        )

        self.assertEqual(record.status, "boundary-changed-no-E")
        self.assertIsNone(record.candidate)
        self.assertEqual(authority.h_magnitude, 0.0)


if __name__ == "__main__":
    unittest.main()
