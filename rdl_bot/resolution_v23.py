"""Explicit resolution classification for canonical rdl_bot mismatch handling.

Core v2.3 says that only unresolved canonical mismatch contributes to H.  This
module makes that classification an explicit, provenance-bearing application
boundary instead of a boolean inferred from legacy feedback events.

There is deliberately no helper such as ``from_deny`` / ``from_miss`` here.
Legacy user-feedback events can be evidence in a higher-level assessment, but
they are not themselves a canonical unresolved decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ResolutionAssessment:
    unresolved: bool
    reason: str
    assessor: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("resolution assessment reason must be non-empty")
        if not self.assessor.strip():
            raise ValueError("resolution assessment assessor must be non-empty")

    @classmethod
    def resolved(
        cls,
        *,
        reason: str,
        assessor: str,
        evidence_refs: Iterable[str] = (),
    ) -> "ResolutionAssessment":
        return cls(
            unresolved=False,
            reason=reason,
            assessor=assessor,
            evidence_refs=tuple(str(ref) for ref in evidence_refs),
        )

    @classmethod
    def unresolved_case(
        cls,
        *,
        reason: str,
        assessor: str,
        evidence_refs: Iterable[str] = (),
    ) -> "ResolutionAssessment":
        return cls(
            unresolved=True,
            reason=reason,
            assessor=assessor,
            evidence_refs=tuple(str(ref) for ref in evidence_refs),
        )
