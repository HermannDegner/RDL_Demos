"""Tests for the conservative canonical resolution-assessment policy."""

import unittest

from assessment_policy_v23 import classify_mismatch, promote_pending_to_unresolved
from authority_v23 import CanonicalLeapAuthority
from v23_state import MismatchObservation


class ResolutionPolicyTests(unittest.TestCase):
    def test_zero_mismatch_is_automatically_resolved(self):
        mismatch = MismatchObservation(values={"route": 0.0})

        candidate = classify_mismatch(
            mismatch,
            evidence_refs=("turn-1", "turn-2"),
        )

        self.assertEqual(candidate.status, "resolved")
        self.assertIsNotNone(candidate.assessment)
        self.assertFalse(candidate.assessment.unresolved)
        self.assertIn("turn-1", candidate.assessment.evidence_refs)

    def test_nonzero_mismatch_stays_pending_by_default(self):
        mismatch = MismatchObservation(values={"route": 1.0})

        candidate = classify_mismatch(
            mismatch,
            evidence_refs=("turn-1", "turn-2"),
        )

        self.assertEqual(candidate.status, "pending")
        self.assertTrue(candidate.is_pending)
        self.assertIsNone(candidate.assessment)
        self.assertEqual(candidate.evidence_refs, ("turn-1", "turn-2"))

    def test_magnitude_alone_never_promotes_pending_to_unresolved(self):
        mismatch = MismatchObservation(values={"route": 999.0})

        candidate = classify_mismatch(mismatch)

        self.assertEqual(candidate.status, "pending")
        self.assertIsNone(candidate.assessment)

    def test_pending_requires_explicit_provenance_to_become_unresolved(self):
        mismatch = MismatchObservation(values={"route": 1.0})
        candidate = classify_mismatch(
            mismatch,
            evidence_refs=("turn-1", "turn-2"),
        )

        assessment = promote_pending_to_unresolved(
            candidate,
            reason="the mismatch persisted after an explicit finite re-evaluation",
            assessor="test-harness",
            evidence_refs=("review-1", "turn-2"),
        )

        self.assertTrue(assessment.unresolved)
        self.assertEqual(assessment.assessor, "test-harness")
        self.assertEqual(
            assessment.evidence_refs,
            ("turn-1", "turn-2", "review-1"),
        )

    def test_resolved_candidate_cannot_be_promoted_to_unresolved(self):
        candidate = classify_mismatch(MismatchObservation(values={"route": 0.0}))

        with self.assertRaises(ValueError):
            promote_pending_to_unresolved(
                candidate,
                reason="should not be allowed",
                assessor="test-harness",
            )

    def test_pending_candidate_cannot_update_authority_directly(self):
        candidate = classify_mismatch(MismatchObservation(values={"route": 1.0}))
        authority = CanonicalLeapAuthority(theta=0.5)

        with self.assertRaises(TypeError):
            authority.observe_mismatch(
                candidate.mismatch,
                assessment=candidate,
            )

        self.assertEqual(authority.h_magnitude, 0.0)

    def test_policy_api_has_no_legacy_feedback_shortcut(self):
        mismatch = MismatchObservation(values={"route": 1.0})

        with self.assertRaises(TypeError):
            classify_mismatch(mismatch, deny=1)
        with self.assertRaises(TypeError):
            classify_mismatch(mismatch, miss=True)
        with self.assertRaises(TypeError):
            classify_mismatch(mismatch, silence=True)


if __name__ == "__main__":
    unittest.main()
