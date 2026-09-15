import random
import unittest

from .dialogue import RelationalDialogueSystem
from . import dialogue_local_aliases as _dialogue_local_aliases  # noqa: F401
from .simulation import VillageSimulation
from .v23_boundary import (
    ExplorationState,
    VillageBoundary,
    VillageBoundaryChange,
    VillageCoverageError,
    VillageUnresolvedH,
    acquire_village_section,
    assess_village_mismatch,
    compare_village_interpretations,
    interpret_village_section,
)
from .v23_live_observer import attach_v23_observer


class VillageV23BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.boundary = VillageBoundary(
            boundary_id="village:test",
            purpose="npc_local_interpretation",
            dimensions=("resource", "danger"),
            observation_time="day-1:tick-10",
            conditions={"place": "well", "band": "morning"},
        )
        self.coefficients = {"resource": 0.8, "danger": 0.6}

    def _mismatch(self):
        current = acquire_village_section(
            section_id="rib:a",
            boundary=self.boundary,
            values={"resource": 1.0, "danger": 0.0},
        )
        later = acquire_village_section(
            section_id="rib:b",
            boundary=self.boundary,
            values={"resource": 0.25, "danger": 1.0},
            role="later",
        )
        f = interpret_village_section(
            current, model_ref="M_B:v1", coefficients=self.coefficients
        )
        f_prime = interpret_village_section(
            later, model_ref="M_B:v1", coefficients=self.coefficients
        )
        return f, f_prime, compare_village_interpretations(f, f_prime)

    def test_same_model_ref_forms_f_fprime_and_e(self):
        f, f_prime, mismatch = self._mismatch()

        self.assertAlmostEqual(f.values["resource"], 0.8)
        self.assertAlmostEqual(f_prime.values["resource"], 0.2)
        self.assertAlmostEqual(mismatch.values["resource"], 0.6)
        self.assertAlmostEqual(mismatch.values["danger"], 0.6)

    def test_model_drift_is_rejected(self):
        section = acquire_village_section(
            section_id="rib:1",
            boundary=self.boundary,
            values={"resource": 1.0, "danger": 0.2},
        )
        f = interpret_village_section(
            section, model_ref="M_B:v1", coefficients=self.coefficients
        )
        f_prime = interpret_village_section(
            section, model_ref="M_B:v2", coefficients=self.coefficients
        )
        with self.assertRaises(ValueError):
            compare_village_interpretations(f, f_prime)

    def test_missing_selected_dimension_is_not_invented_as_zero(self):
        incomplete = acquire_village_section(
            section_id="rib:missing",
            boundary=self.boundary,
            values={"resource": 1.0},
        )
        self.assertEqual(incomplete.missing_dimensions, ("danger",))
        with self.assertRaises(VillageCoverageError):
            interpret_village_section(
                incomplete, model_ref="M_B:v1", coefficients=self.coefficients
            )

    def test_boundary_or_purpose_change_breaks_comparison_window(self):
        current = acquire_village_section(
            section_id="rib:a",
            boundary=self.boundary,
            values={"resource": 1.0, "danger": 0.2},
        )
        changed_boundary = VillageBoundary(
            boundary_id="village:test",
            purpose="npc_local_interpretation",
            dimensions=("resource", "danger"),
            observation_time="day-1:tick-11",
            conditions={"place": "garden", "band": "morning"},
        )
        later = acquire_village_section(
            section_id="rib:b",
            boundary=changed_boundary,
            values={"resource": 0.5, "danger": 0.2},
        )
        f = interpret_village_section(
            current, model_ref="M_B:v1", coefficients=self.coefficients
        )
        f_prime = interpret_village_section(
            later, model_ref="M_B:v1", coefficients=self.coefficients
        )
        with self.assertRaises(VillageBoundaryChange):
            compare_village_interpretations(f, f_prime)

    def test_nonzero_e_defaults_pending_and_does_not_enter_h(self):
        _, _, mismatch = self._mismatch()
        assessment = assess_village_mismatch(mismatch)
        self.assertEqual(assessment.status, "pending-assessment")
        self.assertFalse(assessment.eligible_for_h)

        h = VillageUnresolvedH(theta=0.5)
        h.observe(assessment)
        self.assertEqual(h.magnitude, 0.0)
        self.assertFalse(h.should_reconstruct)

    def test_explicit_resolved_e_does_not_enter_h(self):
        _, _, mismatch = self._mismatch()
        assessment = assess_village_mismatch(
            mismatch,
            status="resolved-difference",
            basis=("finite-local-explanation:test",),
            assessor="test-harness",
        )
        h = VillageUnresolvedH(theta=0.5)
        h.observe(assessment)
        self.assertEqual(h.magnitude, 0.0)
        self.assertFalse(h.should_reconstruct)

    def test_only_explicit_unresolved_assessment_can_enter_h(self):
        _, _, mismatch = self._mismatch()
        with self.assertRaises(ValueError):
            assess_village_mismatch(
                mismatch,
                status="unresolved-mismatch",
                basis=("persistent finite mismatch",),
            )

        assessment = assess_village_mismatch(
            mismatch,
            status="unresolved-mismatch",
            basis=("persistent finite mismatch",),
            assessor="test-harness",
        )
        h = VillageUnresolvedH(theta=0.5)
        h.observe(assessment)
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

    def test_dialogue_unresolved_queue_is_demo_local_alias_not_core_xi(self):
        system = RelationalDialogueSystem(object(), random.Random(0))
        self.assertIs(system.unresolved_dialogue_queue, system.xi_pool)

        system.unresolved_dialogue_queue.append(("ask", "unknown-topic"))
        self.assertEqual(system.xi_pool, [("ask", "unknown-topic")])
        self.assertFalse(hasattr(system.unresolved_dialogue_queue, "xi"))

    def test_live_observer_is_fixed_seed_non_intervening(self):
        plain = VillageSimulation(seed=19)
        watched = VillageSimulation(seed=19)
        observer = attach_v23_observer(watched)

        for _ in range(96):
            plain.step()
            watched.step()

        def signature(simulation):
            return {
                "clock": simulation.world.clock.t,
                "weather": simulation.world.weather,
                "logs": simulation.logs,
                "village_log": dict(simulation.village_log),
                "simulation_rng": simulation.rng.getstate(),
                "agents": [
                    {
                        "name": agent.name,
                        "alive": agent.alive,
                        "pos": agent.pos,
                        "body": agent.body.snapshot(),
                        "local_load": agent.h_vec.snapshot(),
                        "exploration": agent.xi.value,
                        "leaps": list(agent.leap_log),
                        "rng": agent.rng.getstate(),
                    }
                    for agent in simulation.agents
                ],
            }

        self.assertEqual(signature(plain), signature(watched))

        formed = []
        for agent in watched.agents:
            records = observer.records_for(agent.name)
            formed.extend(record for record in records if record.get("formed"))
        self.assertTrue(formed)
        self.assertTrue(
            all(
                record["status"] in {"zero-difference", "pending-assessment"}
                for record in formed
            )
        )
        self.assertTrue(all(record["eligibleForH"] is False for record in formed))
        self.assertEqual(observer.snapshot()["authority"], "read-only-sidecar")


if __name__ == "__main__":
    unittest.main()
