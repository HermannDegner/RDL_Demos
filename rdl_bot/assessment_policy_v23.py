"""Conservative runtime policy for forming canonical resolution assessments.

The policy is intentionally asymmetric:

- zero canonical mismatch can be classified as resolved automatically;
- non-zero canonical mismatch remains pending by default;
- pending mismatch can become unresolved only through an explicit
  provenance-bearing promotion step.

Legacy feedback events (deny/miss/silence), queue size, uncertainty and local
pressure are not accepted by this module.  This prevents a live migration from
silently recreating pre-v2.3 shortcuts such as ``deny -> H``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

try:  # package-style imports
    from .resolution_v23 import ResolutionAssessment
    from .v23_state import MismatchObservation
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from resolution_v23 import ResolutionAssessment  # type: ignore
    from v23_state import MismatchObservation  # type: ignore


def _unique_refs(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        ref = str(value)
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return tuple(ordered)


@dataclass(frozen=True)
class ResolutionCandidate:
    """Runtime classification result before canonical H is allowed to update."""

    status: str
    mismatch: MismatchObservation
    evidence_refs: tuple[str, ...] = ()
    assessment: Optional[ResolutionAssessment] = None

    def __post_init__(self) -> None:
        if self.status not in {"resolved", "pending"}:
            raise ValueError("status must be 'resolved' or 'pending'")
        if self.status == "resolved" and self.assessment is None:
            raise ValueError("resolved candidate requires an assessment")
        if self.status == "pending" and self.assessment is not None:
            raise ValueError("pending candidate must not contain an assessment")
        object.__setattr__(self, "evidence_refs", _unique_refs(self.evidence_refs))

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"


def classify_mismatch(
    mismatch: MismatchObservation,
    *,
    evidence_refs: Iterable[str] = (),
    assessor: str = "rdl_bot.assessment_policy_v23",
) -> ResolutionCandidate:
    """Classify canonical E without manufacturing unresolved H.

    A zero mismatch is mechanically resolved because there is no remaining
    Delta(F, F').  Any non-zero mismatch is merely pending.  Magnitude alone is
    not evidence that the mismatch is unresolved.
    """

    refs = _unique_refs(evidence_refs)
    if mismatch.magnitude == 0.0:
        assessment = ResolutionAssessment.resolved(
            reason="canonical mismatch magnitude is zero under the comparison contract",
            assessor=assessor,
            evidence_refs=refs,
        )
        return ResolutionCandidate(
            status="resolved",
            mismatch=mismatch,
            evidence_refs=refs,
            assessment=assessment,
        )
    return ResolutionCandidate(
        status="pending",
        mismatch=mismatch,
        evidence_refs=refs,
    )


def promote_pending_to_unresolved(
    candidate: ResolutionCandidate,
    *,
    reason: str,
    assessor: str,
    evidence_refs: Iterable[str] = (),
) -> ResolutionAssessment:
    """Explicitly promote one pending canonical mismatch to unresolved.

    The caller must provide its own reason and assessor.  No legacy feedback
    field is accepted here, and this function cannot promote an already-resolved
    zero mismatch.  The original comparison provenance is retained and merged
    with any additional review evidence.
    """

    if not candidate.is_pending:
        raise ValueError("only a pending non-zero mismatch can be promoted")
    refs = _unique_refs((*candidate.evidence_refs, *tuple(str(ref) for ref in evidence_refs)))
    return ResolutionAssessment.unresolved_case(
        reason=reason,
        assessor=assessor,
        evidence_refs=refs,
    )
