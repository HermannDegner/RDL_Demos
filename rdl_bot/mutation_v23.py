"""Explicit mutation adapter for canonical rdl_bot reconstruction.

This module is intentionally narrow.  It receives an already-selected canonical
target from :mod:`executor_v23` and performs a revision using the existing LLM
bridge.  It never reads legacy H/hot-node state, queue pressure, or Core xi.

Safety contract:
- unknown target -> no mutation;
- unavailable/off LLM -> no mutation;
- failed revision generation -> no mutation;
- only a generated replacement causes graph mutation;
- the old node is deprecated, not silently deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

try:
    from .action_gate_v23 import ReconstructionRequest
    from .target_planner_v23 import ReconstructionTargetPlan
except ImportError:
    from action_gate_v23 import ReconstructionRequest  # type: ignore
    from target_planner_v23 import ReconstructionTargetPlan  # type: ignore


@dataclass(frozen=True)
class CanonicalMutationResult:
    status: str
    target_ref: str
    replacement_ref: str | None = None


def make_llm_revision_mutation(graph: Any, llm: Any) -> Callable[[str, ReconstructionRequest, ReconstructionTargetPlan], CanonicalMutationResult]:
    """Return an executor callback that mutates only after successful revision generation."""

    def mutate(
        target_ref: str,
        _request: ReconstructionRequest,
        _plan: ReconstructionTargetPlan,
    ) -> CanonicalMutationResult:
        target = graph.get_by_id(target_ref)
        if target is None:
            return CanonicalMutationResult(
                status="not-mutated-target-missing",
                target_ref=target_ref,
            )

        mode = str(getattr(llm, "mode", "off"))
        available = callable(getattr(llm, "available", None)) and bool(llm.available())
        if mode not in {"on", "on-once"} or not available:
            return CanonicalMutationResult(
                status="not-mutated-llm-unavailable",
                target_ref=target_ref,
            )

        ask_revision = getattr(llm, "ask_for_node_revision", None)
        if not callable(ask_revision):
            return CanonicalMutationResult(
                status="not-mutated-revision-api-unavailable",
                target_ref=target_ref,
            )

        revised = ask_revision(target, None)
        if revised is None:
            return CanonicalMutationResult(
                status="not-mutated-revision-generation-failed",
                target_ref=target_ref,
            )

        relations = getattr(revised, "relations", None)
        if isinstance(relations, list) and target_ref not in relations:
            relations.append(target_ref)

        graph.add(revised)
        update_relations = getattr(graph, "update_relations", None)
        if callable(update_relations):
            update_relations(target_ref, [revised.id])

        target.status = "deprecated"
        target.confidence = max(0.0, float(getattr(target, "confidence", 0.0)) * 0.3)

        save = getattr(graph, "save", None)
        if callable(save):
            save()

        return CanonicalMutationResult(
            status="mutated-with-llm-revision",
            target_ref=target_ref,
            replacement_ref=str(revised.id),
        )

    return mutate
