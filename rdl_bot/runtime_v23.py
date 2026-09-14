"""Core v2.3 shadow adapter for the existing rdl_bot runtime.

This adapter observes real conversation turns without changing the legacy
``main.respond`` decision path.  It gives the migration a concrete acquisition
boundary while preserving all existing CLI behaviour.

Canonical comparison path::

    capture t
      -> freeze the pre-response graph-side evaluator M_B(t)
      -> acquire RIB_B(t)
      -> F = interp(M_B(t), RIB_B(t))

    capture t+Delta
      -> acquire RIB_B(t+Delta)
      -> replay that later section through the *frozen earlier evaluator*
      -> F' = interp(M_B(t), RIB_B(t+Delta))
      -> Delta(F, F')

The live graph is allowed to change between the two captures.  What must remain
fixed for canonical E is the evaluator used to form F and F', not the live
runtime state.  A changed comparison boundary still blocks the comparison.
"""

from __future__ import annotations

import copy
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
    """Fields that can materially affect the finite routing evaluator."""

    return {
        "id": str(getattr(node, "id", "")),
        "inputs": tuple(str(value) for value in getattr(node, "inputs", ())),
        "relations": tuple(str(value) for value in getattr(node, "relations", ())),
        "status": str(getattr(node, "status", "")),
        "source": str(getattr(node, "source", "")),
        "phase": str(getattr(node, "phase", "")),
        "confidence": round(float(getattr(node, "confidence", 0.0)), 12),
        "usage_count": int(getattr(node, "usage_count", 0)),
    }


def frozen_graph_model_ref(graph: Any) -> str:
    """Return a deterministic reference for a finite graph-side evaluator state.

    This is an implementation fingerprint, not an identity claim that the graph
    as a whole *is* Core M_B.
    """

    nodes = getattr(graph, "nodes", {})
    iterable = nodes.values() if hasattr(nodes, "values") else nodes
    payload = sorted((_node_snapshot(node) for node in iterable), key=lambda item: item["id"])
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "bot-graph:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _search_interpreter(graph: Any) -> Callable[[InteractionSection], dict[str, float]]:
    """Create a finite routing-state interpreter over one supplied graph state.

    Match class and confidence alone are insufficient: two different nodes can
    both be exact matches with the same confidence.  The finite F therefore also
    carries a one-hot-like route dimension ``route:<node-id>``.  This is not a
    claim that a node id is a Core primitive; it is a bot-local coordinate that
    preserves which finite route the frozen evaluator selected.
    """

    def evaluate(section: InteractionSection) -> dict[str, float]:
        text = str(section.payload.get("text", ""))
        node, match_type, nearest = graph.search(text)
        candidate = node if node is not None else nearest
        values: dict[str, float] = {
            "exact": 1.0 if match_type == "exact" else 0.0,
            "partial": 1.0 if match_type == "partial" else 0.0,
            "miss": 1.0 if match_type == "miss" else 0.0,
            "candidate_confidence": float(getattr(candidate, "confidence", 0.0)) if candidate else 0.0,
        }
        if candidate is not None:
            candidate_id = str(getattr(candidate, "id", "")).strip()
            if candidate_id:
                values[f"route:{candidate_id}"] = 1.0
        return values

    return evaluate


@dataclass(frozen=True)
class FrozenGraphEvaluator:
    """Deep-copied finite evaluator representing the pre-update M_B-side state."""

    model_ref: str
    graph_snapshot: Any

    @classmethod
    def from_graph(cls, graph: Any) -> "FrozenGraphEvaluator":
        snapshot = copy.deepcopy(graph)
        return cls(
            model_ref=frozen_graph_model_ref(snapshot),
            graph_snapshot=snapshot,
        )

    def interpret(self, section: InteractionSection) -> InterpretationState:
        return interpret_section(
            section,
            model_ref=self.model_ref,
            interpreter=_search_interpreter(self.graph_snapshot),
        )


@dataclass(frozen=True)
class ShadowTurn:
    index: int
    model_ref: str
    model_evaluator: FrozenGraphEvaluator
    input_section: InteractionSection
    input_state: InterpretationState
    response_section: Optional[InteractionSection] = None
    response_node_id: Optional[str] = None


def _same_comparison_boundary(first: BoundaryContext, later: BoundaryContext) -> bool:
    """Compare B-defining fields while allowing observation time to advance."""

    return (
        first.boundary_id == later.boundary_id
        and first.purpose == later.purpose
        and first.question == later.question
        and dict(first.conditions) == dict(later.conditions)
    )


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
        evaluator = FrozenGraphEvaluator.from_graph(graph)
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
        state = evaluator.interpret(section)
        turn = ShadowTurn(
            index=index,
            model_ref=evaluator.model_ref,
            model_evaluator=evaluator,
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
            model_evaluator=turn.model_evaluator,
            input_section=turn.input_section,
            input_state=turn.input_state,
            response_section=section,
            response_node_id=node_id,
        )
        self.turns[-1] = completed
        return completed

    def compare_inputs(self, earlier_index: int, later_index: int):
        """Strict comparison of already-formed F states with identical model refs.

        Kept as a diagnostic compatibility method.  For the canonical temporal
        comparison use :meth:`replay_later_under_earlier_model`.
        """

        earlier = self.turns[earlier_index - 1]
        later = self.turns[later_index - 1]
        if earlier.model_ref != later.model_ref:
            return None
        if not _same_comparison_boundary(earlier.input_section.context, later.input_section.context):
            return None
        return compare_interpretations(earlier.input_state, later.input_state)

    def replay_later_under_earlier_model(self, earlier_index: int, later_index: int):
        """Form F' from the later RIB_B using the earlier frozen evaluator.

        This is the canonical v2.3 path for ``F'``.  Live graph mutation between
        the two turns is irrelevant because both F and F' are interpreted by the
        evaluator frozen at ``earlier_index``.
        """

        earlier = self.turns[earlier_index - 1]
        later = self.turns[later_index - 1]
        if not _same_comparison_boundary(earlier.input_section.context, later.input_section.context):
            return None
        replayed_later = earlier.model_evaluator.interpret(later.input_section)
        return compare_interpretations(earlier.input_state, replayed_later)


def respond_with_shadow(
    user_input: str,
    graph: Any,
    h: Any,
    llm: Any,
    sfo_profile: Any,
    unresolved_queue: list[str],
    llm_trust: Any,
    *,
    shadow: Optional[V23ConversationShadow] = None,
    legacy_respond: Optional[Callable[..., tuple[str, str]]] = None,
) -> tuple[str, str]:
    """Call the legacy response path unchanged while recording canonical sections.

    ``unresolved_queue`` is the v2.3 migration name for the list historically
    passed to ``main.respond`` as ``xi_pool``.  It is still passed positionally to
    the legacy function, so behaviour is unchanged; the new adapter API no
    longer names the deferred-input queue after Core xi.
    """

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
        unresolved_queue,
        llm_trust,
    )
    shadow.capture_response(turn, response_text, node_id)
    return response_text, node_id
