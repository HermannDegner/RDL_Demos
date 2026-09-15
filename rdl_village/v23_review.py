"""Finite review gate for Village v2.3 unresolved formation.

This module does not infer unresolved mismatch from magnitude.  It separates:

1. evidence that the current finite village model actually attempted a bounded
   local adjustment;
2. a review candidate restricted to E dimensions supported by that evidence;
3. an explicit finite review that must exclude ordinary temporal change and
   boundary / coverage change before any component may become unresolved.

The result is still read-only evidence.  It does not call the historical
``LeapEngine`` and does not mutate the village policy model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

from .v23_boundary import (
    VillageDifferenceAssessment,
    VillageMismatch,
    assess_village_mismatch,
)


LOCAL_ABSORPTION_STATUSES = (
    "bounded-local-adjustment-observed",
    "no-observed-local-adjustment",
    "confounded-structural-change",
    "not-formed-missing-local-state",
    "not-formed-boundary-change",
)


def _freeze_float_mapping(value: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType({str(key): float(raw) for key, raw in value.items()})


@dataclass(frozen=True)
class VillageLocalAbsorptionEvidence:
    """Purpose-bound audit of the village's bounded local place-model update."""

    status: str
    tick: int
    previous_tick: int | None
    boundary_id: str
    purpose: str
    place_id: str | None
    before: Mapping[str, float] = field(default_factory=dict)
    expected_after: Mapping[str, float] = field(default_factory=dict)
    observed_after: Mapping[str, float] = field(default_factory=dict)
    changed_axes: tuple[str, ...] = ()
    confounded_axes: tuple[str, ...] = ()
    evidence_ref: str = ""

    def __post_init__(self) -> None:
        if self.status not in LOCAL_ABSORPTION_STATUSES:
            raise ValueError(f"unknown local absorption status: {self.status}")
        object.__setattr__(self, "before", _freeze_float_mapping(self.before))
        object.__setattr__(self, "expected_after", _freeze_float_mapping(self.expected_after))
        object.__setattr__(self, "observed_after", _freeze_float_mapping(self.observed_after))
        changed = tuple(str(item) for item in self.changed_axes)
        confounded = tuple(str(item) for item in self.confounded_axes)
        object.__setattr__(self, "changed_axes", changed)
        object.__setattr__(self, "confounded_axes", confounded)
        if self.status == "bounded-local-adjustment-observed":
            if not changed:
                raise ValueError("bounded local adjustment requires at least one changed axis")
            if confounded:
                raise ValueError("bounded local adjustment cannot contain confounded axes")

    @property
    def qualifies_as_finite_attempt(self) -> bool:
        return self.status == "bounded-local-adjustment-observed"


@dataclass(frozen=True)
class VillageUnresolvedReviewCandidate:
    """A finite review candidate; not itself an unresolved classification."""

    candidate_id: str
    agent_name: str
    mismatch: VillageMismatch
    local_absorption: VillageLocalAbsorptionEvidence
    candidate_dimensions: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        dimensions = tuple(str(item) for item in self.candidate_dimensions)
        refs = tuple(str(item) for item in self.evidence_refs if str(item).strip())
        object.__setattr__(self, "candidate_dimensions", dimensions)
        object.__setattr__(self, "evidence_refs", refs)
        if not self.candidate_id or not self.agent_name:
            raise ValueError("review candidate requires id and agent")
        if not self.local_absorption.qualifies_as_finite_attempt:
            raise ValueError("review candidate requires bounded local absorption evidence")
        if not dimensions:
            raise ValueError("review candidate requires at least one supported E dimension")
        invalid = set(dimensions) - set(self.mismatch.nonzero_dimensions)
        if invalid:
            raise ValueError(f"candidate dimensions outside non-zero E: {sorted(invalid)}")
        if not refs:
            raise ValueError("review candidate requires finite evidence references")


def review_village_candidate(
    candidate: VillageUnresolvedReviewCandidate,
    *,
    status: str,
    basis: Sequence[str],
    assessor: str,
    ordinary_temporal_change_excluded: bool = False,
    boundary_or_coverage_change_excluded: bool = False,
    unresolved_dimensions: Sequence[str] = (),
) -> VillageDifferenceAssessment:
    """Perform the explicit finite review required before canonical H.

    ``unresolved-mismatch`` is accepted only when the reviewer explicitly
    excludes ordinary temporal change and boundary / coverage change, and only
    for dimensions already supported by the bounded local-adjustment evidence.
    """

    if status == "unresolved-mismatch":
        if not ordinary_temporal_change_excluded:
            raise ValueError("unresolved review must explicitly exclude ordinary temporal change")
        if not boundary_or_coverage_change_excluded:
            raise ValueError("unresolved review must explicitly exclude boundary / coverage change")
        unresolved = tuple(str(item) for item in unresolved_dimensions)
        if not unresolved:
            raise ValueError("unresolved review requires explicit unresolved dimensions")
        invalid = set(unresolved) - set(candidate.candidate_dimensions)
        if invalid:
            raise ValueError(
                f"unresolved dimensions lack finite absorption evidence: {sorted(invalid)}"
            )
    else:
        if unresolved_dimensions:
            raise ValueError("non-unresolved review cannot name unresolved dimensions")
        unresolved = ()

    finite_basis = tuple(str(item) for item in basis if str(item).strip())
    if not finite_basis:
        raise ValueError("finite review requires a non-empty basis")
    if not assessor:
        raise ValueError("finite review requires an assessor")

    return assess_village_mismatch(
        candidate.mismatch,
        status=status,
        basis=finite_basis,
        assessor=assessor,
        unresolved_dimensions=unresolved,
    )
