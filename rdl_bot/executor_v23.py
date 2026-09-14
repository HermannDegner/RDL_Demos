"""Candidate executor boundary for canonical rdl_bot reconstruction.

This module does not know how legacy leap/correction works.  It accepts only a
canonical reconstruction request plus a canonical target plan.  Mutation is an
injected callback so the live CLI can be migrated later without importing
legacy H/hot-node state into the canonical decision path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

try:  # package-style imports
    from .action_gate_v23 import ReconstructionRequest
    from .target_planner_v23 import ReconstructionTargetPlan
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from action_gate_v23 import ReconstructionRequest  # type: ignore
    from target_planner_v23 import ReconstructionTargetPlan  # type: ignore


@dataclass(frozen=True)
class ReconstructionExecution:
    status: str
    target_ref: str | None
    result: Any = None


class CanonicalReconstructionExecutor:
    """Execute only an unambiguous canonical target plan.

    The callback receives ``(target_ref, request, plan)``.  The executor neither
    selects the target nor imports legacy feedback state.  Ambiguous or missing
    target plans are returned as non-executed outcomes.
    """

    def execute(
        self,
        request: ReconstructionRequest,
        plan: ReconstructionTargetPlan,
        *,
        mutate: Callable[[str, ReconstructionRequest, ReconstructionTargetPlan], Any],
    ) -> ReconstructionExecution:
        if not isinstance(request, ReconstructionRequest):
            raise TypeError("request must be a ReconstructionRequest")
        if not isinstance(plan, ReconstructionTargetPlan):
            raise TypeError("plan must be a ReconstructionTargetPlan")
        if not callable(mutate):
            raise TypeError("mutate must be callable")

        if plan.status != "target-proposed" or plan.target_ref is None:
            return ReconstructionExecution(
                status="not-executed-target-review-required",
                target_ref=None,
            )

        if plan.target_ref not in plan.candidate_refs:
            return ReconstructionExecution(
                status="not-executed-invalid-target-plan",
                target_ref=None,
            )

        result = mutate(plan.target_ref, request, plan)
        return ReconstructionExecution(
            status="executed-canonical-target",
            target_ref=plan.target_ref,
            result=result,
        )
