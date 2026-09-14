"""Candidate Core v2.3 reconstruction authority for rdl_bot.

This module is intentionally non-authoritative for the live CLI until the
migration cutover is explicitly performed.  It provides the Step 6 candidate
path:

    RIB_B(t)     -> F  = interp(M_B(t), RIB_B(t))
    RIB_B(t+Δ)   -> F' = interp(M_B(t), RIB_B(t+Δ))
                     -> E = Delta(F, F')
                     -> provenance-bearing ResolutionAssessment
                     -> canonical H candidate
                     -> fixed theta
                     -> reconstruction eligibility

No API in this module accepts legacy miss/deny/silence counters, unresolved
input queue size, uncertainty, or a Core-xi scalar.  Those signals therefore
cannot alter this authority's threshold by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

try:  # package-style imports
    from .resolution_v23 import ResolutionAssessment
    from .runtime_v23 import V23ConversationShadow
    from .v23_state import MismatchObservation, UnresolvedMismatchState
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from resolution_v23 import ResolutionAssessment  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore
    from v23_state import MismatchObservation, UnresolvedMismatchState  # type: ignore


@dataclass(frozen=True)
class AuthorityObservation:
    """One candidate authority observation without performing a reconstruction."""

    status: str
    mismatch: Optional[MismatchObservation]
    assessment: ResolutionAssessment
    h_magnitude: float
    theta: float
    should_reconstruct: bool

    @property
    def unresolved(self) -> bool:
        return self.assessment.unresolved


class CanonicalLeapAuthority:
    """Non-authoritative candidate for fixed-theta reconstruction eligibility.

    ``theta`` is fixed for the lifetime of this object.  The authority does not
    expose queue pressure or legacy feedback inputs.

    For a temporal comparison, F and F' are both formed by the evaluator frozen
    at the earlier turn.  Therefore mutation of the live graph between turns is
    not itself a reason to drop E.  A changed comparison boundary B is.

    An explicit :class:`ResolutionAssessment` is mandatory.  A raw bool is not a
    sufficient application boundary because it could silently recreate old
    ``deny -> H`` style shortcuts.
    """

    def __init__(self, *, theta: float = 2.0, decay: float = 1.0) -> None:
        self._theta = float(theta)
        self._h = UnresolvedMismatchState(theta=self._theta, decay=decay)

    @property
    def theta(self) -> float:
        return self._theta

    @property
    def h_magnitude(self) -> float:
        return self._h.magnitude

    @property
    def should_reconstruct(self) -> bool:
        return self._h.should_reconstruct

    def h_snapshot(self) -> dict[str, float]:
        return self._h.snapshot()

    def restore_h_snapshot(self, snapshot: Mapping[str, float]) -> None:
        """Restore a persisted canonical H snapshot without replaying fake E events.

        Restart durability should preserve already-classified unresolved state,
        not manufacture a new mismatch sequence.  This method therefore restores
        the finite H coordinates directly after validating them through the
        underlying state object.
        """

        self._h.restore_snapshot(snapshot)

    @staticmethod
    def _require_assessment(assessment: ResolutionAssessment) -> ResolutionAssessment:
        if not isinstance(assessment, ResolutionAssessment):
            raise TypeError("assessment must be a ResolutionAssessment")
        return assessment

    def observe_mismatch(
        self,
        mismatch: MismatchObservation,
        *,
        assessment: ResolutionAssessment,
    ) -> AuthorityObservation:
        """Observe canonical E only through an explicit resolution assessment."""

        assessment = self._require_assessment(assessment)
        self._h.observe(mismatch, unresolved=assessment.unresolved)
        return AuthorityObservation(
            status="observed-unresolved" if assessment.unresolved else "observed-resolved",
            mismatch=mismatch,
            assessment=assessment,
            h_magnitude=self.h_magnitude,
            theta=self.theta,
            should_reconstruct=self.should_reconstruct,
        )

    def observe_turn_pair(
        self,
        shadow: V23ConversationShadow,
        earlier_index: int,
        later_index: int,
        *,
        assessment: ResolutionAssessment,
    ) -> AuthorityObservation:
        """Form canonical E using the earlier frozen evaluator and observe it.

        ``replay_later_under_earlier_model`` forms F' from the later acquired
        section using the evaluator frozen at ``earlier_index``.  It returns
        ``None`` only when the finite comparison boundary itself changed.
        """

        assessment = self._require_assessment(assessment)
        mismatch = shadow.replay_later_under_earlier_model(earlier_index, later_index)
        if mismatch is None:
            return AuthorityObservation(
                status="boundary-changed-no-E",
                mismatch=None,
                assessment=assessment,
                h_magnitude=self.h_magnitude,
                theta=self.theta,
                should_reconstruct=self.should_reconstruct,
            )
        return self.observe_mismatch(mismatch, assessment=assessment)
