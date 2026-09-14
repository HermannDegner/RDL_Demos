"""End-to-end tests for the non-authoritative canonical pipeline."""

import unittest

from authority_v23 import CanonicalLeapAuthority
from canonical_runtime_v23 import CanonicalRuntimeController
from pipeline_v23 import CanonicalReconstructionPipeline
from runtime_v23 import V23ConversationShadow


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
        if text == "alp":
            return self.a, "partial", self.a
        if text == "beta":
            return self.b, "exact", self.b
        return None, "miss", None


def setup_pair(second="alp", theta=0.5):
    graph = _Graph()
    shadow = V23ConversationShadow()
    shadow.capture_input("alpha", graph)
    shadow.capture_input(second, graph)
    controller = CanonicalRuntimeController(CanonicalLeapAuthority(theta=theta))
    record = controller.assess_pair(shadow=shadow, earlier_index=1, later_index=2)
    return shadow, controller, record


class CanonicalPipelineTests(unittest.TestCase):
    def test_pending_record_executes_only_after_explicit_review(self):
        shadow, controller, record = setup_pair()
        self.assertEqual(record.status, "pending-review")
        calls = []

        result = CanonicalReconstructionPipeline(controller).review_and_execute(
            record,
            shadow=shadow,
            reason="explicit finite review left the mismatch unresolved",
            assessor="pipeline-test",
            evidence_refs=("review-1",),
            mutate=lambda target, request, plan: calls.append((target, request, plan)) or "ok",
        )

        self.assertEqual(result.status, "executed-canonical-target")
        self.assertEqual(result.plan.target_ref, "node-a")
        self.assertEqual(result.execution.result, "ok")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "node-a")

    def test_below_theta_review_does_not_execute(self):
        shadow, controller, record = setup_pair(theta=10.0)
        calls = []

        result = CanonicalReconstructionPipeline(controller).review_and_execute(
            record,
            shadow=shadow,
            reason="reviewed but magnitude remains below threshold",
            assessor="pipeline-test",
            mutate=lambda *args: calls.append(args),
        )

        self.assertEqual(result.status, "reviewed-below-reconstruction-threshold")
        self.assertEqual(calls, [])

    def test_ambiguous_targets_stop_before_mutation(self):
        shadow, controller, record = setup_pair(second="beta")
        calls = []

        result = CanonicalReconstructionPipeline(controller).review_and_execute(
            record,
            shadow=shadow,
            reason="mismatch remains unresolved after explicit review",
            assessor="pipeline-test",
            mutate=lambda *args: calls.append(args),
        )

        self.assertEqual(result.status, "target-review-required")
        self.assertIsNone(result.plan.target_ref)
        self.assertEqual(calls, [])

    def test_resolved_record_cannot_enter_review_pipeline(self):
        shadow, controller, record = setup_pair(second="alpha")
        self.assertEqual(record.status, "resolved-observed")

        with self.assertRaises(ValueError):
            CanonicalReconstructionPipeline(controller).review_and_execute(
                record,
                shadow=shadow,
                reason="invalid",
                assessor="pipeline-test",
                mutate=lambda *args: None,
            )

    def test_pipeline_api_has_no_legacy_hot_node_input(self):
        shadow, controller, record = setup_pair()

        with self.assertRaises(TypeError):
            CanonicalReconstructionPipeline(controller).review_and_execute(
                record,
                shadow=shadow,
                reason="explicit review",
                assessor="pipeline-test",
                mutate=lambda *args: None,
                hot_node="legacy-node",
            )


if __name__ == "__main__":
    unittest.main()
