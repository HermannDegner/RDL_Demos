"""End-to-end candidate pipeline for canonical rdl_bot reconstruction.

This pipeline is still non-authoritative for the default CLI.  It composes the
already separated v2.3 stages without importing legacy H/hot-node state:

    pending runtime record
      -> explicit review/promotion
      -> canonical H + fixed theta
      -> targetless reconstruction request
      -> canonical evidence target plan
      -> injected mutation callback

No automatic path exists from a raw deny/miss/silence event into execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

try:  # package-style imports
    from .action_gate_v23 import CanonicalActionGate, ReconstructionRequest
    from .canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord
    from .executor_v23 import CanonicalReconstructionExecutor, ReconstructionExecution
    from .runtime_v23 import V23ConversationShadow
    from .target_planner_v23 import CanonicalTargetPlanner, ReconstructionTargetPlan
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from action_gate_v23 import CanonicalActionGate, ReconstructionRequest  # type: ignore
    from canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord  # type: ignore
    from executor_v23 import CanonicalReconstructionExecutor, ReconstructionExecution  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore
    from target_planner_v23 import CanonicalTargetPlanner, ReconstructionTargetPlan  # type: ignore


@dataclass(frozen=True)
class CanonicalPipelineResult:
    status: str
    request: ReconstructionRequest | None = None
    plan: ReconstructionTargetPlan | None = None
    execution: ReconstructionExecution | None = None


class CanonicalReconstructionPipeline:
    """Compose explicit-review canonical reconstruction stages."""

    def __init__(
        self,
        controller: CanonicalRuntimeController,
        *,
        gate: CanonicalActionGate | None = None,
        planner: CanonicalTargetPlanner | None = None,
        executor: CanonicalReconstructionExecutor | None = None,
    ) -> None:
        self.controller = controller
        self.gate = gate or CanonicalActionGate()
        self.planner = planner or CanonicalTargetPlanner()
        self.executor = executor or CanonicalReconstructionExecutor()

    def review_and_execute(
        self,
        record: RuntimeAssessmentRecord,
        *,
        shadow: V23ConversationShadow,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
        mutate: Callable[[str, ReconstructionRequest, ReconstructionTargetPlan], Any],
    ) -> CanonicalPipelineResult:
        """Run only after an explicit review of a pending canonical mismatch."""

        observation = self.controller.promote_record(
            record,
            reason=reason,
            assessor=assessor,
            evidence_refs=evidence_refs,
        )
        request = self.gate.request(observation)
        if request is None:
            return CanonicalPipelineResult(status="reviewed-below-reconstruction-threshold")

        plan = self.planner.plan(request, shadow=shadow)
        if plan.status != "target-proposed":
            return CanonicalPipelineResult(
                status=plan.status,
                request=request,
                plan=plan,
            )

        execution = self.executor.execute(request, plan, mutate=mutate)
        return CanonicalPipelineResult(
            status=execution.status,
            request=request,
            plan=plan,
            execution=execution,
        )
