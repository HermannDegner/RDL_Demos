"""Candidate Core v2.3 reconstruction authority for rdl_bot.

This module is intentionally non-authoritative for the live CLI until the
migration cutover is explicitly performed.  It provides the Step 6 candidate
path:

    same-pre-update F / F'
        -> E = Delta(F, F')
        -> explicit unresolved classification
        -> canonical H candidate
        -> fixed theta
        -> reconstruction eligibility

No API in this module accepts legacy miss/deny/silence counters, unresolved
input queue size, uncertainty, or a Core-xi scalar.  Those signals therefore
cannot alter this authority's threshold by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:  # package-style imports
    from .runtime_v23 import V23ConversationShadow
    from .v23_state import MismatchObservation, UnresolvedMismatchState
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from runtime_v23 import V23ConversationShadow  # type: ignore
    from v23_state import MismatchObservation, UnresolvedMismatchState  # type: ignore


@dataclass(frozen=True)
class AuthorityObservation:
    """One candidate authority observation without performing a reconstruction."""

    status: str
    mismatch: Optional[MismatchObservation]
    unresolved: bool
    h_magnitude: float
    theta: float
    should_reconstruct: bool


class CanonicalLeapAuthority:
    """Non-authoritative candidate for fixed-theta reconstruction eligibility.

    ``theta`` is fixed for the lifetime of this object.  The authority does not
    expose queue pressure or legacy feedback inputs.  Model-ref drift is treated
    as non-comparable: it produces no canonical E and therefore no H update.
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

    def observe_mismatch(
        self,
        mismatch: MismatchObservation,
        *,
        unresolved: bool,
    ) -> AuthorityObservation:
        """Observe canonical E only after an explicit unresolved classification."""

        self._h.observe(mismatch, unresolved=unresolved)
        return AuthorityObservation(
            status="observed-unresolved" if unresolved else "observed-resolved",
            mismatch=mismatch,
            unresolved=bool(unresolved),
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
        unresolved: bool,
    ) -> AuthorityObservation:
        """Compare two shadow input states and update H only if comparison is valid.

        ``V23ConversationShadow.compare_inputs`` returns ``None`` when the two
        observations do not share the same frozen pre-response model_ref.  Such
        a pair is not converted into an error surrogate and does not update H.
        """

        mismatch = shadow.compare_inputs(earlier_index, later_index)
        if mismatch is None:
            return AuthorityObservation(
                status="model-changed-no-E",
                mismatch=None,
                unresolved=bool(unresolved),
                h_magnitude=self.h_magnitude,
                theta=self.theta,
                should_reconstruct=self.should_reconstruct,
            )
        return self.observe_mismatch(mismatch, unresolved=unresolved)
