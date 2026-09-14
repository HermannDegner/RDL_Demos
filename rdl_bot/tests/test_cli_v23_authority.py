import unittest

import cli_v23_authority


class _Node:
    def __init__(self, *, kappa=0.5):
        self.confidence = 0.2
        self._kappa = kappa
        self.reinforce_calls = []

    def kappa(self):
        return self._kappa

    def reinforce(self, rate):
        self.reinforce_calls.append(rate)
        self.confidence += rate


class _LegacyModule:
    def __init__(self):
        self.calls = []
        self.reinforce_calls = []

        def decide(*args, **kwargs):
            self.calls.append((args, kwargs))
            return "legacy-decision"

        def reinforce(node, legacy_h, pressure, base_rate):
            self.reinforce_calls.append((node, legacy_h, pressure, base_rate))
            node.reinforce(999.0)

        self._decide_leap = decide
        self._reinforce_along_v_b = reinforce


class CanonicalAuthorityCliTests(unittest.TestCase):
    def test_install_disables_legacy_leap_decision_only_after_explicit_call(self):
        legacy = _LegacyModule()
        original = legacy._decide_leap

        self.assertEqual(legacy._decide_leap("h", "graph", "exact", None, "x"), "legacy-decision")
        returned = cli_v23_authority.install_canonical_action_authority(legacy)

        self.assertIs(returned, original)
        self.assertIsNone(legacy._decide_leap("h", "graph", "exact", None, "x"))
        self.assertEqual(len(legacy.calls), 1)

    def test_threshold_neutral_adaptation_ignores_legacy_H_and_pressure(self):
        legacy = _LegacyModule()
        original = cli_v23_authority.install_threshold_neutral_local_adaptation(legacy)
        node_a = _Node(kappa=0.5)
        node_b = _Node(kappa=0.5)

        legacy._reinforce_along_v_b(node_a, {"huge": 9999}, 0.0, 0.2)
        legacy._reinforce_along_v_b(node_b, {"different": -1}, 1.0, 0.2)

        self.assertIsNotNone(original)
        self.assertEqual(node_a.reinforce_calls, [0.1])
        self.assertEqual(node_b.reinforce_calls, [0.1])
        self.assertEqual(legacy.reinforce_calls, [])

    def test_threshold_neutral_adaptation_uses_bot_local_kappa_and_base_rate_only(self):
        legacy = _LegacyModule()
        cli_v23_authority.install_threshold_neutral_local_adaptation(legacy)
        node = _Node(kappa=0.25)

        legacy._reinforce_along_v_b(node, object(), 12345.0, 0.4)

        self.assertEqual(node.reinforce_calls, [0.1])

    def test_default_legacy_object_is_unchanged_until_authority_mode_is_installed(self):
        legacy = _LegacyModule()
        result = legacy._decide_leap("h", "graph", "miss", None, "x")
        node = _Node()
        legacy._reinforce_along_v_b(node, "legacy-h", 1.0, 0.2)

        self.assertEqual(result, "legacy-decision")
        self.assertEqual(len(legacy.calls), 1)
        self.assertEqual(len(legacy.reinforce_calls), 1)
        self.assertEqual(node.reinforce_calls, [999.0])

    def test_original_hooks_can_be_restored_for_embedding_or_tests(self):
        legacy = _LegacyModule()
        original_decide = cli_v23_authority.install_canonical_action_authority(legacy)
        original_reinforce = cli_v23_authority.install_threshold_neutral_local_adaptation(legacy)
        legacy._decide_leap = original_decide
        legacy._reinforce_along_v_b = original_reinforce

        self.assertEqual(legacy._decide_leap("h", "graph", "partial", None, "x"), "legacy-decision")
        node = _Node()
        legacy._reinforce_along_v_b(node, "h", 0.5, 0.2)
        self.assertEqual(node.reinforce_calls, [999.0])


if __name__ == "__main__":
    unittest.main()
