import os
import tempfile
import unittest
from dataclasses import dataclass, field

from migration_session_v23 import CanonicalMigrationSession
from persistence_v23 import load_session, save_session, session_from_dict, session_to_dict


@dataclass
class _Node:
    id: str
    confidence: float = 0.8
    status: str = "active"
    phase: str = "M_act"
    usage_count: int = 1
    inputs: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    source: str = "manual"


class _Graph:
    def __init__(self):
        self.nodes = {
            "alpha": _Node("alpha", inputs=["alpha"]),
            "beta": _Node("beta", inputs=["beta"]),
        }

    def search(self, text):
        if text in self.nodes:
            node = self.nodes[text]
            return node, "exact", node
        return None, "miss", self.nodes["alpha"]


def _legacy_respond(user_input, graph, *_args):
    node, match_type, nearest = graph.search(user_input)
    candidate = node if node is not None else nearest
    return f"legacy:{user_input}:{match_type}", candidate.id if candidate else "__none__"


def _respond(session, text, graph):
    return session.respond(
        text,
        graph,
        None,
        None,
        None,
        [],
        None,
        legacy_respond=_legacy_respond,
    )


class CanonicalPersistenceTests(unittest.TestCase):
    def test_pending_and_turn_offset_survive_round_trip_without_old_frozen_evaluator(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        _respond(session, "alpha", graph)
        _respond(session, "beta", graph)

        self.assertEqual(len(session.pending_records), 1)
        restored = session_from_dict(session_to_dict(session))

        self.assertEqual(len(restored.pending_records), 1)
        self.assertEqual(restored.shadow.turns, [])
        self.assertEqual(restored.shadow.index_offset, 2)
        self.assertEqual(restored.shadow.last_assigned_index, 2)

        # The first post-restart turn starts a fresh comparison window; no
        # cross-restart E is manufactured from an absent frozen evaluator.
        _respond(restored, "alpha", graph)
        self.assertEqual(restored.shadow.available_turn_indices, (3,))
        self.assertEqual(len(restored.assessments), 1)

        _respond(restored, "beta", graph)
        self.assertEqual(restored.shadow.available_turn_indices, (3, 4))
        self.assertEqual((restored.assessments[-1].earlier_index, restored.assessments[-1].later_index), (3, 4))

    def test_canonical_h_and_review_audit_are_restored_exactly(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        _respond(session, "alpha", graph)
        _respond(session, "beta", graph)
        record = session.pending_records[0]
        observation = session.review_unresolved(
            record,
            reason="review confirmed unresolved route mismatch",
            assessor="unit-reviewer",
            evidence_refs=("review:1",),
        )
        before = session.controller.authority.h_snapshot()
        self.assertTrue(observation.should_reconstruct)

        restored = session_from_dict(session_to_dict(session))

        self.assertEqual(restored.controller.authority.h_snapshot(), before)
        self.assertEqual(restored.controller.authority.h_magnitude, session.controller.authority.h_magnitude)
        self.assertEqual(len(restored.reviews), 1)
        self.assertEqual(restored.reviews[0].assessment.reason, "review confirmed unresolved route mismatch")
        self.assertEqual(restored.reviews[0].assessment.assessor, "unit-reviewer")
        self.assertIn("review:1", restored.reviews[0].assessment.evidence_refs)

    def test_restored_old_review_cannot_invent_target_without_old_frozen_evidence(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        _respond(session, "alpha", graph)
        _respond(session, "beta", graph)
        record = session.pending_records[0]
        session.review_unresolved(
            record,
            reason="confirmed unresolved",
            assessor="unit-reviewer",
        )

        restored = session_from_dict(session_to_dict(session))
        preview = restored.preview_latest_reconstruction()

        self.assertEqual(preview.status, "target-evidence-unavailable")
        self.assertIsNotNone(preview.request)
        self.assertIsNotNone(preview.plan)
        self.assertIsNone(preview.plan.target_ref)

    def test_file_save_and_load_are_atomic_and_json_based(self):
        session = CanonicalMigrationSession(theta=0.5)
        graph = _Graph()
        _respond(session, "alpha", graph)
        _respond(session, "beta", graph)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state", "v23_shadow.json")
            save_session(path, session)
            restored = load_session(path)

            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".tmp"))
            self.assertEqual(len(restored.pending_records), 1)
            self.assertEqual(restored.shadow.index_offset, 2)

    def test_corrupt_h_snapshot_is_rejected(self):
        session = CanonicalMigrationSession()
        payload = session_to_dict(session)
        payload["h_snapshot"] = {"bad": -1.0}
        with self.assertRaises(ValueError):
            session_from_dict(payload)


if __name__ == "__main__":
    unittest.main()
