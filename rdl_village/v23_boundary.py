"""Core v2.3 semantic boundary for the village migration.

The existing village runtime predates the RIB/RIB_B model and still contains
``XiPool`` and several heat metaphors.  This module defines the target semantic
roles without changing the existing simulation behaviour yet.

Village-local exploration pressure, unresolved outcome queues, boredom, fear,
and dialogue load remain useful model variables, but none of them is Core xi by
identity.  Likewise, Core H is reserved here for unresolved canonical
Delta(F, F') only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class VillageBoundary:
    boundary_id: str
    purpose: str
    observation_time: Optional[str] = None
    conditions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", _freeze(self.conditions))


@dataclass(frozen=True)
class VillageRIBSection:
    section_id: str
    boundary: VillageBoundary
    values: Mapping[str, float]
    role: str = "observation"
    source_ref: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze(self.values))


@dataclass(frozen=True)
class VillageInterpretation:
    values: Mapping[str, float]
    section_id: str
    model_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze(self.values))


@dataclass(frozen=True)
class VillageMismatch:
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze(self.values))

    @property
    def magnitude(self) -> float:
        return max((abs(value) for value in self.values.values()), default=0.0)


class VillageUnresolvedH:
    """Core-H candidate for the village: unresolved canonical mismatch only."""

    def __init__(self, theta: float = 1.0, decay: float = 1.0) -> None:
        self.theta = float(theta)
        self.decay = float(decay)
        self.values: dict[str, float] = {}

    def observe(self, mismatch: VillageMismatch, *, unresolved: bool) -> None:
        keys = set(self.values) | set(mismatch.values)
        self.values = {
            key: self.values.get(key, 0.0) * self.decay
            + (abs(mismatch.values.get(key, 0.0)) if unresolved else 0.0)
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
    """Create a finite RIB_B-like section from already selected village observations."""

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
    """Small deterministic M_B-side interpretation used for migration tests."""

    values = {
        key: float(value) * float(coefficients.get(key, 1.0))
        for key, value in section.values.items()
    }
    return VillageInterpretation(values=values, section_id=section.section_id, model_ref=model_ref)


def compare_village_interpretations(
    current: VillageInterpretation,
    later: VillageInterpretation,
) -> VillageMismatch:
    if current.model_ref != later.model_ref:
        raise ValueError("F and F' must use the same pre-update model_ref")
    keys = set(current.values) | set(later.values)
    return VillageMismatch(values={
        key: abs(float(later.values.get(key, 0.0)) - float(current.values.get(key, 0.0)))
        for key in keys
    })
