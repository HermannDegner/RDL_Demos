"""Live read-only Core v2.3 observer for ``rdl_village``.

The historical village runtime remains authoritative at this stage.  This
sidecar attaches to existing NPC ``update_boundary`` calls and observes a
finite, purpose-qualified section without reading from or writing to legacy
``LocalLoadVector``, ``ExplorationState`` or ``LeapEngine`` authority.

The observer forms temporal F / F' only while finite B / Purpose / dimensions /
conditions remain stable.  Missing coverage breaks the window.  Non-zero E is
left pending by default and never enters H automatically.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from types import MethodType, MappingProxyType
from typing import Mapping, Optional

from .v23_boundary import (
    VillageBoundary,
    VillageBoundaryChange,
    VillageCoverageError,
    acquire_village_section,
    assess_village_mismatch,
    compare_village_interpretations,
    interpret_village_section,
)


VILLAGE_OBSERVER_DIMENSIONS = (
    "body_crisis",
    "discomfort",
    "visible_agents",
    "visible_resources",
)

DEFAULT_OBSERVER_COEFFICIENTS = MappingProxyType(
    {
        "body_crisis": 1.0,
        "discomfort": 1.0,
        "visible_agents": 0.25,
        "visible_resources": 0.25,
    }
)


def _finite_or_missing(value) -> Optional[float]:
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


class VillageCanonicalObserver:
    """Read-only finite temporal comparison sidecar for live village agents."""

    def __init__(self, coefficients: Optional[Mapping[str, float]] = None) -> None:
        source = DEFAULT_OBSERVER_COEFFICIENTS if coefficients is None else coefficients
        missing = tuple(key for key in VILLAGE_OBSERVER_DIMENSIONS if key not in source)
        if missing:
            raise ValueError(f"observer coefficients missing selected dimensions: {missing}")
        self.coefficients = MappingProxyType(
            {key: float(source[key]) for key in VILLAGE_OBSERVER_DIMENSIONS}
        )
        self.model_ref = "village-live-observer:M_B:v1"
        self._previous = {}
        self._records = defaultdict(lambda: deque(maxlen=256))
        self._counts = defaultdict(Counter)

    def _boundary_for(self, agent, perception, tick: int) -> VillageBoundary:
        return VillageBoundary(
            boundary_id=f"village:{agent.name}:local-observation",
            purpose="npc_local_interpretation",
            dimensions=VILLAGE_OBSERVER_DIMENSIONS,
            observation_time=f"tick:{tick}",
            conditions={
                "place": perception.place_id,
                "band": perception.band,
            },
        )

    def _values_for(self, agent, perception) -> dict[str, float]:
        candidates = {
            "body_crisis": _finite_or_missing(agent.body.crisis()),
            "discomfort": _finite_or_missing(perception.discomfort),
            "visible_agents": _finite_or_missing(len(perception.visible_agents)),
            "visible_resources": _finite_or_missing(len(perception.visible_resources)),
        }
        return {key: value for key, value in candidates.items() if value is not None}

    def capture(self, agent, perception, tick: int) -> None:
        name = agent.name
        boundary = self._boundary_for(agent, perception, tick)
        section = acquire_village_section(
            section_id=f"village:{name}:tick:{tick}",
            boundary=boundary,
            values=self._values_for(agent, perception),
            role="live-observation",
            source_ref=f"simulation.step:{tick}:{name}",
        )
        try:
            current = interpret_village_section(
                section,
                model_ref=self.model_ref,
                coefficients=self.coefficients,
            )
        except VillageCoverageError as exc:
            self._previous.pop(name, None)
            self._counts[name]["coverage-not-formed"] += 1
            self._records[name].append(
                {
                    "tick": tick,
                    "formed": False,
                    "status": "coverage-not-formed",
                    "reason": str(exc),
                    "coverage": section.coverage,
                }
            )
            return

        previous = self._previous.get(name)
        if previous is None:
            self._counts[name]["window-started"] += 1
            self._records[name].append(
                {
                    "tick": tick,
                    "formed": False,
                    "status": "window-started",
                    "context": current.context_key,
                }
            )
            self._previous[name] = current
            return

        try:
            mismatch = compare_village_interpretations(previous, current)
        except (VillageBoundaryChange, VillageCoverageError) as exc:
            self._counts[name]["boundary-or-coverage-change"] += 1
            self._records[name].append(
                {
                    "tick": tick,
                    "formed": False,
                    "status": "boundary-or-coverage-change",
                    "reason": str(exc),
                    "previous_context": previous.context_key,
                    "current_context": current.context_key,
                }
            )
            self._previous[name] = current
            return

        assessment = assess_village_mismatch(mismatch)
        self._counts[name][assessment.status] += 1
        self._records[name].append(
            {
                "tick": tick,
                "formed": True,
                "status": assessment.status,
                "E": dict(mismatch.values),
                "magnitude": mismatch.magnitude,
                "eligibleForH": assessment.eligible_for_h,
                "modelRef": mismatch.model_ref,
                "boundaryId": mismatch.boundary_id,
                "purpose": mismatch.purpose,
                "dimensions": mismatch.dimensions,
            }
        )
        self._previous[name] = current

    def records_for(self, agent_name: str):
        return tuple(dict(item) for item in self._records.get(agent_name, ()))

    def counts_for(self, agent_name: str):
        return dict(self._counts.get(agent_name, {}))

    def snapshot(self):
        return {
            "modelRef": self.model_ref,
            "dimensions": VILLAGE_OBSERVER_DIMENSIONS,
            "coefficients": dict(self.coefficients),
            "agents": {
                name: {
                    "counts": dict(self._counts[name]),
                    "latest": dict(records[-1]) if records else None,
                }
                for name, records in self._records.items()
            },
            "authority": "read-only-sidecar",
        }


def attach_v23_observer(simulation, coefficients: Optional[Mapping[str, float]] = None):
    """Attach the canonical observer without altering village policy authority.

    Attachment is explicit and opt-in.  Each NPC's existing ``update_boundary``
    method is wrapped so the sidecar sees the same finite perception passed by
    ``VillageSimulation.step``.  The original method is then called unchanged.
    """

    existing = getattr(simulation, "v23_observer", None)
    if existing is not None:
        return existing

    observer = VillageCanonicalObserver(coefficients=coefficients)
    simulation.v23_observer = observer

    for agent in simulation.agents:
        original = agent.update_boundary

        def observed_update(self, perception, _original=original, _observer=observer):
            _observer.capture(self, perception, perception.t)
            return _original(perception)

        agent.update_boundary = MethodType(observed_update, agent)

    return observer
