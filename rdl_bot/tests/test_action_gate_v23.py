"""Tests for canonical reconstruction action gating."""

import unittest

from action_gate_v23 import CanonicalActionGate
from authority_v23 import CanonicalLeapAuthority
from resolution_v23 import ResolutionAssessment
from v23_state import MismatchObservation


def unresolved(reason="still unresolved"):
    return ResolutionAssessment.unresolved_case(
        reason=reason,
        assessor="action-gate-test",
        evidence_refs=("turn-1", "turn-2", "review-1"),
    )


def resolved():
    return ResolutionAssessment.resolved(
        reason="accounted for",
        assessor="action-gate-test",
        evidence_refs=("turn-1", "turn-2"),
    )


class CanonicalActionGateTests(unittest.TestCase):
    def test_below_theta_creates_no_request(self):
        authority = CanonicalLeapAuthority(theta=2.0)
        observation = authority.observe_mismatch(
            MismatchObservation(values={"route": 1.0}),
            assessment=unresolved(),
        )

        self.assertIsNone(CanonicalActionGate().request(observation))

    def test_resolved_mismatch_creates_no_request(self):
        authority = CanonicalLeapAuthority(theta=0.5)
        observation = authority.observe_mismatch(
            MismatchObservation(values={"route": 2.0}),
            assessment=resolved(),
        )

        self.assertIsNone(CanonicalActionGate().request(observation))

    def test_unresolved_above_theta_creates_targetless_request(self):
        authority = CanonicalLeapAuthority(theta=0.5)
        observation = authority.observe_mismatch(
            MismatchObservation(values={"route": 1.0, "confidence": 0.2}),
            assessment=unresolved("explicit finite review left mismatch unresolved"),
        )

        request = CanonicalActionGate().request(observation)

        self.assertIsNotNone(request)
        self.assertEqual(request.status, "canonical-reconstruction-requested")
        self.assertIsNone(request.target_ref)
        self.assertEqual(request.assessment_assessor, "action-gate-test")
        self.assertIn("route", request.mismatch_reasons)
        self.assertIn("review-1", request.evidence_refs)

    def test_gate_does_not_accept_legacy_state_objects(self):
        gate = CanonicalActionGate()

        with self.assertRaises(TypeError):
            gate.request(object())

    def test_gate_api_has_no_legacy_hot_node_input(self):
        authority = CanonicalLeapAuthority(theta=0.5)
        observation = authority.observe_mismatch(
            MismatchObservation(values={"route": 1.0}),
            assessment=unresolved(),
        )
        gate = CanonicalActionGate()

        with self.assertRaises(TypeError):
            gate.request(observation, hot_node="legacy-node")


if __name__ == "__main__":
    unittest.main()
