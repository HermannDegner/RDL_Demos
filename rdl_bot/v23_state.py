"""Canonical Core v2.3 semantic boundary for the rdl_bot migration.

This module intentionally runs beside the legacy bot runtime.  It does not
reinterpret the legacy ``xi_pool`` or ``H_pre/H_post`` as current Core terms.

Canonical path::

    raw event(s)
      -> acquisition under Purpose / B
      -> InteractionSection (bot representation of RIB_B)
      -> interp(M_B, RIB_B)
      -> F

    later raw event(s)
      -> InteractionSection
      -> same pre-update M_B
      -> F'
      -> E = Delta(F, F')
      -> unresolved component only
      -> H

``coverage`` and other missing/unknown observations are kept in a separate
state.  Core xi is not represented by a runtime scalar in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class BoundaryContext:
    boundary_id: str
    purpose: str
    question: Optional[str] = None
    observation_time: Optional[str] = None
    conditions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.boundary_id.strip():
            raise ValueError("boundary_id must be non-empty")
        if not self.purpose.strip():
            raise ValueError("purpose must be non-empty")
        object.__setattr__(self, "conditions", _freeze_mapping(self.conditions))


@dataclass(frozen=True)
class Provenance:
    source: str
    actor: Optional[str] = None
    observed_at: Optional[str] = None
    lineage: Optional[str] = None


@dataclass(frozen=True)
class InteractionSection:
    """Finite, uninterpreted interaction section: bot representation of RIB_B."""

    section_id: str
    context: BoundaryContext
    payload: Mapping[str, Any]
    role: str = "observation"
    provenance: Optional[Provenance] = None

    def __post_init__(self) -> None:
        if not self.section_id.strip():
            raise ValueError("section_id must be non-empty")
        if not self.role.strip():
            raise ValueError("role must be non-empty")
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))


@dataclass(frozen=True)
class InterpretationState:
    """One finite interpreted state F formed from M_B and one InteractionSection."""

    values: Mapping[str, float]
    section_id: str
    model_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values))


@dataclass(frozen=True)
class MismatchObservation:
    """Finite Delta(F, F') observation.  It is not automatically H."""

    values: Mapping[str, float]
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values))

    @property
    def magnitude(self) -> float:
        return max((abs(value) for value in self.values.values()), default=0.0)


class UnresolvedMismatchState:
    """Operational H candidate containing unresolved canonical mismatch only."""

    def __init__(self, *, theta: float = 2.0, decay: float = 1.0) -> None:
        if theta < 0:
            raise ValueError("theta must be non-negative")
        if not 0 <= decay <= 1:
            raise ValueError("decay must be in [0, 1]")
        self.theta = float(theta)
        self.decay = float(decay)
        self.values: dict[str, float] = {}

    def observe(self, mismatch: MismatchObservation, *, unresolved: bool) -> None:
        keys = set(self.values) | set(mismatch.values)
        next_values: dict[str, float] = {}
        for key in keys:
            retained = self.values.get(key, 0.0) * self.decay
            increment = abs(mismatch.values.get(key, 0.0)) if unresolved else 0.0
            next_values[key] = retained + increment
        self.values = next_values

    def restore_snapshot(self, snapshot: Mapping[str, float]) -> None:
        """Restore persisted unresolved-H coordinates after validation.

        A restart restores already-classified state; it does not replay or invent
        E observations.  Values must therefore be finite, non-negative numeric
        magnitudes.  The fixed theta/decay configuration is not changed here.
        """

        restored: dict[str, float] = {}
        for key, raw_value in dict(snapshot).items():
            value = float(raw_value)
            if value < 0 or value != value or value in (float("inf"), float("-inf")):
                raise ValueError("persisted H snapshot values must be finite and non-negative")
            restored[str(key)] = value
        self.values = restored

    @property
    def magnitude(self) -> float:
        return max(self.values.values(), default=0.0)

    @property
    def should_reconstruct(self) -> bool:
        return self.magnitude >= self.theta

    def snapshot(self) -> dict[str, float]:
        return dict(self.values)


class CoverageState:
    """Bot-local observation coverage.  This is neither Core H nor Core xi."""

    def __init__(self) -> None:
        self.missing_inputs = 0
        self.unknown_routes = 0
        self.rejections = 0

    def record_missing(self, count: int = 1) -> None:
        self.missing_inputs += max(0, int(count))

    def record_unknown_route(self, count: int = 1) -> None:
        self.unknown_routes += max(0, int(count))

    def record_rejection(self, count: int = 1) -> None:
        self.rejections += max(0, int(count))

    def snapshot(self) -> dict[str, int]:
        return {
            "missing_inputs": self.missing_inputs,
            "unknown_routes": self.unknown_routes,
            "rejections": self.rejections,
        }


def acquire_text_section(
    *,
    section_id: str,
    text: str,
    context: BoundaryContext,
    role: str = "observation",
    provenance: Optional[Provenance] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> InteractionSection:
    """Acquire a finite text-facing RIB_B section without interpreting it."""

    payload = {"text": text}
    if metadata:
        payload.update(dict(metadata))
    return InteractionSection(
        section_id=section_id,
        context=context,
        payload=payload,
        role=role,
        provenance=provenance,
    )


def interpret_section(
    section: InteractionSection,
    *,
    model_ref: str,
    interpreter: Callable[[InteractionSection], Mapping[str, float]],
) -> InterpretationState:
    """Form F from one finite section using an explicitly supplied M_B-side evaluator."""

    values = dict(interpreter(section))
    return InterpretationState(values=values, section_id=section.section_id, model_ref=model_ref)


def compare_interpretations(
    current: InterpretationState,
    later: InterpretationState,
) -> MismatchObservation:
    """Compute Delta(F, F') without promoting the result into H."""

    if current.model_ref != later.model_ref:
        raise ValueError("F and F' must use the same pre-update model_ref")
    keys = set(current.values) | set(later.values)
    values = {
        key: abs(float(later.values.get(key, 0.0)) - float(current.values.get(key, 0.0)))
        for key in keys
    }
    reasons = tuple(key for key, value in sorted(values.items()) if value > 0)
    return MismatchObservation(values=values, reasons=reasons)
