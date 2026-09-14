"""Tests for the opt-in canonical migration session."""

import unittest

from migration_session_v23 import CanonicalMigrationSession


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
        self.nodes = {self.a.id: self.a}

    def search(self, text):
        if text == "alpha":
            return self.a, "exact", self.a
        if text == "alp":
            return self.a, "partial", self.a
        return None, "miss", None


class CanonicalMigrationSessionTests(unittest.TestCase):
    def test_wrapper_preserves_legacy_responses(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        calls = []

        def legacy(*args):
            calls.append(args[0])
            return f"legacy:{args[0]}", "node-a"

        first = session.respond("alpha", graph, None, None, None, [], None, legacy_respond=legacy)
        second = session.respond("alp", graph, None, None, None, [], None, legacy_respond=legacy)

        self.assertEqual(first, ("legacy:alpha", "node-a"))
        self.assertEqual(second, ("legacy:alp", "node-a"))
        self.assertEqual(calls, ["alpha", "alp"])

    def test_nonzero_adjacent_turn_mismatch_becomes_pending_only(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        legacy = lambda *args: ("answer", "node-a")

        session.respond("alpha", graph, None, None, None, [], None, legacy_respond=legacy)
        session.respond("alp", graph, None, None, None, [], None, legacy_respond=legacy)

        self.assertEqual(len(session.assessments), 1)
        self.assertEqual(session.assessments[0].status, "pending-review")
        self.assertEqual(len(session.pending_records), 1)
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)

    def test_session_never_auto_executes_pending_record(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        legacy = lambda *args: ("answer", "node-a")
        calls = []

        session.respond("alpha", graph, None, None, None, [], None, legacy_respond=legacy)
        session.respond("alp", graph, None, None, None, [], None, legacy_respond=legacy)

        self.assertEqual(calls, [])
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)

    def test_explicit_review_can_enter_canonical_pipeline(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        legacy = lambda *args: ("answer", "node-a")
        session.respond("alpha", graph, None, None, None, [], None, legacy_respond=legacy)
        session.respond("alp", graph, None, None, None, [], None, legacy_respond=legacy)
        record = session.pending_records[0]
        calls = []

        result = session.review_and_execute(
            record,
            reason="explicit finite review left the mismatch unresolved",
            assessor="session-test",
            evidence_refs=("review-1",),
            mutate=lambda target, request, plan: calls.append(target) or "ok",
        )

        self.assertEqual(result.status, "executed-canonical-target")
        self.assertEqual(calls, ["node-a"])

    def test_foreign_record_cannot_be_reviewed(self):
        first = CanonicalMigrationSession(theta=0.5)
        second = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        legacy = lambda *args: ("answer", "node-a")
        first.respond("alpha", graph, None, None, None, [], None, legacy_respond=legacy)
        first.respond("alp", graph, None, None, None, [], None, legacy_respond=legacy)
        foreign = first.pending_records[0]

        with self.assertRaises(ValueError):
            second.review_and_execute(
                foreign,
                reason="invalid cross-session review",
                assessor="session-test",
                mutate=lambda *args: None,
            )


if __name__ == "__main__":
    unittest.main()
