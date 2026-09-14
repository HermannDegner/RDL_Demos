import unittest

import cli_v23_authority


class _LegacyModule:
    def __init__(self):
        self.calls = []

        def decide(*args, **kwargs):
            self.calls.append((args, kwargs))
            return "legacy-decision"

        self._decide_leap = decide


class CanonicalAuthorityCliTests(unittest.TestCase):
    def test_install_disables_legacy_leap_decision_only_after_explicit_call(self):
        legacy = _LegacyModule()
        original = legacy._decide_leap

        self.assertEqual(legacy._decide_leap("h", "graph", "exact", None, "x"), "legacy-decision")
        returned = cli_v23_authority.install_canonical_action_authority(legacy)

        self.assertIs(returned, original)
        self.assertIsNone(legacy._decide_leap("h", "graph", "exact", None, "x"))
        self.assertEqual(len(legacy.calls), 1)

    def test_default_legacy_object_is_unchanged_until_authority_mode_is_installed(self):
        legacy = _LegacyModule()
        result = legacy._decide_leap("h", "graph", "miss", None, "x")

        self.assertEqual(result, "legacy-decision")
        self.assertEqual(len(legacy.calls), 1)

    def test_original_decision_can_be_restored_for_embedding_or_tests(self):
        legacy = _LegacyModule()
        original = cli_v23_authority.install_canonical_action_authority(legacy)
        legacy._decide_leap = original

        self.assertEqual(legacy._decide_leap("h", "graph", "partial", None, "x"), "legacy-decision")


if __name__ == "__main__":
    unittest.main()
