"""Tests for canonical reconstruction target planning."""

import unittest

from action_gate_v23 import CanonicalActionGate
from authority_v23 import CanonicalLeapAuthority
from resolution_v23 import ResolutionAssessment
from runtime_v23 import V23ConversationShadow
from target_planner_v23 import CanonicalTargetPlanner
from v23_state import MismatchObservation


class _Node:
    def __init__(self, node_id, inputs, confidence=0.8):
        self.id = node_id
        self.inputs = list(inputs)
        self.relations = []
        self.status = "active"
        self.source = "manual"
        self.phase = "M_act"
        self.confidence = confidence
        self.usage_count = 0


class _Graph:
    def __init__(self):
        self.a = _Node("node-a", ["alpha"])
        self.b = _Node("node-b", ["beta"])
        self.nodes = {self.a.id: self.a, self.b.id: self.b}

    def search(self, text):
        if text == "alpha":
            return self.a, "exact", self.a
        if text == "beta":
            return self.b, "exact", self.b
        if text.startswith("alp"):
            return self.a, "partial", self.a
        return None, "miss", None


def make_request(*evidence_refs):
    authority = CanonicalLeapAuthority(theta=0.5)
    assessment = ResolutionAssessment.unresolved_case(
        reason="explicit finite review left mismatch unresolved",
        assessor="target-planner-test",
        evidence_refs=evidence_refs,
    )
    observation = authority.observe_mismatch(
        MismatchObservation(values={"route": 1.0}),
        assessment=assessment,
    )
    return CanonicalActionGate().request(observation)


class CanonicalTargetPlannerTests(unittest.TestCase):
    def test_partial_evidence_does_not_rebase_on_available_later_evaluator(self):
        graph = _Graph()
        shadow = V23ConversationShadow(index_offset=1)
        shadow.capture_input("alpha", graph)  # only turn-2 is available
        request = make_request("turn-1", "turn-2")

        plan = CanonicalTargetPlanner().plan(request, shadow=shadow)

        self.assertEqual(plan.status, "target-evidence-unavailable")
        self.assertIsNone(plan.target_ref)
        self.assertEqual(plan.candidate_refs, ())

    def test_same_frozen_candidate_is_proposed(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("alpha", graph)
        shadow.capture_input("alp", graph)
        request = make_request("turn-1", "turn-2", "review-1")

        plan = CanonicalTargetPlanner().plan(request, shadow=shadow)

        self.assertEqual(plan.status, "target-proposed")
        self.assertEqual(plan.target_ref, "node-a")
        self.assertEqual(plan.candidate_refs, ("node-a",))
        self.assertEqual(plan.evidence_turns, (1, 2))

    def test_conflicting_canonical_candidates_require_review(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("alpha", graph)
        shadow.capture_input("beta", graph)
        request = make_request("turn-1", "turn-2")

        plan = CanonicalTargetPlanner().plan(request, shadow=shadow)

        self.assertEqual(plan.status, "target-review-required")
        self.assertIsNone(plan.target_ref)
        self.assertEqual(plan.candidate_refs, ("node-a", "node-b"))

    def test_missing_candidate_does_not_invent_target(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("unknown", graph)
        shadow.capture_input("still-unknown", graph)
        request = make_request("turn-1", "turn-2")

        plan = CanonicalTargetPlanner().plan(request, shadow=shadow)

        self.assertEqual(plan.status, "target-evidence-unavailable")
        self.assertIsNone(plan.target_ref)
        self.assertEqual(plan.candidate_refs, ())

    def test_non_turn_review_refs_are_not_used_as_targets(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("alpha", graph)
        request = make_request("review-1")

        plan = CanonicalTargetPlanner().plan(request, shadow=shadow)

        self.assertEqual(plan.status, "target-evidence-unavailable")
        self.assertEqual(plan.evidence_turns, ())

    def test_planner_api_has_no_legacy_hot_node_input(self):
        graph = _Graph()
        shadow = V23ConversationShadow()
        shadow.capture_input("alpha", graph)
        request = make_request("turn-1")
        planner = CanonicalTargetPlanner()

        with self.assertRaises(TypeError):
            planner.plan(request, shadow=shadow, hot_node="legacy-node")


if __name__ == "__main__":
    unittest.main()
