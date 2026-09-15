"""Core v2.3 finite semantic boundary for the village migration.

The existing village runtime predates the current RIB/RIB_B model and still
contains historical local-load and exploration mechanisms.  This module keeps
canonical roles separate from those mechanisms:

- finite ``VillageBoundary`` selects Purpose / dimensions / conditions;
- ``VillageRIBSection`` holds only actually acquired values;
- F and F' are formed with the same explicit pre-update ``model_ref`` and
  coefficient set;
- missing coverage never becomes numeric zero;
- non-zero E is pending unless a finite assessment classifies it;
- only explicitly assessed unresolved mismatch is eligible for canonical H.

This module does not grant reconstruction authority to the historical village
``LeapEngine``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence


ASSESSMENT_STATUSES = (
    "zero-difference",
    "pending-assessment",
    "ordinary-temporal-change",
    "boundary-or-coverage-change",
    "resolved-difference",
    "unresolved-mismatch",
)


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _freeze_float_mapping(value: Mapping[str, float]) -> Mapping[str, float]:
    frozen: dict[str, float] = {}
    for key, raw in value.items():
        numeric = float(raw)
        if not math.isfinite(numeric):
            raise ValueError(f"non-finite finite-section value: {key}")
        frozen[str(key)] = numeric
    return MappingProxyType(frozen)


class VillageCoverageError(ValueError):
    """The selected finite dimensions were not actually all observed."""


class VillageBoundaryChange(ValueError):
    """F and F' do not belong to the same finite B / Purpose context."""


@dataclass(frozen=True)
class VillageBoundary:
    boundary_id: str
    purpose: str
    dimensions: tuple[str, ...] = ()
    observation_time: Optional[str] = None
    conditions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        dimensions = tuple(str(item) for item in self.dimensions)
        if not self.boundary_id or not self.purpose:
            raise ValueError("finite boundary requires boundary_id and purpose")
        if not dimensions:
            raise ValueError("finite boundary requires selected dimensions")
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("finite boundary dimensions must be unique")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "conditions", _freeze(self.conditions))

    @property
    def context_key(self) -> tuple[Any, ...]:
        return (
            self.boundary_id,
            self.purpose,
            self.dimensions,
            tuple(sorted(self.conditions.items())),
        )


@dataclass(frozen=True)
class VillageRIBSection:
    section_id: str
    boundary: VillageBoundary
    values: Mapping[str, float]
    role: str = "observation"
    source_ref: Optional[str] = None

    def __post_init__(self) -> None:
        values = _freeze_float_mapping(self.values)
        extras = set(values) - set(self.boundary.dimensions)
        if extras:
            raise ValueError(f"section contains dimensions outside finite B: {sorted(extras)}")
        object.__setattr__(self, "values", values)

    @property
    def coverage(self) -> tuple[str, ...]:
        return tuple(key for key in self.boundary.dimensions if key in self.values)

    @property
    def missing_dimensions(self) -> tuple[str, ...]:
        return tuple(key for key in self.boundary.dimensions if key not in self.values)


@dataclass(frozen=True)
class VillageInterpretation:
    values: Mapping[str, float]
    section_id: str
    model_ref: str
    boundary_id: str
    purpose: str
    dimensions: tuple[str, ...]
    conditions: Mapping[str, Any]
    coverage: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_float_mapping(self.values))
        object.__setattr__(self, "conditions", _freeze(self.conditions))

    @property
    def context_key(self) -> tuple[Any, ...]:
        return (
            self.boundary_id,
            self.purpose,
            self.dimensions,
            tuple(sorted(self.conditions.items())),
        )


@dataclass(frozen=True)
class VillageMismatch:
    values: Mapping[str, float]
    boundary_id: str
    purpose: str
    dimensions: tuple[str, ...]
    current_section_id: str
    later_section_id: str
    model_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_float_mapping(self.values))

    @property
    def magnitude(self) -> float:
        """Demo-local max norm; not asserted as the unique Core norm."""

        return max((abs(value) for value in self.values.values()), default=0.0)


@dataclass(frozen=True)
class VillageDifferenceAssessment:
    mismatch: VillageMismatch
    status: str
    basis: tuple[str, ...] = ()
    assessor: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in ASSESSMENT_STATUSES:
            raise ValueError(f"unknown village assessment status: {self.status}")
        basis = tuple(str(item) for item in self.basis if str(item).strip())
        object.__setattr__(self, "basis", basis)
        if self.mismatch.magnitude == 0.0 and self.status != "zero-difference":
            raise ValueError("zero E cannot be classified as a non-zero assessment")
        if self.mismatch.magnitude > 0.0 and self.status == "zero-difference":
            raise ValueError("non-zero E cannot be classified as zero-difference")
        if self.status not in {"zero-difference", "pending-assessment"} and not basis:
            raise ValueError("explicit non-zero assessment requires a finite basis")
        if self.status == "unresolved-mismatch" and not self.assessor:
            raise ValueError("unresolved assessment requires an explicit assessor")

    @property
    def eligible_for_h(self) -> bool:
        return self.status == "unresolved-mismatch"


class VillageUnresolvedH:
    """Read-only migration-sidecar H: reviewed unresolved canonical E only."""

    def __init__(self, theta: float = 1.0, decay: float = 1.0) -> None:
        self.theta = float(theta)
        self.decay = float(decay)
        self.values: dict[str, float] = {}

    def observe(self, assessment: VillageDifferenceAssessment) -> None:
        mismatch = assessment.mismatch
        keys = set(self.values) | set(mismatch.values)
        self.values = {
            key: self.values.get(key, 0.0) * self.decay
            + (abs(mismatch.values.get(key, 0.0)) if assessment.eligible_for_h else 0.0)
            for key in keys
        }

    @property
    def magnitude(self) -> float:
        return max(self.values.values(), default=0.0)

    @property
    def should_reconstruct(self) -> bool:
        return self.magnitude >= self.theta


class ExplorationState:
    """Village-local search pressure and unresolved queue; explicitly not Core xi."""

    def __init__(self, *, maximum: float = 1.0, decay: float = 0.95) -> None:
        self.maximum = max(0.0, float(maximum))
        self.decay = min(1.0, max(0.0, float(decay)))
        self.value = 0.0
        self.unresolved: list[Any] = []

    def add_pressure(self, amount: float) -> None:
        self.value = min(self.maximum, max(0.0, self.value + max(0.0, amount)))

    def decay_tick(self) -> None:
        self.value *= self.decay

    @property
    def pressure(self) -> float:
        if self.maximum <= 0:
            return 0.0
        return min(1.0, self.value / self.maximum)

    def hold(self, value: Any) -> None:
        self.unresolved.append(value)


def acquire_village_section(
    *,
    section_id: str,
    boundary: VillageBoundary,
    values: Mapping[str, float],
    role: str = "observation",
    source_ref: Optional[str] = None,
) -> VillageRIBSection:
    """Create a finite RIB_B-like section from actually selected observations."""

    return VillageRIBSection(
        section_id=section_id,
        boundary=boundary,
        values=values,
        role=role,
        source_ref=source_ref,
    )


def interpret_village_section(
    section: VillageRIBSection,
    *,
    model_ref: str,
    coefficients: Mapping[str, float],
) -> VillageInterpretation:
    """Form F under one explicit finite pre-update evaluator.

    Missing selected dimensions abort formation.  They are never substituted
    with zero.  Coefficients must also be explicit for every selected dimension.
    """

    missing = section.missing_dimensions
    if missing:
        raise VillageCoverageError(f"finite section missing selected dimensions: {missing}")
    missing_coefficients = tuple(
        key for key in section.boundary.dimensions if key not in coefficients
    )
    if missing_coefficients:
        raise VillageCoverageError(
            f"finite evaluator missing coefficients: {missing_coefficients}"
        )
    values = {
        key: float(section.values[key]) * float(coefficients[key])
        for key in section.boundary.dimensions
    }
    return VillageInterpretation(
        values=values,
        section_id=section.section_id,
        model_ref=model_ref,
        boundary_id=section.boundary.boundary_id,
        purpose=section.boundary.purpose,
        dimensions=section.boundary.dimensions,
        conditions=section.boundary.conditions,
        coverage=section.coverage,
    )


def compare_village_interpretations(
    current: VillageInterpretation,
    later: VillageInterpretation,
) -> VillageMismatch:
    if current.model_ref != later.model_ref:
        raise ValueError("F and F' must use the same pre-update model_ref")
    if current.context_key != later.context_key:
        raise VillageBoundaryChange("F and F' must remain within the same finite B / Purpose")
    if current.coverage != later.coverage or current.coverage != current.dimensions:
        raise VillageCoverageError("F and F' require stable complete selected coverage")
    return VillageMismatch(
        values={
            key: abs(float(later.values[key]) - float(current.values[key]))
            for key in current.dimensions
        },
        boundary_id=current.boundary_id,
        purpose=current.purpose,
        dimensions=current.dimensions,
        current_section_id=current.section_id,
        later_section_id=later.section_id,
        model_ref=current.model_ref,
    )


def assess_village_mismatch(
    mismatch: VillageMismatch,
    *,
    status: Optional[str] = None,
    basis: Sequence[str] = (),
    assessor: Optional[str] = None,
) -> VillageDifferenceAssessment:
    """Classify finite E without promoting magnitude to unresolved by itself."""

    if mismatch.magnitude == 0.0:
        resolved_status = "zero-difference" if status is None else status
    else:
        resolved_status = "pending-assessment" if status is None else status
    return VillageDifferenceAssessment(
        mismatch=mismatch,
        status=resolved_status,
        basis=tuple(basis),
        assessor=assessor,
    )
