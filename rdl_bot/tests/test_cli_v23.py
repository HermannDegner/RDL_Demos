"""Tests for the opt-in v2.3 shadow CLI entrypoint."""

import unittest

from cli_v23 import install_shadow_session
from migration_session_v23 import CanonicalMigrationSession


class _Node:
    def __init__(self):
        self.id = "node-a"
        self.inputs = ["alpha"]
        self.relations = []
        self.status = "active"
        self.source = "manual"
        self.phase = "M_act"
        self.confidence = 0.8
        self.usage_count = 0


class _Graph:
    def __init__(self):
        self.node = _Node()
        self.nodes = {self.node.id: self.node}

    def search(self, text):
        if text == "alpha":
            return self.node, "exact", self.node
        if text == "alp":
            return self.node, "partial", self.node
        return None, "miss", None


class _LegacyMain:
    def __init__(self):
        self.calls = []

        def respond(user_input, graph, h, llm, sfo_profile, unresolved_queue, llm_trust):
            self.calls.append(user_input)
            return f"legacy:{user_input}", "node-a"

        self.respond = respond


class V23ShadowCliTests(unittest.TestCase):
    def test_install_preserves_legacy_response_and_call_count(self):
        legacy = _LegacyMain()
        session = install_shadow_session(
            legacy,
            session=CanonicalMigrationSession(theta=0.5),
        )
        graph = _Graph()

        result = legacy.respond("alpha", graph, None, None, None, [], None)

        self.assertEqual(result, ("legacy:alpha", "node-a"))
        self.assertEqual(legacy.calls, ["alpha"])
        self.assertEqual(len(session.shadow.turns), 1)

    def test_second_turn_forms_pending_without_auto_H_or_mutation(self):
        legacy = _LegacyMain()
        session = install_shadow_session(
            legacy,
            session=CanonicalMigrationSession(theta=0.5),
        )
        graph = _Graph()

        legacy.respond("alpha", graph, None, None, None, [], None)
        legacy.respond("alp", graph, None, None, None, [], None)

        self.assertEqual(legacy.calls, ["alpha", "alp"])
        self.assertEqual(len(session.pending_records), 1)
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)
        self.assertFalse(session.controller.authority.should_reconstruct)

    def test_default_legacy_object_is_not_modified_until_install(self):
        legacy = _LegacyMain()
        original = legacy.respond

        result = legacy.respond("alpha", _Graph(), None, None, None, [], None)

        self.assertEqual(result, ("legacy:alpha", "node-a"))
        self.assertIs(legacy.respond, original)

    def test_wrapper_has_no_review_or_hot_node_side_channel(self):
        legacy = _LegacyMain()
        install_shadow_session(legacy)

        with self.assertRaises(TypeError):
            legacy.respond(
                "alpha",
                _Graph(),
                None,
                None,
                None,
                [],
                None,
                hot_node="legacy-node",
            )


if __name__ == "__main__":
    unittest.main()
