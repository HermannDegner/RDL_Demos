"""Canonical evidence-based LLM revision generation for rdl_bot v2.3.

The historical ``LLMBridge.ask_for_node_revision`` prompt describes a node as
being revised because legacy H/deny accumulation crossed a threshold.  That is
not an acceptable premise for the canonical execution path.

This module generates a replacement from the already-reviewed canonical
``ReconstructionRequest``.  The LLM receives the target application node plus
canonical mismatch/review evidence, but no claim that legacy feedback load is
Core H.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from .action_gate_v23 import ReconstructionRequest
    from .llm_bridge import _extract_json, _sanitize_node_payload
    from .node_graph import Node
except ImportError:
    from action_gate_v23 import ReconstructionRequest  # type: ignore
    from llm_bridge import _extract_json, _sanitize_node_payload  # type: ignore
    from node_graph import Node  # type: ignore


CANONICAL_REVISION_SYSTEM_PROMPT = """あなたはRDL Core v2.3に従う補助生成器です。
対象ノード自体をCore M_BやSILNと同一視しません。
RIB_BとFを区別し、E=Δ(F,F')のうち明示的に未解決とレビューされた差分だけを
再構成根拠として扱います。legacyのdeny/miss、待ち行列、ノイズ、uncertaintyを
Core Hやξと同一視しません。返答は要求されたJSONだけにしてください。"""


def generate_canonical_revision(
    llm: Any,
    target: Any,
    request: ReconstructionRequest,
) -> Optional[Any]:
    """Generate one replacement node from explicit canonical review evidence.

    Test doubles or alternative bridges may provide
    ``ask_for_canonical_node_revision(target, request)``.  Otherwise the normal
    ``LLMBridge`` client is called directly with a v2.3-specific prompt.
    """

    custom = getattr(llm, "ask_for_canonical_node_revision", None)
    if callable(custom):
        return custom(target, request)

    client = getattr(llm, "client", None)
    if client is None:
        return None

    inputs = list(getattr(target, "inputs", ()))
    response = getattr(target, "response", None)
    rdl_type = str(getattr(target, "rdl_type", "未分類"))
    reasons = ", ".join(request.mismatch_reasons) or "（有限差分理由なし）"
    evidence = ", ".join(request.evidence_refs) or "（参照なし）"

    prompt = f"""以下のアプリケーションノードについて、canonical RDL v2.3 reviewで
再構成候補が必要と判断されました。旧H/deny蓄積ではなく、下記の明示reviewを根拠に
代替ノードを生成してください。

既存ノード入力: {inputs}
既存ノード応答: {response!r}
既存ノード種別: {rdl_type!r}
canonical mismatch reasons: {reasons}
review reason: {request.assessment_reason}
review assessor: {request.assessment_assessor}
evidence refs: {evidence}

JSON形式:
{{
  "inputs": ["入力パターン1", "入力パターン2"],
  "rdl_type": "アプリケーション上の関係種別",
  "spatial_tag": "人 or 概念 or 物語 or 制度 or 身体",
  "response": "有限reviewを踏まえた修正版応答",
  "confidence": 0.6
}}"""

    response_obj = client.messages.create(
        model=getattr(llm, "model", "claude-haiku-4-5-20251001"),
        max_tokens=300,
        system=CANONICAL_REVISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response_obj.content[0].text.strip()

    try:
        payload = _sanitize_node_payload(
            _extract_json(raw),
            fallback_inputs=inputs,
        )
        if payload is None:
            return None
        sfo_profile = getattr(llm, "sfo_profile", None)
        if payload["response"] and sfo_profile is not None:
            payload["response"] = sfo_profile.get_sfo_filtered_response(payload["response"])
        node = Node(
            inputs=payload["inputs"],
            rdl_type=payload["rdl_type"],
            spatial_tag=payload["spatial_tag"],
            response=payload["response"],
            source="llm_learned",
            confidence=payload["confidence"],
        )
        if getattr(llm, "mode", None) == "on-once":
            llm.mode = "off"
        return node
    except Exception as exc:
        print(f"[canonical v2.3 revision parse failed] {exc}")
        print(raw)
        return None
