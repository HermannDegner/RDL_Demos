import unittest

from .v23_boundary import (
    ExplorationState,
    VillageBoundary,
    VillageUnresolvedH,
    acquire_village_section,
    compare_village_interpretations,
    interpret_village_section,
)


class VillageV23BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.boundary = VillageBoundary(
            boundary_id="village:test",
            purpose="npc_local_interpretation",
            observation_time="day-1:tick-10",
            conditions={"place": "well"},
        )
        self.coefficients = {"resource": 0.8, "danger": 0.6}

    def test_same_model_ref_forms_f_fprime_and_e(self):
        current = acquire_village_section(
            section_id="rib:current",
            boundary=self.boundary,
            values={"resource": 1.0, "danger": 0.2},
        )
        later = acquire_village_section(
            section_id="rib:later",
            boundary=self.boundary,
            values={"resource": 0.25, "danger": 0.8},
            role="later",
        )
        f = interpret_village_section(current, model_ref="M_B:v1", coefficients=self.coefficients)
        f_prime = interpret_village_section(later, model_ref="M_B:v1", coefficients=self.coefficients)
        mismatch = compare_village_interpretations(f, f_prime)

        self.assertAlmostEqual(f.values["resource"], 0.8)
        self.assertAlmostEqual(f_prime.values["resource"], 0.2)
        self.assertAlmostEqual(mismatch.values["resource"], 0.6)
        self.assertAlmostEqual(mismatch.values["danger"], 0.36)

    def test_model_drift_is_rejected(self):
        section = acquire_village_section(
            section_id="rib:1",
            boundary=self.boundary,
            values={"resource": 1.0},
        )
        f = interpret_village_section(section, model_ref="M_B:v1", coefficients=self.coefficients)
        f_prime = interpret_village_section(section, model_ref="M_B:v2", coefficients=self.coefficients)
        with self.assertRaises(ValueError):
            compare_village_interpretations(f, f_prime)

    def test_resolved_e_does_not_enter_h(self):
        current = acquire_village_section(
            section_id="rib:a",
            boundary=self.boundary,
            values={"danger": 0.0},
        )
        later = acquire_village_section(
            section_id="rib:b",
            boundary=self.boundary,
            values={"danger": 1.0},
        )
        f = interpret_village_section(current, model_ref="M_B:v1", coefficients=self.coefficients)
        f_prime = interpret_village_section(later, model_ref="M_B:v1", coefficients=self.coefficients)
        mismatch = compare_village_interpretations(f, f_prime)

        h = VillageUnresolvedH(theta=0.5)
        h.observe(mismatch, unresolved=False)
        self.assertEqual(h.magnitude, 0.0)
        self.assertFalse(h.should_reconstruct)

    def test_unresolved_e_can_enter_h_at_fixed_theta(self):
        current = acquire_village_section(
            section_id="rib:a",
            boundary=self.boundary,
            values={"danger": 0.0},
        )
        later = acquire_village_section(
            section_id="rib:b",
            boundary=self.boundary,
            values={"danger": 1.0},
        )
        f = interpret_village_section(current, model_ref="M_B:v1", coefficients=self.coefficients)
        f_prime = interpret_village_section(later, model_ref="M_B:v1", coefficients=self.coefficients)
        mismatch = compare_village_interpretations(f, f_prime)

        h = VillageUnresolvedH(theta=0.5)
        h.observe(mismatch, unresolved=True)
        self.assertAlmostEqual(h.magnitude, 0.6)
        self.assertTrue(h.should_reconstruct)

    def test_exploration_state_is_not_core_xi_or_h(self):
        exploration = ExplorationState(maximum=2.0, decay=0.5)
        exploration.add_pressure(1.0)
        exploration.hold({"outcome": "unknown"})

        h = VillageUnresolvedH(theta=0.5)
        self.assertEqual(exploration.pressure, 0.5)
        self.assertEqual(len(exploration.unresolved), 1)
        self.assertEqual(h.magnitude, 0.0)
        self.assertFalse(hasattr(exploration, "xi"))


if __name__ == "__main__":
    unittest.main()
