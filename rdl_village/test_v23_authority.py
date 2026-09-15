import unittest
from types import SimpleNamespace

from .simulation import VillageSimulation
from .v23_authority import (
    INSTALL_KIND,
    INSTALL_SCOPE,
    VillageContextObserverView,
    install_village_canonical_authority,
)
from .v23_boundary import VillageMismatch, assess_village_mismatch
from .v23_live_observer import (
    DEFAULT_OBSERVER_COEFFICIENTS,
    VILLAGE_OBSERVER_DIMENSIONS,
    attach_v23_observer,
)
from .v23_mdelta_t1 import (
    VillageReconstructionProposal,
    validate_village_reentry,
)
from .v23_boundary import VillageBoundary, acquire_village_section


class VillageV23AuthorityTests(unittest.TestCase):
    @staticmethod
    def _proposal(agent_name, *, place="well", band="morning"):
        coefficients = dict(DEFAULT_OBSERVER_COEFFICIENTS)
        coefficients["visible_agents"] = 0.15
        return VillageReconstructionProposal(
            proposal_ref=f"proposal:{agent_name}:{place}:{band}",
            request_ref=f"mdelta:{agent_name}:{place}:{band}",
            subject_ref=f"M_B:{agent_name}:current",
            candidate_model_ref=f"M_B_prime:{agent_name}:{place}:{band}",
            candidate_structure={
                "kind": INSTALL_KIND,
                "installScope": INSTALL_SCOPE,
                "placeId": place,
                "observerCoefficients": coefficients,
                "placeMeaningPatch": {
                    "socialExpectation": 0.62,
                    "resourceExpectation": 0.31,
                },
            },
            selection_ref=f"selection:{agent_name}:{place}:{band}",
            retained_relations=(
                "social-density -> local social expectation",
                "resource-visibility -> local resource expectation",
            ),
            valid_conditions=(f"place={place}", f"band={band}"),
            break_conditions=("finite context changes", "fresh unresolved mismatch"),
            unresolved_items=("other finite contexts remain separately revisable",),
            boundary_mode="maintain",
            target_boundary_id=f"village:{agent_name}:local-observation",
            target_purpose="npc_local_interpretation",
            target_dimensions=VILLAGE_OBSERVER_DIMENSIONS,
            target_conditions={"place": place, "band": band},
            basis=("finite retained relations with explicit context scope",),
            builder="authority-test-builder",
        )

    @staticmethod
    def _validation(proposal, index):
        boundary = VillageBoundary(
            boundary_id=proposal.target_boundary_id,
            purpose=proposal.target_purpose,
            dimensions=proposal.target_dimensions,
            conditions=dict(proposal.target_conditions),
        )
        values = {
            "body_crisis": 0.2,
            "discomfort": 0.1,
            "visible_agents": 1.0,
            "visible_resources": 1.0,
        }
        current = acquire_village_section(
            section_id=f"authority-reentry:{index}:a",
            boundary=boundary,
            values=values,
        )
        later = acquire_village_section(
            section_id=f"authority-reentry:{index}:b",
            boundary=boundary,
            values=values,
        )
        return validate_village_reentry(
            proposal,
            current,
            later,
            coefficients=proposal.candidate_structure["observerCoefficients"],
        )

    def _authority_fixture(self):
        simulation = VillageSimulation(seed=31)
        observer = attach_v23_observer(simulation)
        authority = install_village_canonical_authority(
            simulation,
            required_shadow_validations=2,
            reentry_validation_windows=2,
        )
        agent = simulation.agents[0]
        agent.prediction_field.meaning("well")
        proposal = self._proposal(agent.name)
        validations = (self._validation(proposal, 1), self._validation(proposal, 2))
        return simulation, observer, authority, agent, proposal, validations

    def test_cutover_requires_distinct_stable_shadow_windows(self):
        _, _, authority, agent, proposal, validations = self._authority_fixture()
        controller = authority.controller(agent.name)

        with self.assertRaisesRegex(ValueError, "more stable shadow"):
            controller.activate(
                proposal,
                validations[:1],
                installer="test-installer",
                basis=("finite cutover gate",),
                evidence_refs=("shadow:1",),
            )

        with self.assertRaisesRegex(ValueError, "distinct fresh shadow"):
            controller.activate(
                proposal,
                (validations[0], validations[0]),
                installer="test-installer",
                basis=("finite cutover gate",),
                evidence_refs=("shadow:1",),
            )

    def test_context_cutover_switches_model_and_disables_legacy_leap_only_inside_B(self):
        _, observer, authority, agent, proposal, validations = self._authority_fixture()
        controller = authority.controller(agent.name)
        base = agent.prediction_field.meaning("well")
        base_social = base.social_expectation

        audit = controller.activate(
            proposal,
            validations,
            installer="test-installer",
            basis=("two stable shadow windows and explicit finite adapter",),
            evidence_refs=("shadow:1", "shadow:2"),
        )
        self.assertEqual(audit.status, "M_B-prime-installed")
        self.assertEqual(audit.xi_status, "unrecovered-relations-remain")

        target = SimpleNamespace(place_id="well", band="morning")
        controller.prepare_context(target)
        self.assertIsNotNone(controller.current_model)
        self.assertEqual(observer.model_ref, proposal.candidate_model_ref)
        self.assertAlmostEqual(observer.coefficients["visible_agents"], 0.15)
        self.assertAlmostEqual(base.social_expectation, 0.62)
        self.assertFalse(controller.snapshot()["legacyLeapAuthority"])

        # Even an artificially high legacy local load cannot authorize a leap
        # while this finite B is under canonical authority.
        agent.h_vec.values["resource"] = 999.0
        self.assertIsNone(agent.leap_engine.check(agent.h_vec, agent.xi, 9999))
        self.assertIsNone(agent.leap_engine.check_basal(agent.h_vec, agent.xi, 9999))

        # The same place in another band is a different finite context.  Its
        # pre-cutover place state and observer evaluator are restored.
        outside = SimpleNamespace(place_id="well", band="evening")
        controller.prepare_context(outside)
        self.assertIsNone(controller.current_model)
        self.assertEqual(observer.model_ref, controller.default_model_ref)
        self.assertEqual(dict(observer.coefficients), dict(controller.default_coefficients))
        self.assertAlmostEqual(base.social_expectation, base_social)
        self.assertTrue(controller.snapshot()["legacyLeapAuthority"])

        # Context-local state is retained independently rather than reapplying
        # the patch from scratch on every visit.
        controller.prepare_context(target)
        base.social_expectation = 0.71
        controller.prepare_context(outside)
        controller.prepare_context(target)
        self.assertAlmostEqual(base.social_expectation, 0.71)

    def test_authority_install_without_activated_context_is_fixed_seed_nonintervening(self):
        plain = VillageSimulation(seed=73)
        managed = VillageSimulation(seed=73)
        attach_v23_observer(plain)
        attach_v23_observer(managed)
        install_village_canonical_authority(managed)

        for _ in range(96):
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

    def test_context_observer_view_keeps_h_local_to_one_finite_B(self):
        dims = ("body_crisis", "discomfort", "visible_agents", "visible_resources")
        well = VillageMismatch(
            values={"body_crisis": 0.0, "discomfort": 0.0, "visible_agents": 0.25, "visible_resources": 0.0},
            boundary_id="village:Test:local-observation",
            purpose="npc_local_interpretation",
            dimensions=dims,
            conditions={"place": "well", "band": "morning"},
            current_section_id="well:a",
            later_section_id="well:b",
            model_ref="M_B:test",
        )
        garden = VillageMismatch(
            values={"body_crisis": 0.0, "discomfort": 0.0, "visible_agents": 0.75, "visible_resources": 0.0},
            boundary_id="village:Test:local-observation",
            purpose="npc_local_interpretation",
            dimensions=dims,
            conditions={"place": "garden", "band": "morning"},
            current_section_id="garden:a",
            later_section_id="garden:b",
            model_ref="M_B:test",
        )
        well_review = assess_village_mismatch(
            well,
            status="unresolved-mismatch",
            basis=("finite well review",),
            assessor="test-reviewer",
            unresolved_dimensions=("visible_agents",),
        )
        garden_review = assess_village_mismatch(
            garden,
            status="unresolved-mismatch",
            basis=("finite garden review",),
            assessor="test-reviewer",
            unresolved_dimensions=("visible_agents",),
        )

        class FakeObserver:
            theta = 0.2

            def reviews_for(self, _name):
                return (well_review, garden_review)

            def review_candidates_for(self, _name):
                return ()

        view = VillageContextObserverView(FakeObserver(), "Test", well.context_key)
        snapshot = view.h_snapshot("Test")
        self.assertAlmostEqual(snapshot["H_vec"]["visible_agents"], 0.25)
        self.assertAlmostEqual(snapshot["H"], 0.25)
        self.assertTrue(snapshot["shouldReconstructDiagnostic"])

    def test_cutover_rejects_numeric_xi_even_when_nested(self):
        _, _, authority, agent, proposal, validations = self._authority_fixture()
        invalid = VillageReconstructionProposal(
            proposal_ref="proposal:bad-xi",
            request_ref=proposal.request_ref,
            subject_ref=proposal.subject_ref,
            candidate_model_ref="M_B_prime:bad-xi",
            candidate_structure={
                "kind": INSTALL_KIND,
                "installScope": INSTALL_SCOPE,
                "placeId": "well",
                "observerCoefficients": dict(DEFAULT_OBSERVER_COEFFICIENTS),
                "placeMeaningPatch": {"socialExpectation": 0.5},
                "metadata": {"xi": 0.1},
            },
            selection_ref=proposal.selection_ref,
            retained_relations=proposal.retained_relations,
            valid_conditions=proposal.valid_conditions,
            break_conditions=proposal.break_conditions,
            unresolved_items=proposal.unresolved_items,
            boundary_mode="maintain",
            target_boundary_id=proposal.target_boundary_id,
            target_purpose=proposal.target_purpose,
            target_dimensions=proposal.target_dimensions,
            target_conditions=dict(proposal.target_conditions),
            basis=("nested numeric xi must still be rejected",),
            builder="test-builder",
        )
        bad_validations = (self._validation(invalid, 11), self._validation(invalid, 12))
        with self.assertRaisesRegex(ValueError, "must not numericize Core xi"):
            authority.activate(
                agent.name,
                invalid,
                bad_validations,
                installer="test-installer",
                basis=("invalid nested xi",),
                evidence_refs=("bad:1",),
            )


if __name__ == "__main__":
    unittest.main()
