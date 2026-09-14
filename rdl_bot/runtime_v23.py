"""Core v2.3 shadow adapter for the existing rdl_bot runtime.

This adapter observes real conversation turns without changing the legacy
``main.respond`` decision path.  It gives the migration a concrete acquisition
boundary while preserving all existing CLI behaviour.

Important semantic boundary:

- raw user text != RIB_B;
- ``InteractionSection`` is the finite acquired section;
- F is formed only after the section is acquired;
- two F states are comparable only when the frozen pre-update ``model_ref`` is
  identical;
- legacy miss/deny/silence counters and unresolved-input pressure are not
  promoted into canonical H or Core xi here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

try:  # package-style imports
    from .v23_state import (
        BoundaryContext,
        InteractionSection,
        InterpretationState,
        Provenance,
        acquire_text_section,
        compare_interpretations,
        interpret_section,
    )
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from v23_state import (  # type: ignore
        BoundaryContext,
        InteractionSection,
        InterpretationState,
        Provenance,
        acquire_text_section,
        compare_interpretations,
        interpret_section,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node_snapshot(node: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(node, "id", "")),
        "status": str(getattr(node, "status", "")),
        "phase": str(getattr(node, "phase", "")),
        "confidence": round(float(getattr(node, "confidence", 0.0)), 12),
        "usage_count": int(getattr(node, "usage_count", 0)),
    }


def frozen_graph_model_ref(graph: Any) -> str:
    """Return a deterministic reference for the pre-response graph state.

    This is an implementation fingerprint, not an identity claim that the graph
    as a whole *is* Core M_B.  It only pins which finite graph-side evaluator
    state was used for one F observation.
    """

    nodes = getattr(graph, "nodes", {})
    iterable = nodes.values() if hasattr(nodes, "values") else nodes
    payload = sorted((_node_snapshot(node) for node in iterable), key=lambda item: item["id"])
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "bot-graph:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _search_interpreter(graph: Any) -> Callable[[InteractionSection], dict[str, float]]:
    """Freeze a finite routing evaluator for one pre-response graph state."""

    def evaluate(section: InteractionSection) -> dict[str, float]:
        text = str(section.payload.get("text", ""))
        node, match_type, nearest = graph.search(text)
        candidate = node if node is not None else nearest
        return {
            "exact": 1.0 if match_type == "exact" else 0.0,
            "partial": 1.0 if match_type == "partial" else 0.0,
            "miss": 1.0 if match_type == "miss" else 0.0,
            "candidate_confidence": float(getattr(candidate, "confidence", 0.0)) if candidate else 0.0,
        }

    return evaluate


@dataclass(frozen=True)
class ShadowTurn:
    index: int
    model_ref: str
    input_section: InteractionSection
    input_state: InterpretationState
    response_section: Optional[InteractionSection] = None
    response_node_id: Optional[str] = None


@dataclass
class V23ConversationShadow:
    """Non-authoritative observer of live legacy bot turns."""

    boundary_id: str = "rdl_bot:conversation"
    purpose: str = "observe finite user/bot interaction sections during v2.3 migration"
    question: str = "what finite routing state is produced under the frozen pre-response graph?"
    actor: str = "user"
    turns: list[ShadowTurn] = field(default_factory=list)

    def _context(self, observed_at: str) -> BoundaryContext:
        return BoundaryContext(
            boundary_id=self.boundary_id,
            purpose=self.purpose,
            question=self.question,
            observation_time=observed_at,
            conditions={"migration": "shadow", "runtime": "legacy-main.respond"},
        )

    def capture_input(self, text: str, graph: Any) -> ShadowTurn:
        observed_at = _utc_now()
        index = len(self.turns) + 1
        model_ref = frozen_graph_model_ref(graph)
        section = acquire_text_section(
            section_id=f"turn-{index}:input",
            text=text,
            context=self._context(observed_at),
            role="user-input",
            provenance=Provenance(
                source="rdl_bot.runtime_v23",
                actor=self.actor,
                observed_at=observed_at,
                lineage=f"turn-{index}",
            ),
            metadata={"turn_index": index},
        )
        state = interpret_section(
            section,
            model_ref=model_ref,
            interpreter=_search_interpreter(graph),
        )
        turn = ShadowTurn(
            index=index,
            model_ref=model_ref,
            input_section=section,
            input_state=state,
        )
        self.turns.append(turn)
        return turn

    def capture_response(self, turn: ShadowTurn, response_text: str, node_id: str) -> ShadowTurn:
        observed_at = _utc_now()
        section = acquire_text_section(
            section_id=f"turn-{turn.index}:response",
            text=response_text,
            context=turn.input_section.context,
            role="bot-response",
            provenance=Provenance(
                source="rdl_bot.runtime_v23",
                actor="bot",
                observed_at=observed_at,
                lineage=f"turn-{turn.index}",
            ),
            metadata={"turn_index": turn.index, "node_id": node_id},
        )
        completed = ShadowTurn(
            index=turn.index,
            model_ref=turn.model_ref,
            input_section=turn.input_section,
            input_state=turn.input_state,
            response_section=section,
            response_node_id=node_id,
        )
        self.turns[-1] = completed
        return completed

    def compare_inputs(self, earlier_index: int, later_index: int):
        """Compare two user-input F states only when the pre-update model matches."""

        earlier = self.turns[earlier_index - 1]
        later = self.turns[later_index - 1]
        if earlier.model_ref != later.model_ref:
            return None
        return compare_interpretations(earlier.input_state, later.input_state)


def respond_with_shadow(
    user_input: str,
    graph: Any,
    h: Any,
    llm: Any,
    sfo_profile: Any,
    xi_pool: list[str],
    llm_trust: Any,
    *,
    shadow: Optional[V23ConversationShadow] = None,
    legacy_respond: Optional[Callable[..., tuple[str, str]]] = None,
) -> tuple[str, str]:
    """Call the legacy response path unchanged while recording canonical sections."""

    if shadow is None:
        shadow = V23ConversationShadow()
    if legacy_respond is None:
        try:
            from .main import respond as legacy_respond_impl
        except ImportError:
            from main import respond as legacy_respond_impl  # type: ignore
        legacy_respond = legacy_respond_impl

    turn = shadow.capture_input(user_input, graph)
    response_text, node_id = legacy_respond(
        user_input,
        graph,
        h,
        llm,
        sfo_profile,
        xi_pool,
        llm_trust,
    )
    shadow.capture_response(turn, response_text, node_id)
    return response_text, node_id
