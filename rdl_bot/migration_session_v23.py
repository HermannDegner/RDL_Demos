"""Opt-in conversation session for the rdl_bot Core v2.3 migration.

The session wraps the existing legacy response function through
``respond_with_shadow`` and automatically forms conservative canonical
assessments between adjacent user-input turns.  It does not execute
reconstruction automatically.

Non-zero E becomes ``pending-review`` only.  A caller must explicitly select a
pending record and call ``review_and_execute`` with provenance plus an injected
mutation callback before the canonical pipeline can mutate anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:  # package-style imports
    from .authority_v23 import CanonicalLeapAuthority
    from .canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord
    from .pipeline_v23 import CanonicalPipelineResult, CanonicalReconstructionPipeline
    from .runtime_v23 import V23ConversationShadow, respond_with_shadow
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from authority_v23 import CanonicalLeapAuthority  # type: ignore
    from canonical_runtime_v23 import CanonicalRuntimeController, RuntimeAssessmentRecord  # type: ignore
    from pipeline_v23 import CanonicalPipelineResult, CanonicalReconstructionPipeline  # type: ignore
    from runtime_v23 import V23ConversationShadow, respond_with_shadow  # type: ignore


@dataclass
class CanonicalMigrationSession:
    """Observe live turns and retain canonical review records without auto-action."""

    theta: float = 2.0
    decay: float = 1.0
    shadow: V23ConversationShadow = field(default_factory=V23ConversationShadow)
    controller: CanonicalRuntimeController = field(init=False)
    pipeline: CanonicalReconstructionPipeline = field(init=False)
    assessments: list[RuntimeAssessmentRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        authority = CanonicalLeapAuthority(theta=self.theta, decay=self.decay)
        self.controller = CanonicalRuntimeController(authority)
        self.pipeline = CanonicalReconstructionPipeline(self.controller)

    @property
    def pending_records(self) -> tuple[RuntimeAssessmentRecord, ...]:
        return tuple(record for record in self.assessments if record.status == "pending-review")

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
            later = len(self.shadow.turns)
            record = self.controller.assess_pair(
                shadow=self.shadow,
                earlier_index=later - 1,
                later_index=later,
            )
            self.assessments.append(record)
        return result

    def review_and_execute(
        self,
        record: RuntimeAssessmentRecord,
        *,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
        mutate: Callable[..., Any],
    ) -> CanonicalPipelineResult:
        """Explicitly review one pending record; never inferred from raw feedback."""

        if record not in self.assessments:
            raise ValueError("record does not belong to this migration session")
        return self.pipeline.review_and_execute(
            record,
            shadow=self.shadow,
            reason=reason,
            assessor=assessor,
            evidence_refs=evidence_refs,
            mutate=mutate,
        )
