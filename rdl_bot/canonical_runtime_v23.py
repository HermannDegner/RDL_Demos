"""Conservative live-side controller for the rdl_bot Core v2.3 migration.

This controller wires real shadow turn pairs to the canonical authority without
making non-zero mismatch automatically count as H.

Flow::

    shadow turn pair
      -> frozen pre-update replay
      -> E = Delta(F, F')
      -> classify_mismatch
           zero E    -> resolved assessment -> authority (no H increment)
           nonzero E -> pending              -> no authority update
      -> explicit promotion of pending evidence
           -> unresolved ResolutionAssessment -> authority

The controller performs no legacy leap/correction action itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:  # package-style imports
    from .assessment_policy_v23 import (
        ResolutionCandidate,
        classify_mismatch,
        promote_pending_to_unresolved,
    )
    from .authority_v23 import AuthorityObservation, CanonicalLeapAuthority
    from .runtime_v23 import V23ConversationShadow
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from assessment_policy_v23 import (  # type: ignore
        ResolutionCandidate,
        classify_mismatch,
        promote_pending_to_unresolved,
    )
    from authority_v23 import AuthorityObservation, CanonicalLeapAuthority  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore


@dataclass(frozen=True)
class RuntimeAssessmentRecord:
    earlier_index: int
    later_index: int
    status: str
    candidate: Optional[ResolutionCandidate]
    authority_observation: Optional[AuthorityObservation]


@dataclass
class CanonicalRuntimeController:
    """Wire canonical comparison to fixed-theta authority conservatively."""

    authority: CanonicalLeapAuthority
    records: list[RuntimeAssessmentRecord] = field(default_factory=list)

    def assess_pair(
        self,
        *,
        shadow: V23ConversationShadow,
        earlier_index: int,
        later_index: int,
    ) -> RuntimeAssessmentRecord:
        mismatch = shadow.compare_with_earlier_model(earlier_index, later_index)
        if mismatch is None:
            record = RuntimeAssessmentRecord(
                earlier_index=earlier_index,
                later_index=later_index,
                status="boundary-changed-no-E",
                candidate=None,
                authority_observation=None,
            )
            self.records.append(record)
            return record

        refs = (f"turn-{earlier_index}", f"turn-{later_index}")
        candidate = classify_mismatch(mismatch, evidence_refs=refs)
        if candidate.assessment is None:
            record = RuntimeAssessmentRecord(
                earlier_index=earlier_index,
                later_index=later_index,
                status="pending-review",
                candidate=candidate,
                authority_observation=None,
            )
            self.records.append(record)
            return record

        observation = self.authority.observe_mismatch(
            mismatch,
            assessment=candidate.assessment,
        )
        record = RuntimeAssessmentRecord(
            earlier_index=earlier_index,
            later_index=later_index,
            status="resolved-observed",
            candidate=candidate,
            authority_observation=observation,
        )
        self.records.append(record)
        return record

    def promote_record(
        self,
        record: RuntimeAssessmentRecord,
        *,
        reason: str,
        assessor: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> AuthorityObservation:
        """Promote one pending runtime record to unresolved canonical H."""

        if record.status != "pending-review" or record.candidate is None:
            raise ValueError("only pending-review records can be promoted")
        assessment = promote_pending_to_unresolved(
            record.candidate,
            reason=reason,
            assessor=assessor,
            evidence_refs=evidence_refs,
        )
        return self.authority.observe_mismatch(
            record.candidate.mismatch,
            assessment=assessment,
        )
