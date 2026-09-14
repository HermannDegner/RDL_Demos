"""Action gate between canonical reconstruction authority and mutation execution.

The gate deliberately does *not* choose a node to revise.  Canonical H answers
whether reconstruction is eligible under the current finite comparison; target
selection is a separate application/planning problem and must not fall back to
legacy hot-node load by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # package-style imports
    from .authority_v23 import AuthorityObservation
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from authority_v23 import AuthorityObservation  # type: ignore


@dataclass(frozen=True)
class ReconstructionRequest:
    """Canonical request to enter a reconstruction/planning phase.

    ``target_ref`` intentionally starts as ``None``.  A later planner may derive
    a target from canonical evidence/provenance, but this gate never imports or
    queries ``LegacyFeedbackLoadState``.
    """

    status: str
    h_magnitude: float
    theta: float
    mismatch_reasons: tuple[str, ...]
    assessment_reason: str
    assessment_assessor: str
    evidence_refs: tuple[str, ...]
    target_ref: None = None


def _mismatch_reasons(observation: AuthorityObservation) -> tuple[str, ...]:
    """Return explicit reasons, falling back to non-zero mismatch dimensions."""

    mismatch = observation.mismatch
    if mismatch is None:
        return ()
    if mismatch.reasons:
        return tuple(mismatch.reasons)
    return tuple(
        key
        for key, value in sorted(mismatch.values.items())
        if abs(float(value)) > 0.0
    )


class CanonicalActionGate:
    """Translate one authority observation into reconstruction eligibility."""

    def request(self, observation: AuthorityObservation) -> ReconstructionRequest | None:
        if not isinstance(observation, AuthorityObservation):
            raise TypeError("observation must be an AuthorityObservation")
        if not observation.unresolved:
            return None
        if not observation.should_reconstruct:
            return None
        if observation.mismatch is None:
            return None

        return ReconstructionRequest(
            status="canonical-reconstruction-requested",
            h_magnitude=observation.h_magnitude,
            theta=observation.theta,
            mismatch_reasons=_mismatch_reasons(observation),
            assessment_reason=observation.assessment.reason,
            assessment_assessor=observation.assessment.assessor,
            evidence_refs=tuple(observation.assessment.evidence_refs),
        )
