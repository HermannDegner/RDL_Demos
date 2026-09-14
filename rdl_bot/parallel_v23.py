"""Parallel decision observer for the rdl_bot Core v2.3 migration.

The live CLI still acts on ``LegacyFeedbackLoadState``.  This module compares
that legacy eligibility signal with ``CanonicalLeapAuthority`` without letting
the canonical candidate mutate the legacy action path or vice versa.

Canonical unresolved classification arrives as a provenance-bearing
``ResolutionAssessment``; it is never inferred from legacy miss/deny/silence
counters here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:  # package-style imports
    from .authority_v23 import AuthorityObservation, CanonicalLeapAuthority
    from .resolution_v23 import ResolutionAssessment
    from .runtime_v23 import V23ConversationShadow
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from authority_v23 import AuthorityObservation, CanonicalLeapAuthority  # type: ignore
    from resolution_v23 import ResolutionAssessment  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore


@dataclass(frozen=True)
class ParallelDecisionRecord:
    earlier_index: int
    later_index: int
    canonical_status: str
    canonical_should_reconstruct: bool
    canonical_h_magnitude: float
    canonical_theta: float
    assessment_reason: str
    assessment_assessor: str
    legacy_should_leap: bool
    legacy_target: str

    @property
    def agrees(self) -> bool:
        return self.canonical_should_reconstruct == self.legacy_should_leap


@dataclass
class CanonicalParallelObserver:
    """Record candidate-vs-legacy eligibility without performing any action."""

    authority: CanonicalLeapAuthority
    records: list[ParallelDecisionRecord] = field(default_factory=list)

    def observe_pair(
        self,
        *,
        shadow: V23ConversationShadow,
        legacy_state: Any,
        earlier_index: int,
        later_index: int,
        assessment: ResolutionAssessment,
    ) -> ParallelDecisionRecord:
        canonical: AuthorityObservation = self.authority.observe_turn_pair(
            shadow,
            earlier_index,
            later_index,
            assessment=assessment,
        )

        # Live Step-4 semantics: no unresolved-queue pressure is supplied here.
        # This is observation only; no legacy leap_done/correction is called.
        legacy_should_leap, legacy_target = legacy_state.should_leap(0.0)
        record = ParallelDecisionRecord(
            earlier_index=earlier_index,
            later_index=later_index,
            canonical_status=canonical.status,
            canonical_should_reconstruct=canonical.should_reconstruct,
            canonical_h_magnitude=canonical.h_magnitude,
            canonical_theta=canonical.theta,
            assessment_reason=canonical.assessment.reason,
            assessment_assessor=canonical.assessment.assessor,
            legacy_should_leap=bool(legacy_should_leap),
            legacy_target=str(legacy_target),
        )
        self.records.append(record)
        return record
