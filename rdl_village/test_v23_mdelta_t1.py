import unittest
from types import SimpleNamespace

from .v23_boundary import VillageBoundary, acquire_village_section
from .v23_live_observer import VillageCanonicalObserver
from .v23_mdelta_t1 import (
    bind_village_mdelta_subject,
    propose_village_reconstruction,
    record_village_probe,
    request_village_mdelta,
    select_village_candidate,
    validate_village_reentry,
)


class VillageV23MDeltaT1Tests(unittest.TestCase):
    @staticmethod
    def _agent(*, name="Test", place_id="well", crisis=0.2):
        meaning = SimpleNamespace(
            comfort=0.04,
            social_expectation=0.0,
            resource_expectation=0.0,
            danger_expectation=0.0,
            familiarity=0.5,
        )
        agent = SimpleNamespace(
            name=name,
            body=SimpleNamespace(crisis=lambda: crisis),
            prediction_field=SimpleNamespace(places={place_id: meaning}),
        )
        return agent, meaning

    @staticmethod
    def _perception(*, tick, place_id="well", band="morning", discomfort=0.0, agents=0, resources=0):
        return SimpleNamespace(
            t=tick,
            place_id=place_id,
            band=band,
            discomfort=discomfort,
            visible_agents=[object() for _ in range(agents)],
            visible_resources=[SimpleNamespace(state="available") for _ in range(resources)],
        )

    def _reviewed_observer(self, *, theta=0.2, name="Test", place_id="well", band="morning"):
        observer = VillageCanonicalObserver(theta=theta)
        agent, meaning = self._agent(name=name, place_id=place_id)
        first = self._perception(tick=1, place_id=place_id, band=band)
        observer.capture(agent, first, 1)

        # Exact existing local one-step update under the second perception.
        meaning.comfort = 0.04 * 0.97 - 0.03
        meaning.social_expectation = 0.03
        meaning.resource_expectation = 0.04
        agent.body.crisis = lambda: 0.5
        second = self._perception(
            tick=2,
            place_id=place_id,
            band=band,
            discomfort=0.5,
            agents=1,
            resources=1,
        )
        observer.capture(agent, second, 2)
        candidate = observer.review_candidates_for(name)[-1]
        observer.submit_review(
            name,
            candidate.candidate_id,
            status="unresolved-mismatch",
            basis=(
                "bounded local place-model adjustment observed",
                "ordinary temporal change excluded for finite test window",
            ),
            assessor="test-reviewer",
            ordinary_temporal_change_excluded=True,
            boundary_or_coverage_change_excluded=True,
            unresolved_dimensions=("visible_agents",),
        )
        return observer, agent, meaning, candidate

    def test_h_below_theta_cannot_form_mdelta_request(self):
        observer, _, _, _ = self._reviewed_observer(theta=0.5)
        self.assertAlmostEqual(observer.h_snapshot("Test")["H"], 0.25)
        with self.assertRaisesRegex(ValueError, "H >= theta"):
            request_village_mdelta(
                observer,
                "Test",
                request_ref="mdelta:test:below",
                requester="test-harness",
                basis=("threshold gate",),
            )

    def test_mdelta_recomputes_h_provenance_and_invents_no_m_b_prime(self):
        observer, _, _, candidate = self._reviewed_observer(theta=0.2)
        request = request_village_mdelta(
            observer,
            "Test",
            request_ref="mdelta:test:1",
            requester="test-harness",
            basis=("reviewed unresolved H reached explicit theta",),
        )

        self.assertEqual(request.status, "m-delta-requested")
        self.assertEqual(request.next_layer, "T1")
        self.assertEqual(request.authority, "handoff-only")
        self.assertAlmostEqual(request.H_vector["visible_agents"], 0.25)
        self.assertAlmostEqual(request.H, 0.25)
        self.assertAlmostEqual(request.theta, 0.2)
        self.assertEqual(request.review_refs, (candidate.candidate_id,))
        self.assertEqual(request.context["conditions"]["place"], "well")
        self.assertEqual(request.context["conditions"]["band"], "morning")
        self.assertIsNone(request.subject_ref)
        self.assertIsNone(request.reconstructed_model_ref)
        self.assertEqual(request.xi_status, "unrecovered-relations-remain")
        self.assertFalse(hasattr(request, "xi"))

    def test_mdelta_rejects_h_mixed_across_finite_contexts(self):
        observer, agent, _, _ = self._reviewed_observer(theta=0.2)

        # Add a second place and create another reviewed unresolved window there.
        garden = SimpleNamespace(
            comfort=0.04,
            social_expectation=0.0,
            resource_expectation=0.0,
            danger_expectation=0.0,
            familiarity=0.2,
        )
        agent.prediction_field.places["garden"] = garden
        third = self._perception(tick=3, place_id="garden", band="morning")
        observer.capture(agent, third, 3)  # boundary break / new local baseline

        garden.comfort = 0.04 * 0.97 - 0.03
        garden.social_expectation = 0.03
        garden.resource_expectation = 0.04
        fourth = self._perception(
            tick=4,
            place_id="garden",
            band="morning",
            discomfort=0.5,
            agents=1,
            resources=1,
        )
        observer.capture(agent, fourth, 4)
        second_candidate = observer.review_candidates_for("Test")[-1]
        observer.submit_review(
            "Test",
            second_candidate.candidate_id,
            status="unresolved-mismatch",
            basis=("second finite context",),
            assessor="test-reviewer",
            ordinary_temporal_change_excluded=True,
            boundary_or_coverage_change_excluded=True,
            unresolved_dimensions=("visible_agents",),
        )

        with self.assertRaisesRegex(ValueError, "mixed across finite contexts"):
            request_village_mdelta(
                observer,
                "Test",
                request_ref="mdelta:test:mixed",
                requester="test-harness",
                basis=("must stay context-local",),
            )

    def _handoff(self):
        observer, _, _, _ = self._reviewed_observer(theta=0.2)
        request = request_village_mdelta(
            observer,
            "Test",
            request_ref="mdelta:test:t1",
            requester="test-harness",
            basis=("threshold and provenance reproduced",),
        )
        handoff = bind_village_mdelta_subject(
            request,
            subject_ref="M_B:Test:current",
            subject_slice={
                "sliceRole": "prediction-field-place-meaning",
                "placeId": "well",
                "comfort": 0.01,
                "socialExpectation": 0.03,
                "resourceExpectation": 0.04,
            },
            basis=("current finite self-side structure explicitly bound",),
            binder="test-binder",
        )
        return request, handoff

    def test_t1_handoff_binds_current_m_b_without_target_invention(self):
        request, handoff = self._handoff()
        self.assertIs(handoff.request, request)
        self.assertEqual(handoff.subject_role, "SILN_SELF-current-M_B")
        self.assertEqual(handoff.slice_role, "finite-subject-slice-not-whole-M_B")
        self.assertEqual(handoff.subject_ref, "M_B:Test:current")
        self.assertIsNone(handoff.reconstruction_target_ref)
        self.assertIsNone(handoff.reconstructed_model_ref)
        self.assertEqual(handoff.selection_status, "not-performed")

    def _selection(self):
        request, handoff = self._handoff()
        probe = record_village_probe(
            handoff,
            probe_ref="probe:test:1",
            condition_ref="condition:counterfactual-social-density",
            rib_section_ref="rib:probe:1",
            observed_values={
                "body_crisis": 0.4,
                "discomfort": 0.2,
                "visible_agents": 2.0,
                "visible_resources": 1.0,
            },
            interpreted_values={
                "body_crisis": 0.4,
                "discomfort": 0.2,
                "visible_agents": 0.5,
                "visible_resources": 0.25,
            },
            evidence_refs=("simulation-shadow:probe:1",),
            basis=("finite condition perturbation under current subject",),
        )
        selection = select_village_candidate(
            handoff,
            (probe,),
            selection_ref="selection:test:1",
            candidate_ref="candidate:test:1",
            decision="retain",
            criteria=("reduce reviewed visible-agent mismatch without losing selected coverage",),
            basis=("finite probe remained interpretable under selected B",),
            retained_relations=("social-density -> local social expectation",),
            valid_conditions=("well / morning / selected dimensions covered",),
            break_conditions=("selected coverage missing", "fresh mismatch remains unresolved"),
            unresolved_items=("other finite contexts untested",),
        )
        return request, handoff, probe, selection

    def test_probe_selection_and_reconstruction_are_explicit_and_shadow_only(self):
        _, handoff, probe, selection = self._selection()
        self.assertEqual(probe.authority, "probe-evidence-only")
        self.assertEqual(selection.decision, "retain")
        self.assertEqual(selection.authority, "selection-only")

        candidate_structure = {
            "kind": "finite-village-model-candidate",
            "relations": ("social-density -> local social expectation",),
            "interpreterRef": "candidate-evaluator:test:1",
        }
        proposal = propose_village_reconstruction(
            handoff,
            selection,
            proposal_ref="proposal:test:1",
            candidate_model_ref="M_B_prime:test:1",
            candidate_structure=candidate_structure,
            boundary_mode="maintain",
            basis=("retained finite relation plus explicit validity and break conditions",),
            builder="test-builder",
        )
        self.assertEqual(dict(proposal.candidate_structure), candidate_structure)
        self.assertEqual(proposal.status, "m-b-prime-proposal")
        self.assertEqual(proposal.authority, "shadow-proposal-only")
        self.assertFalse(proposal.installed)
        self.assertEqual(proposal.xi_status, "unrecovered-relations-remain")
        self.assertFalse(hasattr(proposal, "H_vector"))
        self.assertFalse(hasattr(proposal, "xi"))

        with self.assertRaisesRegex(ValueError, "must not be numericized"):
            propose_village_reconstruction(
                handoff,
                selection,
                proposal_ref="proposal:test:bad-xi",
                candidate_model_ref="M_B_prime:test:bad-xi",
                candidate_structure={"xi": 0.1, "kind": "invalid"},
                boundary_mode="maintain",
                basis=("invalid numeric xi",),
                builder="test-builder",
            )

    def test_reentry_validation_does_not_turn_fresh_e_directly_into_h(self):
        _, handoff, _, selection = self._selection()
        proposal = propose_village_reconstruction(
            handoff,
            selection,
            proposal_ref="proposal:test:reentry",
            candidate_model_ref="M_B_prime:test:reentry",
            candidate_structure={
                "kind": "finite-village-model-candidate",
                "relations": ("social-density -> local social expectation",),
            },
            boundary_mode="maintain",
            basis=("explicit retained relation",),
            builder="test-builder",
        )
        boundary = VillageBoundary(
            boundary_id=proposal.target_boundary_id,
            purpose=proposal.target_purpose,
            dimensions=proposal.target_dimensions,
            conditions=dict(proposal.target_conditions),
        )
        coefficients = {
            "body_crisis": 1.0,
            "discomfort": 1.0,
            "visible_agents": 0.25,
            "visible_resources": 0.25,
        }
        current = acquire_village_section(
            section_id="reentry:a",
            boundary=boundary,
            values={
                "body_crisis": 0.2,
                "discomfort": 0.0,
                "visible_agents": 1.0,
                "visible_resources": 1.0,
            },
        )
        same = acquire_village_section(
            section_id="reentry:b",
            boundary=boundary,
            values={
                "body_crisis": 0.2,
                "discomfort": 0.0,
                "visible_agents": 1.0,
                "visible_resources": 1.0,
            },
        )
        stable = validate_village_reentry(
            proposal,
            current,
            same,
            coefficients=coefficients,
        )
        self.assertTrue(stable.stable_for_shadow)
        self.assertEqual(stable.H_new, 0.0)
        self.assertEqual(stable.status, "stable-for-shadow-reentry")

        changed = acquire_village_section(
            section_id="reentry:c",
            boundary=boundary,
            values={
                "body_crisis": 0.2,
                "discomfort": 0.0,
                "visible_agents": 3.0,
                "visible_resources": 1.0,
            },
        )
        pending = validate_village_reentry(
            proposal,
            current,
            changed,
            coefficients=coefficients,
        )
        self.assertFalse(pending.stable_for_shadow)
        self.assertIsNone(pending.H_new)
        self.assertEqual(pending.assessment.status, "pending-assessment")

        resolved = validate_village_reentry(
            proposal,
            current,
            changed,
            coefficients=coefficients,
            assessment_status="resolved-difference",
            basis=("finite external cause accounts for fresh difference",),
            assessor="test-reviewer",
        )
        self.assertTrue(resolved.stable_for_shadow)
        self.assertEqual(resolved.H_new, 0.0)

        with self.assertRaisesRegex(ValueError, "full finite review gate"):
            validate_village_reentry(
                proposal,
                current,
                changed,
                coefficients=coefficients,
                assessment_status="unresolved-mismatch",
                basis=("must not bypass review",),
                assessor="test-reviewer",
            )


if __name__ == "__main__":
    unittest.main()
