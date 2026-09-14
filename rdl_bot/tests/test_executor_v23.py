"""Tests for the canonical reconstruction executor boundary."""

import unittest

from action_gate_v23 import ReconstructionRequest
from executor_v23 import CanonicalReconstructionExecutor
from target_planner_v23 import ReconstructionTargetPlan


def request():
    return ReconstructionRequest(
        status="canonical-reconstruction-requested",
        h_magnitude=1.0,
        theta=0.5,
        mismatch_reasons=("route",),
        assessment_reason="explicit review left mismatch unresolved",
        assessment_assessor="executor-test",
        evidence_refs=("turn-1", "turn-2", "review-1"),
    )


class CanonicalExecutorTests(unittest.TestCase):
    def test_unambiguous_plan_calls_injected_mutation(self):
        req = request()
        plan = ReconstructionTargetPlan(
            status="target-proposed",
            target_ref="node-a",
            candidate_refs=("node-a",),
            evidence_turns=(1, 2),
        )
        calls = []

        def mutate(target_ref, seen_request, seen_plan):
            calls.append((target_ref, seen_request, seen_plan))
            return "revision-result"

        execution = CanonicalReconstructionExecutor().execute(
            req, plan, mutate=mutate
        )

        self.assertEqual(execution.status, "executed-canonical-target")
        self.assertEqual(execution.target_ref, "node-a")
        self.assertEqual(execution.result, "revision-result")
        self.assertEqual(calls, [("node-a", req, plan)])

    def test_review_required_plan_does_not_mutate(self):
        req = request()
        plan = ReconstructionTargetPlan(
            status="target-review-required",
            target_ref=None,
            candidate_refs=("node-a", "node-b"),
            evidence_turns=(1, 2),
        )
        calls = []

        execution = CanonicalReconstructionExecutor().execute(
            req,
            plan,
            mutate=lambda *args: calls.append(args),
        )

        self.assertEqual(execution.status, "not-executed-target-review-required")
        self.assertIsNone(execution.target_ref)
        self.assertEqual(calls, [])

    def test_missing_target_plan_does_not_mutate(self):
        req = request()
        plan = ReconstructionTargetPlan(
            status="target-evidence-unavailable",
            target_ref=None,
            candidate_refs=(),
            evidence_turns=(1, 2),
        )
        calls = []

        CanonicalReconstructionExecutor().execute(
            req,
            plan,
            mutate=lambda *args: calls.append(args),
        )

        self.assertEqual(calls, [])

    def test_invalid_proposed_target_is_rejected(self):
        req = request()
        plan = ReconstructionTargetPlan(
            status="target-proposed",
            target_ref="node-x",
            candidate_refs=("node-a",),
            evidence_turns=(1, 2),
        )
        calls = []

        execution = CanonicalReconstructionExecutor().execute(
            req,
            plan,
            mutate=lambda *args: calls.append(args),
        )

        self.assertEqual(execution.status, "not-executed-invalid-target-plan")
        self.assertEqual(calls, [])

    def test_executor_has_no_legacy_hot_node_argument(self):
        req = request()
        plan = ReconstructionTargetPlan(
            status="target-proposed",
            target_ref="node-a",
            candidate_refs=("node-a",),
            evidence_turns=(1,),
        )

        with self.assertRaises(TypeError):
            CanonicalReconstructionExecutor().execute(
                req,
                plan,
                mutate=lambda *args: None,
                hot_node="legacy-node",
            )


if __name__ == "__main__":
    unittest.main()
