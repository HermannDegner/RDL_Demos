import unittest
from types import SimpleNamespace

from .simulation import VillageSimulation
from .v23_authority import INSTALL_KIND, INSTALL_SCOPE
from .v23_boundary import VillageBoundary, acquire_village_section
from .v23_live_observer import DEFAULT_OBSERVER_COEFFICIENTS
from .v23_runtime import install_village_canonical_runtime


class VillageV23RuntimeTests(unittest.TestCase):
    @staticmethod
    def _perception(*, tick, discomfort=0.0, agents=0, resources=0):
        return SimpleNamespace(
            t=tick,
            place_id="well",
            band="morning",
            discomfort=discomfort,
            visible_agents=[object() for _ in range(agents)],
            visible_resources=[SimpleNamespace(state="available") for _ in range(resources)],
        )

    @staticmethod
    def _shadow_sections(proposal, index):
        boundary = VillageBoundary(
            boundary_id=proposal.target_boundary_id,
            purpose=proposal.target_purpose,
            dimensions=proposal.target_dimensions,
            conditions=dict(proposal.target_conditions),
        )
        values = {
            "body_crisis": 0.2,
            "discomfort": 0.2,
            "visible_agents": 1.0,
            "visible_resources": 1.0,
        }
        current = acquire_village_section(
            section_id=f"runtime-shadow:{index}:a",
            boundary=boundary,
            values=values,
        )
        later = acquire_village_section(
            section_id=f"runtime-shadow:{index}:b",
            boundary=boundary,
            values=values,
        )
        return current, later

    def test_explicit_runtime_carries_review_through_install_and_live_reentry(self):
        simulation = VillageSimulation(seed=101)
        runtime = install_village_canonical_runtime(
            simulation,
            theta=0.2,
            required_shadow_validations=2,
            reentry_validation_windows=2,
        )
        observer = simulation.v23_observer
        agent = simulation.agents[0]
        meaning = agent.prediction_field.meaning("well")

        first = self._perception(tick=1)
        observer.capture(agent, first, 1)

        # Exact existing one-step local place update before the second capture.
        meaning.comfort = meaning.comfort * 0.97 - 0.03
        meaning.social_expectation = meaning.social_expectation * 0.96 + 0.03
        meaning.resource_expectation = meaning.resource_expectation * 0.95 + 0.04
        second = self._perception(tick=2, discomfort=0.5, agents=1, resources=1)
        observer.capture(agent, second, 2)
        candidate = observer.review_candidates_for(agent.name)[-1]

        review = runtime.review(
            agent.name,
            candidate.candidate_id,
            status="unresolved-mismatch",
            basis=(
                "bounded local place adjustment was observed",
                "ordinary temporal change excluded for this finite test window",
            ),
            assessor="runtime-test-reviewer",
            ordinary_temporal_change_excluded=True,
            boundary_or_coverage_change_excluded=True,
            unresolved_dimensions=("visible_agents",),
        )
        self.assertTrue(review.eligible_for_h)

        context_key = candidate.mismatch.context_key
        session = runtime.session(agent.name, context_key)
        self.assertIsNotNone(session)
        self.assertEqual(session.status, "M_delta-awaiting-probe")
        self.assertEqual(session.handoff.subject_role, "SILN_SELF-current-M_B")

        runtime.record_probe(
            agent.name,
            context_key,
            probe_ref="runtime-probe:1",
            condition_ref="finite-social-density-probe",
            rib_section_ref="runtime-rib:probe:1",
            observed_values={
                "body_crisis": 0.2,
                "discomfort": 0.2,
                "visible_agents": 2.0,
                "visible_resources": 1.0,
            },
            interpreted_values={
                "body_crisis": 0.2,
                "discomfort": 0.2,
                "visible_agents": 0.5,
                "visible_resources": 0.25,
            },
            evidence_refs=("runtime-shadow-probe:1",),
            basis=("explicit finite condition perturbation",),
        )
        runtime.select(
            agent.name,
            context_key,
            selection_ref="runtime-selection:1",
            candidate_ref="runtime-candidate:1",
            decision="retain",
            criteria=("reduce reviewed social-density mismatch while preserving finite coverage",),
            basis=("finite Probe remained interpretable",),
            retained_relations=("social-density -> local social expectation",),
            valid_conditions=("well/morning",),
            break_conditions=("coverage changes", "fresh unresolved mismatch"),
            unresolved_items=("other finite contexts remain untested",),
        )

        coefficients = dict(DEFAULT_OBSERVER_COEFFICIENTS)
        coefficients["visible_agents"] = 0.15
        proposal = runtime.propose(
            agent.name,
            context_key,
            proposal_ref="runtime-proposal:1",
            candidate_model_ref="M_B_prime:runtime:1",
            candidate_structure={
                "kind": INSTALL_KIND,
                "installScope": INSTALL_SCOPE,
                "placeId": "well",
                "observerCoefficients": coefficients,
                "placeMeaningPatch": {
                    "socialExpectation": 0.55,
                    "resourceExpectation": 0.25,
                },
            },
            boundary_mode="maintain",
            basis=("retained finite relation and explicit install adapter",),
            builder="runtime-test-builder",
        )
        self.assertEqual(proposal.authority, "shadow-proposal-only")

        for index in (1, 2):
            current, later = self._shadow_sections(proposal, index)
            validation = runtime.validate_shadow(
                agent.name,
                context_key,
                current,
                later,
                coefficients=coefficients,
            )
            self.assertTrue(validation.stable_for_shadow)

        audit = runtime.install_proposal(
            agent.name,
            context_key,
            installer="runtime-test-installer",
            basis=("two distinct stable shadow windows",),
            evidence_refs=("runtime-shadow:1", "runtime-shadow:2"),
        )
        self.assertEqual(audit.status, "M_B-prime-installed")
        self.assertEqual(session.status, "installed-reentry-pending")

        controller = runtime.authority.controller(agent.name)
        live = self._perception(tick=3, discomfort=0.2, agents=1, resources=1)
        controller.prepare_context(live)
        observer.capture(agent, live, 3)
        controller.observe_after_capture(live)  # starts the fresh window only

        for tick in (4, 5):
            fresh = self._perception(tick=tick, discomfort=0.2, agents=1, resources=1)
            controller.prepare_context(fresh)
            observer.capture(agent, fresh, tick)
            controller.observe_after_capture(fresh)

        completion = runtime.finalize_reentry(
            agent.name,
            context_key,
            basis="two fresh finite zero-difference comparisons after installed M_B prime",
            validator="runtime-test-validator",
            evidence_refs=("live-zero:4", "live-zero:5"),
        )
        self.assertEqual(completion["status"], "normal-operation-restored")
        self.assertEqual(completion["xiStatus"], "unrecovered-relations-remain")
        self.assertEqual(session.status, "reentry-complete")
        self.assertEqual(runtime.snapshot()["reviewPolicy"], "explicit-only-no-automatic-unresolved-promotion")

    def test_runtime_does_not_auto_promote_pending_candidate(self):
        simulation = VillageSimulation(seed=102)
        runtime = install_village_canonical_runtime(simulation, theta=0.2)
        observer = simulation.v23_observer
        agent = simulation.agents[0]
        meaning = agent.prediction_field.meaning("well")

        observer.capture(agent, self._perception(tick=1), 1)
        meaning.comfort = meaning.comfort * 0.97 - 0.03
        meaning.social_expectation = meaning.social_expectation * 0.96 + 0.03
        meaning.resource_expectation = meaning.resource_expectation * 0.95 + 0.04
        observer.capture(
            agent,
            self._perception(tick=2, discomfort=0.5, agents=1, resources=1),
            2,
        )
        candidate = observer.review_candidates_for(agent.name)[-1]
        self.assertIsNone(runtime.session(agent.name, candidate.mismatch.context_key))
        self.assertEqual(observer.h_snapshot(agent.name)["H"], 0.0)


if __name__ == "__main__":
    unittest.main()
