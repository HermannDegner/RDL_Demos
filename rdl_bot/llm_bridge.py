"""
llm_bridge.py
LLM ブリッジ: ξポンプ / Phase 0 種まき器
"""

import os
import json
import re
from typing import Optional

try:
    import anthropic
except ImportError:
    # LLM offで使う場合にまでanthropicのインストールを必須にしない。
    anthropic = None

from node_graph import Node
from sfo_profile import AI_SFO


SYSTEM_PROMPT = """あなたはRDL（関係力学言語）の語彙で思考するアシスタントです。
RDLの主要概念：
- SILN（非線形世界における局所近似を通じた構造統合）
- H（フラストレーション・誤差蓄積）
- leap（閾値超過による構造の再編成）
- 境界（開放/閉鎖/接触）
- M_B（運動場・行動場）
- SFO（空間流向診断）
- ξ（未処理の揺らぎ）
- W_ij（構造間接続）

回答は日本語で、RDL語彙を自然に織り交ぜてください。
ただし、ユーザーがRDL語彙を使っていない場合は押しつけず、
背景として理解しながら日常語で応答してください。"""


VALID_SPATIAL_TAGS = {"人", "概念", "物語", "制度", "身体"}


def _sanitize_node_payload(d: dict, fallback_inputs: list[str]) -> Optional[dict]:
    """
    LLMが返すJSONの型・値域を検証する。不正な場合はNoneまたはフォールバック値に補正する。
    例えば inputs が文字列で返ってくると、検索時に1文字ずつパターン扱いされてしまう。
    """
    if not isinstance(d, dict):
        return None

    inputs = d.get("inputs")
    if isinstance(inputs, str):
        inputs = [inputs]
    if not isinstance(inputs, list):
        inputs = fallback_inputs
    inputs = [p for p in inputs if isinstance(p, str) and p.strip()]
    if not inputs:
        inputs = fallback_inputs
    if not inputs:
        return None

    rdl_type = d.get("rdl_type")
    if not isinstance(rdl_type, str) or not rdl_type.strip():
        rdl_type = "未分類"

    spatial_tag = d.get("spatial_tag")
    if spatial_tag not in VALID_SPATIAL_TAGS:
        spatial_tag = "概念"

    response = d.get("response")
    if response is not None and not isinstance(response, str):
        response = str(response)

    try:
        confidence = float(d.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    return {
        "inputs": inputs,
        "rdl_type": rdl_type,
        "spatial_tag": spatial_tag,
        "response": response,
        "confidence": confidence,
    }


_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*[ \t]*\r?\n?(.*?)(?:```|\Z)", re.DOTALL)


def _extract_json(raw: str):
    """
    LLM応答からJSONを取り出してパースする。

    以前は raw.split("```")[1].lstrip("json") で言語タグを外していた。
    str.lstrip() は「先頭にある j/s/o/n という*文字*をすべて剥がす」挙動で
    あって "json" という前置文字列の除去ではないため、
      - 言語タグが ```JSON のように大文字だと剥がれずパース失敗
      - フェンスを付けず散文に続けてJSONを返された場合も丸ごと失敗
    という取りこぼしがあった（H閾値超過でせっかく呼んだLLM応答が
    ノード化されず、そのままξプール行きになる）。

    順に、
      1. 素のテキストとしてパース
      2. コードフェンスの中身をパース
      3. 各 { / [ の位置から raw_decode() し、最初に成立した値を返す
    を試す。すべて失敗したら JSONDecodeError を送出する。
    """
    text = raw.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = _CODE_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # フェンスも無く前置きの散文が付いている場合の最後の手段。
    # 各 { / [ の位置から raw_decode() し、独立して成立する最初の値を返す。
    # 「最初の開き括弧」と「最後の閉じ括弧」で挟む方式だと、値が2つ並ぶ
    # 応答（`前置き {"a":1} 補足 {"b":2}`）で両者をまたいだ不正なJSONを
    # 組み立ててしまい、先頭の値が妥当でも取り出せなかった。
    # raw_decode は末尾の余分なテキストを無視するため後続の散文も許容でき、
    # 左から順に試すので配列内の最初の { を掴む心配もない。
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
            return value
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("JSONペイロードが見つかりません", text or "", 0)


class LLMBridge:
    def __init__(self, sfo_profile: AI_SFO): # SFOプロファイルを受け取るように変更
        self.sfo_profile = sfo_profile
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=api_key) if (anthropic and api_key) else None
        self.mode = "off"          # off / on / on-once
        self.model = "claude-haiku-4-5-20251001"

    def set_mode(self, mode: str):
        assert mode in ("off", "on", "on-once")
        self.mode = mode

    def available(self) -> bool:
        return self.client is not None

    def ask(self, user_input: str, context: str = "") -> Optional[str]:
        if not self.client:
            return None
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
            messages.append({"role": "assistant", "content": "了解しました。"})
        messages.append({"role": "user", "content": user_input})

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw_output = resp.content[0].text
        if self.mode == "on-once":
            self.mode = "off"
        return self.sfo_profile.get_sfo_filtered_response(raw_output) # SFOフィルタリングを適用

    def ask_for_node(self, user_input: str) -> Optional[Node]:
        """
        入力に対してRDLノード構造を返すようLLMに依頼する。
        未知の入力に対するleap時（対応する既存ノードがない場合）に呼ばれる。
        """
        if not self.client:
            return None

        prompt = f"""以下のユーザー入力をRDL語彙でノード化してください。
JSON形式で返してください（他のテキスト不要）。

入力: "{user_input}"

返すJSON:
{{
  "inputs": ["入力パターン1", "入力パターン2"],
  "rdl_type": "関係性の種類（例：関係性開始 / H過負荷 / 境界開放要求）",
  "spatial_tag": "人 or 概念 or 物語 or 制度 or 身体",
  "response": "返答テンプレート（日本語、1〜2文）",
  "confidence": 0.6
}}"""

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        # SFOフィルタリングはJSON構造の外側テキストではなく、
        # パース後の応答文にのみ適用する（生JSONに適用すると
        # 接頭辞付与や文字列置換でJSONが壊れ、常にパース失敗する）。
        raw = resp.content[0].text.strip()

        try:
            d = _extract_json(raw)
            payload = _sanitize_node_payload(d, fallback_inputs=[user_input])
            if payload is None:
                raise ValueError("empty/invalid inputs after sanitization")
            if payload["response"]:
                payload["response"] = self.sfo_profile.get_sfo_filtered_response(payload["response"])
            node = Node(
                inputs=payload["inputs"],
                rdl_type=payload["rdl_type"],
                spatial_tag=payload["spatial_tag"],
                response=payload["response"],
                source="llm_learned",
                confidence=payload["confidence"],
            )
            if self.mode == "on-once":
                self.mode = "off"
            return node
        except Exception as e:
            print(f"[LLM JSON parse failed] {e}")
            print(raw)
            return None

    def ask_for_node_revision(self, hot_node: Node, user_input: str) -> Optional[Node]:
        """
        既に否定が閾値を超えて蓄積した既存ノード（hot_node）を修正するためのノードを生成する。
        ask_for_node と異なり、「今回たまたま入力された文」ではなく
        「否定され続けている既存ノードの登録パターン・旧応答・否定理由」を渡し、
        leapの学習対象を実際にHが溜まった箇所と一致させる。
        """
        if not self.client:
            return None

        recent_counterexamples = hot_node.counterexamples[-5:]
        counterexample_lines = "\n".join(
            f'- 入力「{c.get("input", "")}」に対して {c.get("reason", "deny")}'
            for c in recent_counterexamples
        ) or "（記録なし）"

        prompt = f"""以下は、あるRDLノードがユーザーから繰り返し否定・言い換え要求を受けている状況です。
このノードを修正した新しいノードをRDL語彙で生成してください。
JSON形式で返してください（他のテキスト不要）。

既存ノードの登録パターン: {hot_node.inputs}
既存ノードの応答（否定されている内容）: "{hot_node.response}"
既存ノードのrdl_type: "{hot_node.rdl_type}"
直近の否定・言い換え履歴:
{counterexample_lines}
今回あらためて入力された文: "{user_input}"

返すJSON:
{{
  "inputs": ["入力パターン1", "入力パターン2"],
  "rdl_type": "関係性の種類",
  "spatial_tag": "人 or 概念 or 物語 or 制度 or 身体",
  "response": "旧応答を踏まえて修正した返答テンプレート（日本語、1〜2文）",
  "confidence": 0.6
}}"""

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()

        try:
            d = _extract_json(raw)
            payload = _sanitize_node_payload(d, fallback_inputs=list(hot_node.inputs) or [user_input])
            if payload is None:
                raise ValueError("empty/invalid inputs after sanitization")
            if payload["response"]:
                payload["response"] = self.sfo_profile.get_sfo_filtered_response(payload["response"])
            node = Node(
                inputs=payload["inputs"],
                rdl_type=payload["rdl_type"],
                spatial_tag=payload["spatial_tag"],
                response=payload["response"],
                source="llm_learned",
                confidence=payload["confidence"],
            )
            if self.mode == "on-once":
                self.mode = "off"
            return node
        except Exception as e:
            print(f"[LLM revision JSON parse failed] {e}")
            print(raw)
            return None

    def seed_universal_nodes(self) -> list[Node]:
        """
        Phase 0: 普遍ノード（レベル1）をLLMで生成する。
        """
        if not self.client:
            return []

        prompt = """日本語の日常会話で頻出する20個の入力パターンを、
RDL語彙でノード化してください。
JSON配列で返してください（他のテキスト不要）。

各要素:
{
  "inputs": ["パターン1", "パターン2"],
  "rdl_type": "関係性の種類",
  "spatial_tag": "人 or 概念 or 物語 or 制度 or 身体",
  "response": "返答テンプレート"
}"""

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        # ask_for_node と同様、生JSONにはSFOフィルタリングを適用しない。
        raw = resp.content[0].text.strip()

        try:
            items = _extract_json(raw)
            if not isinstance(items, list):
                raise ValueError(f"JSON配列を期待しましたが {type(items).__name__} でした")
            nodes = []
            for d in items:
                payload = _sanitize_node_payload(d, fallback_inputs=[])
                if payload is None:
                    continue
                if payload["response"]:
                    payload["response"] = self.sfo_profile.get_sfo_filtered_response(payload["response"])
                nodes.append(Node(
                    inputs=payload["inputs"],
                    rdl_type=payload["rdl_type"],
                    spatial_tag=payload["spatial_tag"],
                    response=payload["response"],
                    source="llm_seed",
                    confidence=0.5,
                    ttl=500,
                ))
            return nodes
        except Exception as e:
            print(f"[LLM seed parse failed] {e}")
            print(raw)
            return []
