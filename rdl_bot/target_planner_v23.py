"""Canonical evidence-based target planning for reconstruction requests.

The planner operates *after* canonical reconstruction eligibility has been
established.  It derives candidate node refs only from the frozen evaluator and
turn evidence named by the canonical request.  It never reads legacy H/hot-node
state.

A target is auto-proposed only when all concrete canonical evidence resolves to
one unique node under the same earlier frozen evaluator.  Ambiguous or missing
evidence remains review-required.

Restored sessions may retain review/pending records from an earlier process while
starting a fresh shadow comparison window.  Old frozen evaluators are not
recreated.  Therefore this planner only uses turn ids actually available in the
current process-local shadow window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:  # package-style imports
    from .action_gate_v23 import ReconstructionRequest
    from .runtime_v23 import V23ConversationShadow
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from action_gate_v23 import ReconstructionRequest  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore


_TURN_REF = re.compile(r"^turn-(\d+)$")


@dataclass(frozen=True)
class ReconstructionTargetPlan:
    status: str
    target_ref: str | None
    candidate_refs: tuple[str, ...]
    evidence_turns: tuple[int, ...]


def _turn_indices(request: ReconstructionRequest) -> tuple[int, ...]:
    values: list[int] = []
    for ref in request.evidence_refs:
        match = _TURN_REF.match(ref)
        if match:
            index = int(match.group(1))
            if index not in values:
                values.append(index)
    return tuple(values)


def _candidate_ref(evaluator, section) -> str | None:
    text = str(section.payload.get("text", ""))
    node, _match_type, nearest = evaluator.graph_snapshot.search(text)
    candidate = node if node is not None else nearest
    if candidate is None:
        return None
    ref = str(getattr(candidate, "id", ""))
    if not ref or ref.startswith("__"):
        return None
    return ref


class CanonicalTargetPlanner:
    """Propose a reconstruction target from canonical turn evidence only."""

    def plan(
        self,
        request: ReconstructionRequest,
        *,
        shadow: V23ConversationShadow,
    ) -> ReconstructionTargetPlan:
        if not isinstance(request, ReconstructionRequest):
            raise TypeError("request must be a ReconstructionRequest")

        indices = _turn_indices(request)
        available = set(shadow.available_turn_indices)
        valid_indices = tuple(index for index in indices if index in available)
        if not valid_indices:
            return ReconstructionTargetPlan(
                status="target-evidence-unavailable",
                target_ref=None,
                candidate_refs=(),
                evidence_turns=(),
            )

        earlier = shadow.turn_by_index(min(valid_indices))
        evaluator = earlier.model_evaluator
        candidates: list[str] = []
        for index in valid_indices:
            turn = shadow.turn_by_index(index)
            ref = _candidate_ref(evaluator, turn.input_section)
            if ref is not None and ref not in candidates:
                candidates.append(ref)

        candidate_refs = tuple(candidates)
        if len(candidate_refs) == 1:
            return ReconstructionTargetPlan(
                status="target-proposed",
                target_ref=candidate_refs[0],
                candidate_refs=candidate_refs,
                evidence_turns=valid_indices,
            )
        if not candidate_refs:
            return ReconstructionTargetPlan(
                status="target-evidence-unavailable",
                target_ref=None,
                candidate_refs=(),
                evidence_turns=valid_indices,
            )
        return ReconstructionTargetPlan(
            status="target-review-required",
            target_ref=None,
            candidate_refs=candidate_refs,
            evidence_turns=valid_indices,
        )
