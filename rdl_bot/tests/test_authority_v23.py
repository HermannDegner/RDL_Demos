"""Step 6 candidate authority tests for the rdl_bot migration."""

import unittest

from authority_v23 import CanonicalLeapAuthority
from h_state import HState, unresolved_input_pressure
from local_state import UnresolvedInputQueue
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


class CanonicalAuthorityTests(unittest.TestCase):
    def shadow_pair(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("known", graph)
        shadow.capture_input("unknown", graph)
        return graph, shadow

    def test_resolved_mismatch_does_not_drive_reconstruction(self):
        _, shadow = self.shadow_pair()
        authority = CanonicalLeapAuthority(theta=0.5)

        observation = authority.observe_turn_pair(shadow, 1, 2, unresolved=False)

        self.assertEqual(observation.status, "observed-resolved")
        self.assertEqual(authority.h_magnitude, 0.0)
        self.assertFalse(authority.should_reconstruct)
        self.assertEqual(authority.theta, 0.5)

    def test_unresolved_canonical_mismatch_can_drive_fixed_theta(self):
        _, shadow = self.shadow_pair()
        authority = CanonicalLeapAuthority(theta=0.5)

        observation = authority.observe_turn_pair(shadow, 1, 2, unresolved=True)

        self.assertEqual(observation.status, "observed-unresolved")
        self.assertGreater(authority.h_magnitude, 0.0)
        self.assertTrue(authority.should_reconstruct)
        self.assertEqual(observation.theta, 0.5)

    def test_model_change_produces_no_E_and_no_H_update(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("known", graph)
        graph.node.confidence = 0.4  # changes the frozen evaluator fingerprint
        shadow.capture_input("unknown", graph)
        authority = CanonicalLeapAuthority(theta=0.5)

        observation = authority.observe_turn_pair(shadow, 1, 2, unresolved=True)

        self.assertEqual(observation.status, "model-changed-no-E")
        self.assertIsNone(observation.mismatch)
        self.assertEqual(authority.h_magnitude, 0.0)
        self.assertFalse(authority.should_reconstruct)

    def test_legacy_feedback_does_not_change_canonical_authority(self):
        authority = CanonicalLeapAuthority(theta=0.5)
        legacy = HState(theta=0.5)

        for _ in range(5):
            legacy.on_deny("node-known")
            legacy.on_silence("node-known")
            legacy.on_miss(None)

        self.assertGreater(legacy.merged_h("node-known"), authority.theta)
        self.assertEqual(authority.h_magnitude, 0.0)
        self.assertFalse(authority.should_reconstruct)
        self.assertEqual(authority.theta, 0.5)

    def test_queue_size_is_diagnostic_but_cannot_change_fixed_theta(self):
        authority = CanonicalLeapAuthority(theta=0.5)
        queue = UnresolvedInputQueue(["a", "b", "c", "d"])
        diagnostic = unresolved_input_pressure(queue, saturation=2.0)

        self.assertEqual(diagnostic, 1.0)
        self.assertEqual(authority.theta, 0.5)
        self.assertEqual(authority.h_magnitude, 0.0)
        self.assertFalse(authority.should_reconstruct)

    def test_authority_api_has_no_pressure_or_feedback_input(self):
        authority = CanonicalLeapAuthority(theta=0.5)

        with self.assertRaises(TypeError):
            CanonicalLeapAuthority(theta=0.5, pressure=1.0)
        with self.assertRaises(TypeError):
            authority.observe_turn_pair(None, 1, 2, unresolved=True, deny=3)


if __name__ == "__main__":
    unittest.main()
