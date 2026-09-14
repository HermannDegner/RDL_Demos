import os
import tempfile
import unittest
from unittest import mock

import main
from cli_v23_authority import install_canonical_action_authority
from h_state import HState
from llm_bridge import LLMBridge
from llm_trust import LLMTrust
from node_graph import Node, NodeGraph
from sfo_profile import AI_SFO


class _StubLLM(LLMBridge):
    def __init__(self, sfo):
        super().__init__(sfo)
        self.mode = "on"
        self.revision_calls = []

    def available(self):
        return True

    def ask_for_node_revision(self, hot_node, user_input=None):
        self.revision_calls.append((hot_node.id, user_input))
        return Node(
            inputs=list(hot_node.inputs),
            rdl_type="修正",
            response="canonical-authority-mode-should-not-call-this-via-legacy",
            source="llm_learned",
        )


class CanonicalAuthorityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
        env.start()
        self.addCleanup(env.stop)

    def test_real_respond_does_not_execute_legacy_hot_node_correction_in_authority_mode(self):
        graph = NodeGraph(os.path.join(self.tmpdir.name, "graph.json"))
        node = Node(inputs=["こんにちは"], response="やあ", spatial_tag="人")
        graph.add(node)
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny(node.id)

        sfo = AI_SFO()
        llm = _StubLLM(sfo)
        trust = LLMTrust()
        unresolved_queue = []
        original = install_canonical_action_authority(main)
        self.addCleanup(setattr, main, "_decide_leap", original)

        response, node_id = main.respond(
            "こんにちは",
            graph,
            h,
            llm,
            sfo,
            unresolved_queue,
            trust,
        )

        self.assertEqual(response, "やあ")
        self.assertEqual(node_id, node.id)
        self.assertEqual(node.status, "active")
        self.assertEqual(llm.revision_calls, [])
        self.assertEqual(tuple(graph.nodes), (node.id,))

    def test_install_is_process_local_and_restorable(self):
        original = main._decide_leap
        returned = install_canonical_action_authority(main)
        self.assertIs(returned, original)
        self.assertIsNone(main._decide_leap(HState(), NodeGraph(os.path.join(self.tmpdir.name, "g.json")), "miss", None, "x"))
        main._decide_leap = original
        self.assertIs(main._decide_leap, original)


if __name__ == "__main__":
    unittest.main()
