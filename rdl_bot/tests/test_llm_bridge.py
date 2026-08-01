"""LLM応答のパースと検証（llm_bridge.py）"""

import json
import unittest

from llm_bridge import _extract_json, _sanitize_node_payload


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_with_language_tag(self):
        raw = '```json\n{"a": 1}\n```'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_fenced_without_language_tag(self):
        raw = '```\n{"json_like": 1}\n```'
        self.assertEqual(_extract_json(raw), {"json_like": 1})

    def test_fenced_with_uppercase_language_tag(self):
        """
        回帰テスト: 旧実装の lstrip("json") は小文字の j/s/o/n しか剥がさず、
        ```JSON と大文字で返されるとタグが本文に残りパースに失敗していた。
        """
        raw = '```JSON\n{"a": 1}\n```'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_prose_before_object(self):
        """
        回帰テスト: フェンス無しで散文に続けてJSONを返された場合、
        旧実装は raw をそのまま渡すためパースに失敗していた。
        """
        raw = '了解しました。以下がノードです:\n{"a": 1}'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_prose_before_array_returns_whole_array(self):
        """配列の中の最初の { を掴んで一部だけ返さないこと。"""
        raw = 'はい:\n[{"a": 1}, {"b": 2}]'
        self.assertEqual(_extract_json(raw), [{"a": 1}, {"b": 2}])

    def test_two_separate_embedded_objects_returns_the_first(self):
        """
        回帰テスト: 「最初の { と最後の }」で挟む方式だと、値が2つ並ぶ応答で
        両者をまたいだ不正なJSONを組み立ててしまい、先頭の値が妥当なのに
        取り出せなかった。
        """
        raw = '前置き {"a": 1} 補足 {"b": 2}'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_object_followed_by_array(self):
        raw = '前置き {"a": 1} 補足 [{"b": 2}]'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_trailing_prose_after_object(self):
        raw = '{"a": 1}\n\n以上です。'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_nested_object_is_not_truncated(self):
        raw = 'response: {"outer": {"inner": 1}}'
        self.assertEqual(_extract_json(raw), {"outer": {"inner": 1}})

    def test_skips_unparsable_opener_and_finds_later_value(self):
        raw = 'note {not json at all} then {"a": 1}'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_fenced_array(self):
        raw = '```json\n[{"a": 1}]\n```'
        self.assertEqual(_extract_json(raw), [{"a": 1}])

    def test_unterminated_fence(self):
        raw = '```json\n{"a": 1}'
        self.assertEqual(_extract_json(raw), {"a": 1})

    def test_garbage_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            _extract_json("すみません、JSONは返せません。")

    def test_empty_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            _extract_json("")


class TestSanitizeNodePayload(unittest.TestCase):
    def test_string_inputs_becomes_list(self):
        """inputs が文字列のままだと検索時に1文字ずつパターン扱いされる。"""
        p = _sanitize_node_payload({"inputs": "こんにちは"}, fallback_inputs=[])
        self.assertEqual(p["inputs"], ["こんにちは"])

    def test_invalid_spatial_tag_falls_back(self):
        p = _sanitize_node_payload(
            {"inputs": ["x"], "spatial_tag": "宇宙"}, fallback_inputs=[]
        )
        self.assertEqual(p["spatial_tag"], "概念")

    def test_valid_spatial_tag_kept(self):
        p = _sanitize_node_payload(
            {"inputs": ["x"], "spatial_tag": "身体"}, fallback_inputs=[]
        )
        self.assertEqual(p["spatial_tag"], "身体")

    def test_confidence_clamped_and_coerced(self):
        self.assertEqual(
            _sanitize_node_payload({"inputs": ["x"], "confidence": 5}, [])["confidence"], 1.0
        )
        self.assertEqual(
            _sanitize_node_payload({"inputs": ["x"], "confidence": -3}, [])["confidence"], 0.0
        )
        self.assertEqual(
            _sanitize_node_payload({"inputs": ["x"], "confidence": "0.42"}, [])["confidence"], 0.42
        )
        self.assertEqual(
            _sanitize_node_payload({"inputs": ["x"], "confidence": "なし"}, [])["confidence"], 0.6
        )

    def test_blank_inputs_use_fallback(self):
        p = _sanitize_node_payload({"inputs": ["", "  "]}, fallback_inputs=["元の入力"])
        self.assertEqual(p["inputs"], ["元の入力"])

    def test_no_usable_inputs_returns_none(self):
        self.assertIsNone(_sanitize_node_payload({"inputs": []}, fallback_inputs=[]))

    def test_non_dict_returns_none(self):
        self.assertIsNone(_sanitize_node_payload(["not", "a", "dict"], fallback_inputs=["x"]))

    def test_blank_rdl_type_falls_back(self):
        p = _sanitize_node_payload({"inputs": ["x"], "rdl_type": "   "}, [])
        self.assertEqual(p["rdl_type"], "未分類")


if __name__ == "__main__":
    unittest.main()
