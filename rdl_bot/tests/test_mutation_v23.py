import unittest
from dataclasses import dataclass, field

from action_gate_v23 import ReconstructionRequest
from mutation_v23 import make_llm_revision_mutation
from target_planner_v23 import ReconstructionTargetPlan


@dataclass
class _Node:
    id: str
    confidence: float = 0.8
    status: str = "active"
    relations: list[str] = field(default_factory=list)


class _Graph:
    def __init__(self):
        self.nodes = {"old": _Node("old")}
        self.saved = 0
        self.relation_updates = []

    def get_by_id(self, ref):
        return self.nodes.get(ref)

    def add(self, node):
        self.nodes[node.id] = node

    def update_relations(self, ref, relations):
        self.relation_updates.append((ref, tuple(relations)))

    def save(self):
        self.saved += 1


class _LLM:
    def __init__(self, *, mode="on", available=True, revised=None):
        self.mode = mode
        self._available = available
        self.revised = revised
        self.calls = []

    def available(self):
        return self._available

    def ask_for_node_revision(self, node, user_input=None):
        self.calls.append((node.id, user_input))
        return self.revised


def _request():
    return ReconstructionRequest(
        status="canonical-reconstruction-requested",
        h_magnitude=2.0,
        theta=1.0,
        mismatch_reasons=("route:old",),
        assessment_reason="reviewed unresolved",
        assessment_assessor="unit",
        evidence_refs=("turn-1", "turn-2"),
    )


def _plan():
    return ReconstructionTargetPlan(
        status="target-proposed",
        target_ref="old",
        candidate_refs=("old",),
        evidence_turns=(1, 2),
    )


class CanonicalMutationTests(unittest.TestCase):
    def test_successful_revision_is_the_only_path_that_mutates_graph(self):
        graph = _Graph()
        replacement = _Node("new", confidence=0.6)
        llm = _LLM(revised=replacement)
        mutate = make_llm_revision_mutation(graph, llm)

        result = mutate("old", _request(), _plan())

        self.assertEqual(result.status, "mutated-with-llm-revision")
        self.assertEqual(result.replacement_ref, "new")
        self.assertEqual(graph.nodes["old"].status, "deprecated")
        self.assertAlmostEqual(graph.nodes["old"].confidence, 0.24)
        self.assertIn("old", graph.nodes["new"].relations)
        self.assertEqual(graph.relation_updates, [("old", ("new",))])
        self.assertEqual(graph.saved, 1)
        self.assertEqual(llm.calls, [("old", None)])

    def test_llm_off_does_not_mutate(self):
        graph = _Graph()
        llm = _LLM(mode="off", revised=_Node("new"))
        result = make_llm_revision_mutation(graph, llm)("old", _request(), _plan())

        self.assertEqual(result.status, "not-mutated-llm-unavailable")
        self.assertEqual(tuple(graph.nodes), ("old",))
        self.assertEqual(graph.nodes["old"].status, "active")
        self.assertEqual(graph.saved, 0)
        self.assertEqual(llm.calls, [])

    def test_unavailable_llm_does_not_mutate(self):
        graph = _Graph()
        llm = _LLM(available=False, revised=_Node("new"))
        result = make_llm_revision_mutation(graph, llm)("old", _request(), _plan())

        self.assertEqual(result.status, "not-mutated-llm-unavailable")
        self.assertEqual(tuple(graph.nodes), ("old",))
        self.assertEqual(graph.saved, 0)

    def test_failed_revision_generation_does_not_quarantine_or_deprecate(self):
        graph = _Graph()
        llm = _LLM(revised=None)
        result = make_llm_revision_mutation(graph, llm)("old", _request(), _plan())

        self.assertEqual(result.status, "not-mutated-revision-generation-failed")
        self.assertEqual(graph.nodes["old"].status, "active")
        self.assertAlmostEqual(graph.nodes["old"].confidence, 0.8)
        self.assertEqual(graph.saved, 0)

    def test_missing_target_does_not_call_llm(self):
        graph = _Graph()
        llm = _LLM(revised=_Node("new"))
        result = make_llm_revision_mutation(graph, llm)("missing", _request(), _plan())

        self.assertEqual(result.status, "not-mutated-target-missing")
        self.assertEqual(llm.calls, [])
        self.assertEqual(graph.saved, 0)


if __name__ == "__main__":
    unittest.main()
