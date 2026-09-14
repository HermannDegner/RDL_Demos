import unittest

from rdl_bot.v23_state import (
    BoundaryContext,
    CoverageState,
    Provenance,
    UnresolvedMismatchState,
    acquire_text_section,
    compare_interpretations,
    interpret_section,
)


class V23BotStateTests(unittest.TestCase):
    def setUp(self):
        self.context = BoundaryContext(
            boundary_id="bot:test",
            purpose="conversation_interpretation",
            question="what changed?",
            observation_time="2026-09-14T10:00:00+09:00",
            conditions={"channel": "test"},
        )

    @staticmethod
    def interpreter(section):
        text = section.payload["text"]
        return {
            "length": min(len(text) / 20.0, 1.0),
            "question": 1.0 if "?" in text else 0.0,
        }

    def test_raw_text_and_rib_section_remain_distinct(self):
        section = acquire_text_section(
            section_id="rib:1",
            text="hello?",
            context=self.context,
            provenance=Provenance(source="user", actor="tester"),
        )
        self.assertEqual(section.payload["text"], "hello?")
        self.assertEqual(section.role, "observation")
        self.assertFalse(hasattr(section, "F"))

    def test_same_preupdate_model_forms_f_fprime_and_e(self):
        first = acquire_text_section(section_id="rib:1", text="hello", context=self.context)
        later = acquire_text_section(section_id="rib:2", text="hello?", context=self.context, role="later")

        f = interpret_section(first, model_ref="M_B:v1", interpreter=self.interpreter)
        f_prime = interpret_section(later, model_ref="M_B:v1", interpreter=self.interpreter)
        mismatch = compare_interpretations(f, f_prime)

        self.assertEqual(f.model_ref, f_prime.model_ref)
        self.assertEqual(mismatch.values["question"], 1.0)
        self.assertGreater(mismatch.magnitude, 0.0)

    def test_model_drift_is_rejected_before_e(self):
        first = acquire_text_section(section_id="rib:1", text="a", context=self.context)
        later = acquire_text_section(section_id="rib:2", text="b", context=self.context)
        f = interpret_section(first, model_ref="M_B:v1", interpreter=self.interpreter)
        f_prime = interpret_section(later, model_ref="M_B:v2", interpreter=self.interpreter)
        with self.assertRaises(ValueError):
            compare_interpretations(f, f_prime)

    def test_resolved_mismatch_does_not_enter_h(self):
        first = acquire_text_section(section_id="rib:1", text="a", context=self.context)
        later = acquire_text_section(section_id="rib:2", text="a?", context=self.context)
        f = interpret_section(first, model_ref="M_B:v1", interpreter=self.interpreter)
        f_prime = interpret_section(later, model_ref="M_B:v1", interpreter=self.interpreter)
        mismatch = compare_interpretations(f, f_prime)

        h = UnresolvedMismatchState(theta=0.5)
        h.observe(mismatch, unresolved=False)
        self.assertEqual(h.magnitude, 0.0)
        self.assertFalse(h.should_reconstruct)

    def test_unresolved_mismatch_can_drive_fixed_theta(self):
        first = acquire_text_section(section_id="rib:1", text="a", context=self.context)
        later = acquire_text_section(section_id="rib:2", text="a?", context=self.context)
        f = interpret_section(first, model_ref="M_B:v1", interpreter=self.interpreter)
        f_prime = interpret_section(later, model_ref="M_B:v1", interpreter=self.interpreter)
        mismatch = compare_interpretations(f, f_prime)

        h = UnresolvedMismatchState(theta=0.5)
        h.observe(mismatch, unresolved=True)
        self.assertGreaterEqual(h.magnitude, 0.5)
        self.assertTrue(h.should_reconstruct)

    def test_coverage_is_separate_from_h_and_xi(self):
        coverage = CoverageState()
        coverage.record_missing(2)
        coverage.record_unknown_route()
        coverage.record_rejection()

        h = UnresolvedMismatchState(theta=0.5)
        self.assertEqual(h.magnitude, 0.0)
        self.assertEqual(coverage.snapshot()["missing_inputs"], 2)
        self.assertFalse(hasattr(coverage, "xi"))
        self.assertFalse(h.should_reconstruct)


if __name__ == "__main__":
    unittest.main()
