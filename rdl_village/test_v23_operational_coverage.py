import unittest

from .simulation import VillageSimulation
from .v23_boundary import VillageMismatch
from .v23_operational import install_village_operational_coverage
from .v23_review import VillageLocalAbsorptionEvidence, VillageUnresolvedReviewCandidate
from .v23_review_assist import VillageReviewAdvisor


DIMS = ("body_crisis", "discomfort", "visible_agents", "visible_resources")


class VillageV23OperationalCoverageTests(unittest.TestCase):
    @staticmethod
    def _candidate(index, value, *, agent="Test", place="well", band="morning"):
        mismatch = VillageMismatch(
            values={
                "body_crisis": 0.0,
                "discomfort": 0.0,
                "visible_agents": float(value),
                "visible_resources": 0.0,
            },
            boundary_id=f"village:{agent}:local-observation",
            purpose="npc_local_interpretation",
            dimensions=DIMS,
            conditions={"place": place, "band": band},
            current_section_id=f"section:{index}:a",
            later_section_id=f"section:{index}:b",
            model_ref="M_B:test",
        )
        absorption = VillageLocalAbsorptionEvidence(
            status="bounded-local-adjustment-observed",
            tick=index,
            previous_tick=index - 1,
            boundary_id=mismatch.boundary_id,
            purpose=mismatch.purpose,
            place_id=place,
            before={
                "comfort": 0.1,
                "social_expectation": 0.1,
                "resource_expectation": 0.1,
            },
            expected_after={
                "comfort": 0.1,
                "social_expectation": 0.13,
                "resource_expectation": 0.1,
            },
            observed_after={
                "comfort": 0.1,
                "social_expectation": 0.13,
                "resource_expectation": 0.1,
            },
            changed_axes=("social_expectation",),
            evidence_ref=f"local-update:{index}",
        )
        return VillageUnresolvedReviewCandidate(
            candidate_id=f"candidate:{index}",
            agent_name=agent,
            mismatch=mismatch,
            local_absorption=absorption,
            candidate_dimensions=("visible_agents",),
            evidence_refs=(
                mismatch.current_section_id,
                mismatch.later_section_id,
                absorption.evidence_ref,
            ),
        )

    def test_repeated_same_signed_residual_recommends_review_without_classifying(self):
        advisor = VillageReviewAdvisor(required_distinct_windows=3)
        candidates = (
            self._candidate(1, 0.25),
            self._candidate(2, 0.30),
            self._candidate(3, 0.20),
        )
        recommendations = advisor.recommendations(candidates)
        self.assertEqual(len(recommendations), 1)
        recommendation = recommendations[0]
        self.assertEqual(recommendation.dimension, "visible_agents")
        self.assertEqual(recommendation.direction, "positive")
        self.assertEqual(recommendation.window_count, 3)
        self.assertEqual(recommendation.status, "review-recommended")
        self.assertEqual(recommendation.authority, "advisory-only")
        self.assertEqual(recommendation.classification_status, "not-performed")
        self.assertFalse(recommendation.ordinary_temporal_change_excluded)
        self.assertFalse(recommendation.boundary_or_coverage_change_excluded)
        self.assertEqual(recommendation.xi_status, "unrecovered-relations-remain")

    def test_rereading_same_candidate_cannot_manufacture_persistence(self):
        advisor = VillageReviewAdvisor(required_distinct_windows=3)
        candidate = self._candidate(1, 0.25)
        self.assertEqual(advisor.recommendations((candidate, candidate, candidate)), ())

    def test_sign_reversal_starts_new_persistence_run(self):
        advisor = VillageReviewAdvisor(required_distinct_windows=3)
        first = (
            self._candidate(1, 0.25),
            self._candidate(2, 0.20),
            self._candidate(3, -0.15),
            self._candidate(4, -0.20),
        )
        self.assertEqual(advisor.recommendations(first), ())
        recommendation = advisor.recommendations(first + (self._candidate(5, -0.18),))[0]
        self.assertEqual(recommendation.direction, "negative")
        self.assertEqual(recommendation.candidate_ids, ("candidate:3", "candidate:4", "candidate:5"))

    def test_contexts_never_combine_to_reach_review_window_count(self):
        advisor = VillageReviewAdvisor(required_distinct_windows=3)
        candidates = (
            self._candidate(1, 0.25, place="well"),
            self._candidate(2, 0.25, place="garden"),
            self._candidate(3, 0.25, place="well"),
        )
        self.assertEqual(advisor.recommendations(candidates), ())

    def test_minimum_residual_is_advisory_filter_not_h_threshold(self):
        advisor = VillageReviewAdvisor(required_distinct_windows=2, minimum_abs_residual=0.2)
        candidates = (
            self._candidate(1, 0.10),
            self._candidate(2, 0.15),
            self._candidate(3, 0.25),
            self._candidate(4, 0.30),
        )
        recommendation = advisor.recommendations(candidates)[0]
        self.assertEqual(recommendation.candidate_ids, ("candidate:3", "candidate:4"))
        self.assertIn("advisory-only", recommendation.authority)

    def test_operational_coverage_install_is_nonintervening_before_activation(self):
        plain = VillageSimulation(seed=91)
        managed = VillageSimulation(seed=91)
        install_village_operational_coverage(
            managed,
            theta=1.0,
            required_review_windows=3,
        )

        for _ in range(64):
            plain.step()
            managed.step()

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

        self.assertEqual(signature(plain), signature(managed))
        coverage = managed.v23OperationalCoverage.snapshot()
        self.assertEqual(coverage["reviewPolicy"], "explicit-review-required")
        self.assertEqual(coverage["recommendationAuthority"], "advisory-only")
        self.assertEqual(coverage["finiteContextPolicy"], "no-cross-context-generalization")


if __name__ == "__main__":
    unittest.main()
