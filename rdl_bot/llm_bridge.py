"""
llm_bridge.py
LLM ブリッジ: ξポンプ / Phase 0 種まき器
"""

import os
import json
from typing import Optional
import anthropic

from node_graph import Node


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


class LLMBridge:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
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
        if self.mode == "on-once":
            self.mode = "off"
        return resp.content[0].text

    def ask_for_node(self, user_input: str) -> Optional[Node]:
        """
        入力に対してRDLノード構造を返すようLLMに依頼する。
        leap時に呼ばれる。
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
        raw = resp.content[0].text.strip()

        try:
            # コードブロックを除去
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            d = json.loads(raw)
            node = Node(
                inputs=d.get("inputs", [user_input]),
                rdl_type=d.get("rdl_type", "未分類"),
                spatial_tag=d.get("spatial_tag", "概念"),
                response=d.get("response"),
                source="llm_learned",
                confidence=float(d.get("confidence", 0.6)),
            )
            if self.mode == "on-once":
                self.mode = "off"
            return node
        except Exception:
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
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()

        try:
            items = json.loads(raw)
            nodes = []
            for d in items:
                nodes.append(Node(
                    inputs=d.get("inputs", []),
                    rdl_type=d.get("rdl_type", "未分類"),
                    spatial_tag=d.get("spatial_tag", "概念"),
                    response=d.get("response"),
                    source="llm_seed",
                    confidence=0.5,
                    ttl=500,
                ))
            return nodes
        except Exception:
            return []
