"""Opt-in conversation session for the rdl_bot Core v2.3 migration.

The session wraps the existing legacy response function through
``respond_with_shadow`` and automatically forms conservative canonical
assessments between adjacent user-input turns.  It does not execute
reconstruction automatically.

Non-zero E becomes ``pending-review`` only.  A pending record can be explicitly
reviewed as either resolved or unresolved with provenance.  Only an unresolved
review updates canonical H.  A reviewed unresolved observation can then be
planned in dry-run mode without mutating the graph.  Mutation remains a separate
explicit call through the candidate pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:  # package-style imports
    from .action_gate_v23 import ReconstructionRequest
    from .authority_v23 import AuthorityObservation, CanonicalLeapAuthority
    from .canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord
    from .pipeline_v23 import CanonicalPipelineResult, CanonicalReconstructionPipeline
    from .resolution_v23 import ResolutionAssessment
    from .runtime_v23 import V23ConversationShadow, respond_with_shadow
    from .target_planner_v23 import ReconstructionTargetPlan
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from action_gate_v23 import ReconstructionRequest  # type: ignore
    from authority_v23 import AuthorityObservation, CanonicalLeapAuthority  # type: ignore
    from canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord  # type: ignore
    from pipeline_v23 import CanonicalPipelineResult, CanonicalReconstructionPipeline  # type: ignore
    from resolution_v23 import ResolutionAssessment  # type: ignore
    from runtime_v23 import V23ConversationShadow, respond_with_shadow  # type: ignore
    from target_planner_v23 import ReconstructionTargetPlan  # type: ignore


def _merged_refs(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for value in group:
            ref = str(value)
            if ref not in seen:
                seen.add(ref)
                result.append(ref)
    return tuple(result)


@dataclass(frozen=True)
class SessionReview:
    earlier_index: int
    later_index: int
    assessment: ResolutionAssessment
    authority_observation: Optional[AuthorityObservation] = None

    @property
    def disposition(self) -> str:
        return "unresolved" if self.assessment.unresolved else "resolved"


@dataclass(frozen=True)
class SessionPlanPreview:
    status: str
    request: Optional[ReconstructionRequest] = None
    plan: Optional[ReconstructionTargetPlan] = None


@dataclass
class CanonicalMigrationSession:
    """Observe live turns and retain explicit canonical review state."""

    theta: float = 2.0
    decay: float = 1.0
    shadow: V23ConversationShadow = field(default_factory=V23ConversationShadow)
    controller: CanonicalRuntimeController = field(init=False)
    pipeline: CanonicalReconstructionPipeline = field(init=False)
    assessments: list[RuntimeAssessmentRecord] = field(default_factory=list)
    reviews: list[SessionReview] = field(default_factory=list)

    def __post_init__(self) -> None:
        authority = CanonicalLeapAuthority(theta=self.theta, decay=self.decay)
        self.controller = CanonicalRuntimeController(authority)
        self.pipeline = CanonicalReconstructionPipeline(self.controller)

    def _review_key(self, record: RuntimeAssessmentRecord) -> tuple[int, int]:
        return record.earlier_index, record.later_index

    def _review_for(self, record: RuntimeAssessmentRecord) -> Optional[SessionReview]:
        key = self._review_key(record)
        for review in self.reviews:
            if (review.earlier_index, review.later_index) == key:
                return review
        return None

    def _require_pending_record(self, record: RuntimeAssessmentRecord) -> None:
        if record not in self.assessments:
            raise ValueError("record does not belong to this migration session")
        if record.status != "pending-review" or record.candidate is None:
            raise ValueError("only pending-review records can be reviewed")
        if self._review_for(record) is not None:
            raise ValueError("record has already been reviewed")

    @property
    def pending_records(self) -> tuple[RuntimeAssessmentRecord, ...]:
        return tuple(
            record
            for record in self.assessments
            if record.status == "pending-review" and self._review_for(record) is None
        )

    def respond(
        self,
        user_input: str,
        graph: Any,
        h: Any,
        llm: Any,
        sfo_profile: Any,
        unresolved_queue: list[str],
        llm_trust: Any,
        *,
        legacy_respond: Optional[Callable[..., tuple[str, str]]] = None,
    ) -> tuple[str, str]:
        """Preserve the legacy response while adding non-authoritative observation."""

        result = respond_with_shadow(
            user_input,
            graph,
            h,
            llm,
            sfo_profile,
            unresolved_queue,
            llm_trust,
            shadow=self.shadow,
            legacy_respond=legacy_respond,
        )
        if len(self.shadow.turns) >= 2:
            earlier_index = self.shadow.turns[-2].index
            later_index = self.shadow.turns[-1].index
            record = self.controller.assess_pair(
                shadow=self.shadow,
                earlier_index=earlier_index,
                later_index=later_index,
            )
            self.assessments.append(record)
        return result

    def review_resolved(
        self,
        record: RuntimeAssessmentRecord,
        *,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> ResolutionAssessment:
        """Explicitly close a non-zero pending mismatch as resolved without H."""

        self._require_pending_record(record)
        candidate = record.candidate
        refs = _merged_refs(candidate.evidence_refs, evidence_refs)
        assessment = ResolutionAssessment.resolved(
            reason=reason,
            assessor=assessor,
            evidence_refs=refs,
        )
        self.reviews.append(
            SessionReview(record.earlier_index, record.later_index, assessment)
        )
        return assessment

    def review_unresolved(
        self,
        record: RuntimeAssessmentRecord,
        *,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> AuthorityObservation:
        """Explicitly promote a pending mismatch into canonical H, but do not mutate."""

        self._require_pending_record(record)
        observation = self.controller.promote_record(
            record,
            reason=reason,
            assessor=assessor,
            evidence_refs=evidence_refs,
        )
        self.reviews.append(
            SessionReview(
                record.earlier_index,
                record.later_index,
                observation.assessment,
                authority_observation=observation,
            )
        )
        return observation

    def preview_latest_reconstruction(self) -> SessionPlanPreview:
        """Dry-run the latest unresolved review through gate + target planner only."""

        review = next(
            (
                item
                for item in reversed(self.reviews)
                if item.disposition == "unresolved" and item.authority_observation is not None
            ),
            None,
        )
        if review is None:
            return SessionPlanPreview(status="no-unresolved-review")

        request = self.pipeline.gate.request(review.authority_observation)
        if request is None:
            return SessionPlanPreview(status="below-reconstruction-threshold")

        plan = self.pipeline.planner.plan(request, shadow=self.shadow)
        return SessionPlanPreview(
            status=plan.status,
            request=request,
            plan=plan,
        )

    def review_and_execute(
        self,
        record: RuntimeAssessmentRecord,
        *,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
        mutate: Callable[..., Any],
    ) -> CanonicalPipelineResult:
        """Explicitly review one pending record and enter the candidate mutation pipeline."""

        self._require_pending_record(record)
        result = self.pipeline.review_and_execute(
            record,
            shadow=self.shadow,
            reason=reason,
            assessor=assessor,
            evidence_refs=evidence_refs,
            mutate=mutate,
        )
        candidate = record.candidate
        assessment = ResolutionAssessment.unresolved_case(
            reason=reason,
            assessor=assessor,
            evidence_refs=_merged_refs(candidate.evidence_refs, evidence_refs),
        )
        self.reviews.append(
            SessionReview(record.earlier_index, record.later_index, assessment)
        )
        return result
