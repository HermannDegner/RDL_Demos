"""Step 5 boundary: raw bot feedback events are not canonical Core H."""

import unittest

from h_state import HState, LegacyFeedbackLoadState
from v23_state import (
    BoundaryContext,
    UnresolvedMismatchState,
    acquire_text_section,
    compare_interpretations,
    interpret_section,
)


class FeedbackBoundaryV23Tests(unittest.TestCase):
    def setUp(self):
        self.context = BoundaryContext(
            boundary_id="rdl_bot:feedback-test",
            purpose="compare finite routing interpretations without collapsing feedback into H",
            question="what changed under the same pre-update evaluator?",
        )

    @staticmethod
    def interpreter(section):
        text = str(section.payload.get("text", ""))
        return {
            "length": float(len(text)),
            "has_question": 1.0 if "?" in text or "？" in text else 0.0,
        }

    def canonical_mismatch(self):
        current = acquire_text_section(
            section_id="turn-1",
            text="こんにちは",
            context=self.context,
        )
        later = acquire_text_section(
            section_id="turn-2",
            text="こんにちは？",
            context=self.context,
        )
        f = interpret_section(
            current,
            model_ref="M_B:pre-update:feedback-test",
            interpreter=self.interpreter,
        )
        f_prime = interpret_section(
            later,
            model_ref="M_B:pre-update:feedback-test",
            interpreter=self.interpreter,
        )
        return compare_interpretations(f, f_prime)

    def test_legacy_feedback_state_is_not_canonical_h_type(self):
        legacy = HState(theta=2.0)
        canonical = UnresolvedMismatchState(theta=0.5)

        self.assertIsInstance(legacy, LegacyFeedbackLoadState)
        self.assertNotIsInstance(legacy, UnresolvedMismatchState)
        self.assertNotIsInstance(canonical, LegacyFeedbackLoadState)

    def test_miss_deny_and_silence_do_not_mutate_canonical_h(self):
        legacy = HState(theta=2.0)
        canonical = UnresolvedMismatchState(theta=0.5)

        legacy.on_miss(None)
        legacy.on_deny("node-a")
        legacy.on_silence("node-a")

        self.assertGreater(legacy.merged_h("node-a"), 0.0)
        self.assertEqual(canonical.magnitude, 0.0)
        self.assertFalse(canonical.should_reconstruct)

    def test_resolved_canonical_mismatch_still_does_not_enter_h(self):
        canonical = UnresolvedMismatchState(theta=0.5)
        mismatch = self.canonical_mismatch()

        canonical.observe(mismatch, unresolved=False)

        self.assertEqual(canonical.magnitude, 0.0)
        self.assertFalse(canonical.should_reconstruct)

    def test_only_explicit_unresolved_canonical_mismatch_enters_h(self):
        canonical = UnresolvedMismatchState(theta=0.5)
        mismatch = self.canonical_mismatch()

        canonical.observe(mismatch, unresolved=True)

        self.assertGreater(canonical.magnitude, 0.0)
        self.assertTrue(canonical.should_reconstruct)


if __name__ == "__main__":
    unittest.main()
