"""SFOプロファイル・MBTI変換・drift機構（sfo_profile.py）"""

import unittest

from sfo_profile import (
    AI_SFO,
    DEFAULT_SFO_PRESET,
    MBTI_TO_SFO_MAP,
    create_sfo_profile_from_mbti,
)

VALID_SPACES = {"人", "概念", "物語", "制度", "身体"}
VALID_HIERARCHY = {"物理", "基層", "中核", "上層"}


class TestMBTITable(unittest.TestCase):
    def test_all_entries_use_valid_spatial_tags(self):
        """
        回帰テスト: ISTP の main_foreground_space に hierarchy_bias 側の値
        「物理」が混入しており、どのノードの spatial_tag とも一致しなかった。
        """
        for name, data in MBTI_TO_SFO_MAP.items():
            with self.subTest(mbti=name):
                self.assertTrue(set(data["main_foreground_space"]) <= VALID_SPACES)

    def test_all_entries_use_valid_hierarchy_bias(self):
        for name, data in MBTI_TO_SFO_MAP.items():
            with self.subTest(mbti=name):
                self.assertIn(data["hierarchy_bias"], VALID_HIERARCHY)

    def test_every_preset_is_reachable_by_name(self):
        """
        回帰テスト: 検索が mbti_type.upper() だったため、キーが混在ケースの
        RDL_native_* プリセットは一つも引けず、/mbti RDL_native_trickster が
        常に既定へフォールバックしていた。
        """
        for name in MBTI_TO_SFO_MAP:
            with self.subTest(mbti=name):
                p = create_sfo_profile_from_mbti(name)
                self.assertEqual(p.initial_fingerprint, name)

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(create_sfo_profile_from_mbti("intp").initial_fingerprint, "INTP")
        self.assertEqual(
            create_sfo_profile_from_mbti("rdl_NATIVE_trickster").initial_fingerprint,
            "RDL_native_trickster",
        )

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(create_sfo_profile_from_mbti("  INTP  ").initial_fingerprint, "INTP")

    def test_default_preset_exists(self):
        self.assertIn(DEFAULT_SFO_PRESET, MBTI_TO_SFO_MAP)

    def test_unknown_type_falls_back_to_observer(self):
        p = create_sfo_profile_from_mbti("XXXX")
        self.assertEqual(p.initial_fingerprint, "RDL_native_observer")

    def test_profile_does_not_share_lists_with_the_table(self):
        """
        回帰テスト: 生成したプロファイルがモジュール定数のlistを共有すると、
        update_drift() の破壊的更新でグローバルなテーブルが汚染される。
        """
        original = list(MBTI_TO_SFO_MAP["INTP"]["得意操作"])
        p = create_sfo_profile_from_mbti("INTP")
        p.得意操作.append("汚染")
        p.main_foreground_space.append("身体")
        self.assertEqual(MBTI_TO_SFO_MAP["INTP"]["得意操作"], original)
        self.assertEqual(MBTI_TO_SFO_MAP["INTP"]["main_foreground_space"], ["概念"])

    def test_two_profiles_are_independent(self):
        a = create_sfo_profile_from_mbti("INTP")
        b = create_sfo_profile_from_mbti("INTP")
        a.得意操作.append("汚染")
        self.assertNotIn("汚染", b.得意操作)


class TestSerialization(unittest.TestCase):
    def test_to_dict_returns_a_copy(self):
        """
        回帰テスト: 以前は self.__dict__ をそのまま返しており、
        受け取ったdictを書き換えるとプロファイル本体まで変わっていた。
        """
        p = AI_SFO()
        d = p.to_dict()
        d["得意操作"].append("汚染")
        d["hierarchy_bias"] = "上層"
        self.assertNotIn("汚染", p.得意操作)
        self.assertEqual(p.hierarchy_bias, "中核")

    def test_round_trip(self):
        p = create_sfo_profile_from_mbti("ENFP")
        p.drift_factor = 0.42
        restored = AI_SFO.from_dict(p.to_dict())
        self.assertEqual(restored.initial_fingerprint, "ENFP")
        self.assertEqual(restored.drift_factor, 0.42)
        self.assertEqual(restored.得意操作, p.得意操作)

    def test_from_dict_tolerates_unknown_keys(self):
        """session_state.json はバージョンをまたいで残るため、起動不能にしない。"""
        p = AI_SFO.from_dict({"hierarchy_bias": "上層", "将来追加された項目": 1})
        self.assertEqual(p.hierarchy_bias, "上層")

    def test_from_dict_uses_defaults_for_missing_keys(self):
        p = AI_SFO.from_dict({})
        self.assertEqual(p.hierarchy_bias, "中核")
        self.assertEqual(p.attention_mode, "DMN")


class TestDrift(unittest.TestCase):
    def test_deny_pushes_drift_up_and_agree_pulls_it_down(self):
        p = AI_SFO()
        p.update_drift({"deny": 4, "agree": 0, "llm_usage": 0})
        after_deny = p.drift_factor
        self.assertGreater(after_deny, 0.0)
        p.update_drift({"deny": 0, "agree": 5, "llm_usage": 0})
        self.assertLess(p.drift_factor, after_deny)

    def test_drift_is_clamped_to_unit_range(self):
        p = AI_SFO()
        p.update_drift({"deny": 1000, "agree": 0, "llm_usage": 1000})
        self.assertEqual(p.drift_factor, 1.0)
        p.update_drift({"deny": 0, "agree": 10000, "llm_usage": 0})
        self.assertEqual(p.drift_factor, 0.0)

    def test_repeated_drift_keeps_profile_valid(self):
        """ドリフトで空間や操作が入れ替わっても不正値にならないこと。"""
        p = create_sfo_profile_from_mbti("INTP")
        for _ in range(200):
            p.update_drift({"deny": 3, "agree": 1, "llm_usage": 2})
            self.assertTrue(set(p.main_foreground_space) <= VALID_SPACES)
            self.assertIn(p.hierarchy_bias, VALID_HIERARCHY)
            self.assertLessEqual(len(p.main_foreground_space), 2)


class TestCrisisMode(unittest.TestCase):
    def test_triggers_above_one_and_a_half_theta(self):
        p = AI_SFO()
        self.assertTrue(p.check_crisis_mode(3.1, 2.0))
        self.assertFalse(p.check_crisis_mode(2.9, 2.0))

    def test_zero_h_never_triggers(self):
        self.assertFalse(AI_SFO().check_crisis_mode(0.0, 2.0))


class TestSFOFilter(unittest.TestCase):
    def test_no_internal_label_leaks_into_output(self):
        """
        回帰テスト: 以前は "[SFOフィルタリング適用] " という内部ラベルが
        会話本文や Node.response にそのまま保存されていた。
        """
        out = AI_SFO().get_sfo_filtered_response("こんにちは")
        self.assertNotIn("SFOフィルタリング", out)

    def test_weak_operation_is_rephrased(self):
        p = AI_SFO(苦手操作=["壊す"])
        self.assertNotIn("壊す", p.get_sfo_filtered_response("ここは壊すべきです"))

    def test_output_is_a_string(self):
        self.assertIsInstance(AI_SFO().get_sfo_filtered_response(""), str)


if __name__ == "__main__":
    unittest.main()
