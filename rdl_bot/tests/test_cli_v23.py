"""Tests for the opt-in v2.3 CLI entrypoint."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from cli_v23 import install_shadow_session
from migration_session_v23 import CanonicalMigrationSession
from persistence_v23 import load_session


class _Node:
    def __init__(self, node_id="node-a"):
        self.id = node_id
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
        self.saved = 0
        self.relation_updates = []

    def search(self, text):
        if text == "alpha":
            return self.node, "exact", self.node
        if text == "alp":
            return self.node, "partial", self.node
        return None, "miss", None

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

    def ask_for_canonical_node_revision(self, node, request):
        self.calls.append((node.id, request))
        return self.revised

    def ask_for_node_revision(self, node, user_input=None):
        raise AssertionError("canonical CLI must not use legacy H/deny revision")


class _LegacyMain:
    def __init__(self):
        self.calls = []
        self.command_calls = []

        def respond(user_input, graph, h, llm, sfo_profile, unresolved_queue, llm_trust):
            self.calls.append(user_input)
            return f"legacy:{user_input}", "node-a"

        def handle_command(cmd, *args, **kwargs):
            self.command_calls.append(cmd)
            return True

        self.respond = respond
        self.handle_command = handle_command


def installed_pending_session(theta=0.5):
    legacy = _LegacyMain()
    session = install_shadow_session(
        legacy,
        session=CanonicalMigrationSession(theta=theta),
    )
    graph = _Graph()
    legacy.respond("alpha", graph, None, None, None, [], None)
    legacy.respond("alp", graph, None, None, None, [], None)
    return legacy, session, graph


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
        legacy, session, _ = installed_pending_session()

        self.assertEqual(legacy.calls, ["alpha", "alp"])
        self.assertEqual(len(session.pending_records), 1)
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)
        self.assertFalse(session.controller.authority.should_reconstruct)

    def test_v23_status_is_read_only_and_not_delegated(self):
        legacy, session, _ = installed_pending_session()
        before_h = session.controller.authority.h_magnitude
        before_pending = len(session.pending_records)
        output = io.StringIO()

        with redirect_stdout(output):
            handled = legacy.handle_command("/v23", None, None)

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, [])
        self.assertEqual(session.controller.authority.h_magnitude, before_h)
        self.assertEqual(len(session.pending_records), before_pending)
        self.assertIn("pending=1", output.getvalue())

    def test_explicit_resolve_review_closes_pending_without_H(self):
        legacy, session, graph = installed_pending_session()
        before_nodes = tuple(graph.nodes)
        output = io.StringIO()

        with redirect_stdout(output):
            handled = legacy.handle_command(
                "/v23 resolve routing difference is accounted for",
                None,
            )

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, [])
        self.assertEqual(len(session.pending_records), 0)
        self.assertEqual(len(session.reviews), 1)
        self.assertEqual(session.reviews[0].disposition, "resolved")
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)
        self.assertEqual(tuple(graph.nodes), before_nodes)
        self.assertIn("resolved", output.getvalue())

    def test_explicit_unresolved_review_updates_canonical_H_only(self):
        legacy, session, graph = installed_pending_session(theta=0.5)
        before_nodes = tuple(graph.nodes)
        output = io.StringIO()

        with redirect_stdout(output):
            handled = legacy.handle_command(
                "/v23 unresolved finite review cannot account for mismatch",
                None,
            )

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, [])
        self.assertEqual(len(session.pending_records), 0)
        self.assertEqual(session.reviews[0].disposition, "unresolved")
        self.assertGreater(session.controller.authority.h_magnitude, 0.0)
        self.assertTrue(session.controller.authority.should_reconstruct)
        self.assertEqual(tuple(graph.nodes), before_nodes)
        self.assertIn("node graph mutationは実行しません", output.getvalue())

    def test_plan_after_unresolved_review_is_dry_run_only(self):
        legacy, session, graph = installed_pending_session(theta=0.5)
        before_nodes = tuple(graph.nodes)
        legacy.handle_command(
            "/v23 unresolved finite review cannot account for mismatch",
            None,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handled = legacy.handle_command("/v23 plan", None)

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, [])
        self.assertEqual(tuple(graph.nodes), before_nodes)
        self.assertIn("status=target-proposed", output.getvalue())
        self.assertIn("target=node-a", output.getvalue())
        self.assertIn("dry-run only", output.getvalue())

    def test_execute_mutates_only_after_explicit_unresolved_review(self):
        legacy, session, graph = installed_pending_session(theta=0.5)
        llm = _LLM(revised=_Node("node-b"))
        legacy.handle_command(
            "/v23 unresolved reviewed canonical mismatch",
            llm,
            graph,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handled = legacy.handle_command("/v23 execute", llm, graph)

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, [])
        self.assertIn("node-b", graph.nodes)
        self.assertEqual(graph.nodes["node-a"].status, "deprecated")
        self.assertIn("node-a", graph.nodes["node-b"].relations)
        self.assertEqual(len(session.executions), 1)
        self.assertTrue(session.executions[0].mutated)
        self.assertIn("mutation=mutated-with-llm-revision", output.getvalue())

    def test_successful_execute_is_one_shot_for_same_review(self):
        legacy, session, graph = installed_pending_session(theta=0.5)
        llm = _LLM(revised=_Node("node-b"))
        legacy.handle_command("/v23 unresolved reviewed mismatch", llm, graph)
        legacy.handle_command("/v23 execute", llm, graph)
        calls_after_first = list(llm.calls)
        output = io.StringIO()

        with redirect_stdout(output):
            legacy.handle_command("/v23 execute", llm, graph)

        self.assertEqual(llm.calls, calls_after_first)
        self.assertEqual(len(session.executions), 1)
        self.assertIn("already-executed-canonical-review", output.getvalue())

    def test_llm_off_execute_is_non_mutating_and_retryable(self):
        legacy, session, graph = installed_pending_session(theta=0.5)
        llm = _LLM(mode="off", revised=_Node("node-b"))
        legacy.handle_command("/v23 unresolved reviewed mismatch", llm, graph)
        legacy.handle_command("/v23 execute", llm, graph)

        self.assertEqual(graph.nodes["node-a"].status, "active")
        self.assertNotIn("node-b", graph.nodes)
        self.assertEqual(len(session.executions), 1)
        self.assertFalse(session.executions[0].mutated)

        llm.mode = "on"
        legacy.handle_command("/v23 execute", llm, graph)
        self.assertIn("node-b", graph.nodes)
        self.assertTrue(session.executions[-1].mutated)

    def test_plan_without_unresolved_review_does_not_create_one(self):
        legacy, session, _ = installed_pending_session(theta=0.5)
        output = io.StringIO()

        with redirect_stdout(output):
            legacy.handle_command("/v23 plan", None)

        self.assertEqual(len(session.pending_records), 1)
        self.assertEqual(len(session.reviews), 0)
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)
        self.assertIn("status=no-unresolved-review", output.getvalue())

    def test_review_reason_is_required(self):
        legacy, session, _ = installed_pending_session()
        output = io.StringIO()

        with redirect_stdout(output):
            legacy.handle_command("/v23 unresolved", None)

        self.assertEqual(len(session.pending_records), 1)
        self.assertEqual(len(session.reviews), 0)
        self.assertEqual(session.controller.authority.h_magnitude, 0.0)
        self.assertIn("review理由が必要", output.getvalue())

    def test_state_path_persists_and_restart_continues_monotonic_turn_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v23_shadow.json")
            graph = _Graph()
            first_legacy = _LegacyMain()
            first_session = install_shadow_session(
                first_legacy,
                session=CanonicalMigrationSession(theta=0.5),
                state_path=path,
            )
            first_legacy.respond("alpha", graph, None, None, None, [], None)
            first_legacy.respond("alp", graph, None, None, None, [], None)

            self.assertTrue(os.path.exists(path))
            self.assertEqual(first_session.shadow.last_assigned_index, 2)
            self.assertEqual(len(load_session(path).pending_records), 1)

            second_legacy = _LegacyMain()
            restored = install_shadow_session(second_legacy, state_path=path)
            self.assertEqual(restored.shadow.index_offset, 2)
            self.assertEqual(len(restored.pending_records), 1)

            second_legacy.respond("alpha", graph, None, None, None, [], None)
            self.assertEqual(restored.shadow.available_turn_indices, (3,))
            self.assertEqual(len(restored.assessments), 1)

            second_legacy.respond("alp", graph, None, None, None, [], None)
            self.assertEqual(restored.shadow.available_turn_indices, (3, 4))
            self.assertEqual((restored.assessments[-1].earlier_index, restored.assessments[-1].later_index), (3, 4))

    def test_review_command_persists_canonical_H_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v23_shadow.json")
            graph = _Graph()
            legacy = _LegacyMain()
            install_shadow_session(
                legacy,
                session=CanonicalMigrationSession(theta=0.5),
                state_path=path,
            )
            legacy.respond("alpha", graph, None, None, None, [], None)
            legacy.respond("alp", graph, None, None, None, [], None)

            legacy.handle_command("/v23 unresolved reviewed mismatch remains unresolved")
            restored = load_session(path)

            self.assertEqual(len(restored.reviews), 1)
            self.assertEqual(restored.reviews[0].disposition, "unresolved")
            self.assertGreater(restored.controller.authority.h_magnitude, 0.0)
            self.assertTrue(restored.controller.authority.should_reconstruct)

    def test_successful_execution_audit_persists_and_blocks_restart_reexecution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v23_shadow.json")
            graph = _Graph()
            legacy = _LegacyMain()
            session = install_shadow_session(
                legacy,
                session=CanonicalMigrationSession(theta=0.5),
                state_path=path,
            )
            llm = _LLM(revised=_Node("node-b"))
            legacy.respond("alpha", graph, None, None, None, [], None)
            legacy.respond("alp", graph, None, None, None, [], None)
            legacy.handle_command("/v23 unresolved reviewed mismatch", llm, graph)
            legacy.handle_command("/v23 execute", llm, graph)

            self.assertTrue(session.executions[-1].mutated)
            restored = load_session(path)
            self.assertEqual(len(restored.executions), 1)
            self.assertTrue(restored.executions[0].mutated)

            second_legacy = _LegacyMain()
            restored = install_shadow_session(second_legacy, state_path=path)
            retry_llm = _LLM(revised=_Node("node-c"))
            output = io.StringIO()
            with redirect_stdout(output):
                second_legacy.handle_command("/v23 execute", retry_llm, graph)
            self.assertEqual(retry_llm.calls, [])
            self.assertIn("already-executed-canonical-review", output.getvalue())

    def test_non_v23_command_is_delegated_unchanged(self):
        legacy = _LegacyMain()
        install_shadow_session(legacy)

        handled = legacy.handle_command("/graph", "sentinel")

        self.assertTrue(handled)
        self.assertEqual(legacy.command_calls, ["/graph"])

    def test_default_legacy_object_is_not_modified_until_install(self):
        legacy = _LegacyMain()
        original = legacy.respond
        original_command = legacy.handle_command

        result = legacy.respond("alpha", _Graph(), None, None, None, [], None)

        self.assertEqual(result, ("legacy:alpha", "node-a"))
        self.assertIs(legacy.respond, original)
        self.assertIs(legacy.handle_command, original_command)

    def test_wrapper_has_no_hot_node_side_channel(self):
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
