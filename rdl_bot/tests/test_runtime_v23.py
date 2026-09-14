import unittest
from dataclasses import dataclass, field

from runtime_v23 import V23ConversationShadow, frozen_graph_model_ref, respond_with_shadow


@dataclass
class DummyNode:
    id: str
    confidence: float = 0.8
    status: str = "active"
    phase: str = "M_act"
    usage_count: int = 1
    inputs: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    source: str = "manual"


class DummyGraph:
    def __init__(self):
        self.nodes = {
            "known": DummyNode("known", confidence=0.8, inputs=["known"]),
            "other": DummyNode("other", confidence=0.8, inputs=["other"]),
            "near": DummyNode("near", confidence=0.4, inputs=["near"]),
        }

    def search(self, text):
        if text == "known":
            return self.nodes["known"], "exact", self.nodes["known"]
        if text == "other":
            return self.nodes["other"], "exact", self.nodes["other"]
        if text.startswith("kn"):
            return self.nodes["known"], "partial", self.nodes["known"]
        return None, "miss", self.nodes["near"]


class ShadowRuntimeTests(unittest.TestCase):
    def test_wrapper_preserves_legacy_response_exactly(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        calls = []

        def legacy(*args):
            calls.append(args)
            return "legacy-response", "known"

        result = respond_with_shadow(
            "known", graph, object(), object(), object(), [], object(),
            shadow=shadow,
            legacy_respond=legacy,
        )

        self.assertEqual(result, ("legacy-response", "known"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "known")

    def test_real_turn_is_acquired_as_finite_sections(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()

        respond_with_shadow(
            "known", graph, None, None, None, [], None,
            shadow=shadow,
            legacy_respond=lambda *args: ("answer", "known"),
        )

        self.assertEqual(len(shadow.turns), 1)
        turn = shadow.turns[0]
        self.assertEqual(turn.input_section.role, "user-input")
        self.assertEqual(turn.input_section.payload["text"], "known")
        self.assertEqual(turn.input_state.values["exact"], 1.0)
        self.assertEqual(turn.input_state.values["route:known"], 1.0)
        self.assertEqual(turn.response_section.role, "bot-response")
        self.assertEqual(turn.response_section.payload["text"], "answer")
        self.assertEqual(turn.response_node_id, "known")

    def test_raw_text_is_not_the_section_or_F(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        turn = shadow.capture_input("known", graph)

        self.assertNotEqual(turn.input_section, "known")
        self.assertNotEqual(turn.input_state, turn.input_section)
        self.assertEqual(turn.input_section.payload["text"], "known")

    def test_same_frozen_graph_allows_strict_input_comparison(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        first = shadow.capture_input("known", graph)
        shadow.capture_response(first, "a", "known")
        second = shadow.capture_input("unknown", graph)
        shadow.capture_response(second, "b", "__none__")

        mismatch = shadow.compare_inputs(1, 2)
        self.assertIsNotNone(mismatch)
        self.assertGreater(mismatch.magnitude, 0.0)
        self.assertIn("exact", mismatch.reasons)
        self.assertIn("miss", mismatch.reasons)

    def test_same_match_class_and_confidence_still_preserve_route_change(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        shadow.capture_input("known", graph)
        shadow.capture_input("other", graph)

        mismatch = shadow.replay_later_under_earlier_model(1, 2)

        self.assertIsNotNone(mismatch)
        self.assertEqual(mismatch.values["exact"], 0.0)
        self.assertEqual(mismatch.values["candidate_confidence"], 0.0)
        self.assertEqual(mismatch.values["route:known"], 1.0)
        self.assertEqual(mismatch.values["route:other"], 1.0)
        self.assertIn("route:known", mismatch.reasons)
        self.assertIn("route:other", mismatch.reasons)

    def test_live_graph_change_breaks_strict_comparison_but_not_frozen_replay(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        first = shadow.capture_input("known", graph)
        shadow.capture_response(first, "a", "known")

        graph.nodes["known"].confidence = 0.2
        graph.nodes["near"].confidence = 0.1
        second = shadow.capture_input("unknown", graph)
        shadow.capture_response(second, "b", "__none__")

        self.assertNotEqual(shadow.turns[0].model_ref, shadow.turns[1].model_ref)
        self.assertIsNone(shadow.compare_inputs(1, 2))

        mismatch = shadow.replay_later_under_earlier_model(1, 2)
        self.assertIsNotNone(mismatch)
        self.assertGreater(mismatch.magnitude, 0.0)
        # F' was formed with the earlier snapshot, where nearest confidence was 0.4.
        self.assertAlmostEqual(mismatch.values["candidate_confidence"], 0.4)

    def test_frozen_evaluator_does_not_follow_live_mutation(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow()
        first = shadow.capture_input("known", graph)
        graph.nodes["known"].confidence = 0.1

        replayed = first.model_evaluator.interpret(first.input_section)

        self.assertAlmostEqual(replayed.values["candidate_confidence"], 0.8)
        self.assertAlmostEqual(first.input_state.values["candidate_confidence"], 0.8)

    def test_boundary_change_prevents_replay_E(self):
        graph = DummyGraph()
        shadow = V23ConversationShadow(boundary_id="B:one")
        shadow.capture_input("known", graph)
        shadow.boundary_id = "B:two"
        shadow.capture_input("unknown", graph)

        self.assertIsNone(shadow.replay_later_under_earlier_model(1, 2))

    def test_model_fingerprint_is_deterministic_for_same_finite_state(self):
        first = DummyGraph()
        second = DummyGraph()
        self.assertEqual(frozen_graph_model_ref(first), frozen_graph_model_ref(second))

    def test_model_fingerprint_changes_when_routing_inputs_change(self):
        first = DummyGraph()
        second = DummyGraph()
        second.nodes["known"].inputs = ["different"]
        self.assertNotEqual(frozen_graph_model_ref(first), frozen_graph_model_ref(second))


if __name__ == "__main__":
    unittest.main()
