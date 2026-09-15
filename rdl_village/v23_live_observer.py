"""Live read-only Core v2.3 observer for ``rdl_village``.

The historical village runtime remains authoritative.  This sidecar observes a
finite purpose-qualified interaction section, audits bounded local place-model
updates separately from E formation, and allows only explicit finite reviews to
feed canonical-H diagnostic state.

No legacy ``LocalLoadVector``, ``ExplorationState`` or ``LeapEngine`` value is
used as canonical E / H / xi / theta evidence, and this module never writes back
to village policy authority.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from types import MethodType, MappingProxyType
from typing import Mapping, Optional, Sequence

from .v23_boundary import (
    VillageBoundary,
    VillageBoundaryChange,
    VillageCoverageError,
    VillageUnresolvedH,
    acquire_village_section,
    assess_village_mismatch,
    compare_village_interpretations,
    interpret_village_section,
)
from .v23_review import (
    VillageLocalAbsorptionEvidence,
    VillageUnresolvedReviewCandidate,
    review_village_candidate,
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

# These are existing village-local place-model update axes.  Their update laws
# are audited here as a purpose-bound demo contract, not promoted to Core laws.
LOCAL_MODEL_AXES = (
    "comfort",
    "social_expectation",
    "resource_expectation",
)

OBSERVATION_TO_LOCAL_AXIS = MappingProxyType(
    {
        "discomfort": "comfort",
        "visible_agents": "social_expectation",
        "visible_resources": "resource_expectation",
    }
)

LOCAL_UPDATE_EPSILON = 1e-12


def _finite_or_missing(value) -> Optional[float]:
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class VillageCanonicalObserver:
    """Read-only finite comparison / review sidecar for live village agents."""

    def __init__(
        self,
        coefficients: Optional[Mapping[str, float]] = None,
        *,
        theta: float = 1.0,
    ) -> None:
        source = DEFAULT_OBSERVER_COEFFICIENTS if coefficients is None else coefficients
        missing = tuple(key for key in VILLAGE_OBSERVER_DIMENSIONS if key not in source)
        if missing:
            raise ValueError(f"observer coefficients missing selected dimensions: {missing}")
        self.coefficients = MappingProxyType(
            {key: float(source[key]) for key in VILLAGE_OBSERVER_DIMENSIONS}
        )
        self.theta = float(theta)
        if not math.isfinite(self.theta) or self.theta < 0.0:
            raise ValueError("observer theta must be a finite non-negative demo-local threshold")
        self.model_ref = "village-live-observer:M_B:v1"
        self._previous = {}
        self._local_baseline = {}
        self._records = defaultdict(lambda: deque(maxlen=256))
        self._counts = defaultdict(Counter)
        self._review_candidates = defaultdict(lambda: deque(maxlen=128))
        self._reviews = defaultdict(lambda: deque(maxlen=128))
        self._reviewed_candidate_ids = defaultdict(set)
        self._h = {}

    def _h_for(self, agent_name: str) -> VillageUnresolvedH:
        if agent_name not in self._h:
            self._h[agent_name] = VillageUnresolvedH(theta=self.theta, decay=1.0)
        return self._h[agent_name]

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

    def _local_model_snapshot(self, agent, perception) -> Optional[dict[str, float]]:
        place_id = perception.place_id
        if not place_id:
            return None
        meaning = agent.prediction_field.places.get(place_id)
        if meaning is None:
            return None
        values = {
            "comfort": _finite_or_missing(meaning.comfort),
            "social_expectation": _finite_or_missing(meaning.social_expectation),
            "resource_expectation": _finite_or_missing(meaning.resource_expectation),
        }
        if any(value is None for value in values.values()):
            return None
        return {key: float(values[key]) for key in LOCAL_MODEL_AXES}

    def _expected_local_update(self, before: Mapping[str, float], perception) -> dict[str, float]:
        usable = sum(
            1 for item in perception.visible_resources if getattr(item, "state", None) == "available"
        )
        return {
            "comfort": _clamp(
                before["comfort"] * 0.97
                + (0.04 if float(perception.discomfort) < 0.15 else -0.03),
                -1.0,
                1.0,
            ),
            "social_expectation": _clamp(
                before["social_expectation"] * 0.96
                + len(perception.visible_agents) * 0.03,
                0.0,
                1.0,
            ),
            "resource_expectation": _clamp(
                before["resource_expectation"] * 0.95 + usable * 0.04,
                0.0,
                1.0,
            ),
        }

    def _audit_local_absorption(
        self,
        agent,
        perception,
        boundary: VillageBoundary,
        tick: int,
    ) -> VillageLocalAbsorptionEvidence:
        name = agent.name
        observed_after = self._local_model_snapshot(agent, perception)
        previous = self._local_baseline.get(name)
        current_context = boundary.context_key

        if observed_after is None:
            evidence = VillageLocalAbsorptionEvidence(
                status="not-formed-missing-local-state",
                tick=tick,
                previous_tick=previous["tick"] if previous else None,
                boundary_id=boundary.boundary_id,
                purpose=boundary.purpose,
                place_id=perception.place_id,
                evidence_ref=f"village-local-update:{name}:{tick}",
            )
            self._local_baseline.pop(name, None)
            return evidence

        if previous is None:
            evidence = VillageLocalAbsorptionEvidence(
                status="not-formed-missing-local-state",
                tick=tick,
                previous_tick=None,
                boundary_id=boundary.boundary_id,
                purpose=boundary.purpose,
                place_id=perception.place_id,
                observed_after=observed_after,
                evidence_ref=f"village-local-update:{name}:{tick}",
            )
            self._local_baseline[name] = {
                "tick": tick,
                "context": current_context,
                "values": dict(observed_after),
            }
            return evidence

        if previous["context"] != current_context:
            evidence = VillageLocalAbsorptionEvidence(
                status="not-formed-boundary-change",
                tick=tick,
                previous_tick=previous["tick"],
                boundary_id=boundary.boundary_id,
                purpose=boundary.purpose,
                place_id=perception.place_id,
                before=previous["values"],
                observed_after=observed_after,
                evidence_ref=f"village-local-update:{name}:{tick}",
            )
            self._local_baseline[name] = {
                "tick": tick,
                "context": current_context,
                "values": dict(observed_after),
            }
            return evidence

        before = previous["values"]
        expected_after = self._expected_local_update(before, perception)
        confounded_axes = tuple(
            axis
            for axis in LOCAL_MODEL_AXES
            if abs(observed_after[axis] - expected_after[axis]) > LOCAL_UPDATE_EPSILON
        )
        changed_axes = tuple(
            axis
            for axis in LOCAL_MODEL_AXES
            if abs(observed_after[axis] - before[axis]) > LOCAL_UPDATE_EPSILON
        )

        if confounded_axes:
            status = "confounded-structural-change"
        elif changed_axes:
            status = "bounded-local-adjustment-observed"
        else:
            status = "no-observed-local-adjustment"

        evidence = VillageLocalAbsorptionEvidence(
            status=status,
            tick=tick,
            previous_tick=previous["tick"],
            boundary_id=boundary.boundary_id,
            purpose=boundary.purpose,
            place_id=perception.place_id,
            before=before,
            expected_after=expected_after,
            observed_after=observed_after,
            changed_axes=changed_axes,
            confounded_axes=confounded_axes,
            evidence_ref=f"village-local-update:{name}:{tick}",
        )
        self._local_baseline[name] = {
            "tick": tick,
            "context": current_context,
            "values": dict(observed_after),
        }
        return evidence

    def _candidate_for(self, agent_name, mismatch, absorption):
        if not absorption.qualifies_as_finite_attempt:
            return None
        supported = tuple(
            dimension
            for dimension in mismatch.nonzero_dimensions
            if OBSERVATION_TO_LOCAL_AXIS.get(dimension) in absorption.changed_axes
        )
        if not supported:
            return None
        candidate_id = f"village-review:{agent_name}:{mismatch.later_section_id}"
        candidate = VillageUnresolvedReviewCandidate(
            candidate_id=candidate_id,
            agent_name=agent_name,
            mismatch=mismatch,
            local_absorption=absorption,
            candidate_dimensions=supported,
            evidence_refs=(
                mismatch.current_section_id,
                mismatch.later_section_id,
                absorption.evidence_ref,
            ),
        )
        self._review_candidates[agent_name].append(candidate)
        self._counts[agent_name]["review-candidate"] += 1
        return candidate

    def capture(self, agent, perception, tick: int) -> None:
        name = agent.name
        boundary = self._boundary_for(agent, perception, tick)
        absorption = self._audit_local_absorption(agent, perception, boundary, tick)
        self._counts[name][f"local:{absorption.status}"] += 1

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
                    "localAbsorption": absorption.status,
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
                    "localAbsorption": absorption.status,
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
                    "localAbsorption": absorption.status,
                }
            )
            self._previous[name] = current
            return

        assessment = assess_village_mismatch(mismatch)
        candidate = self._candidate_for(name, mismatch, absorption)
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
                "localAbsorption": absorption.status,
                "localChangedAxes": absorption.changed_axes,
                "localConfoundedAxes": absorption.confounded_axes,
                "reviewCandidate": candidate.candidate_id if candidate else None,
                "reviewCandidateDimensions": candidate.candidate_dimensions if candidate else (),
            }
        )
        self._previous[name] = current

    def records_for(self, agent_name: str):
        return tuple(dict(item) for item in self._records.get(agent_name, ()))

    def counts_for(self, agent_name: str):
        return dict(self._counts.get(agent_name, {}))

    def review_candidates_for(self, agent_name: str):
        return tuple(self._review_candidates.get(agent_name, ()))

    def reviews_for(self, agent_name: str):
        return tuple(self._reviews.get(agent_name, ()))

    def submit_review(
        self,
        agent_name: str,
        candidate_id: str,
        *,
        status: str,
        basis: Sequence[str],
        assessor: str,
        ordinary_temporal_change_excluded: bool = False,
        boundary_or_coverage_change_excluded: bool = False,
        unresolved_dimensions: Sequence[str] = (),
    ):
        """Apply one explicit finite review to diagnostic H at most once."""

        if candidate_id in self._reviewed_candidate_ids[agent_name]:
            raise ValueError("review candidate has already been classified")
        candidate = next(
            (
                item
                for item in self._review_candidates.get(agent_name, ())
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise ValueError("unknown finite review candidate")

        assessment = review_village_candidate(
            candidate,
            status=status,
            basis=basis,
            assessor=assessor,
            ordinary_temporal_change_excluded=ordinary_temporal_change_excluded,
            boundary_or_coverage_change_excluded=boundary_or_coverage_change_excluded,
            unresolved_dimensions=unresolved_dimensions,
        )
        self._reviewed_candidate_ids[agent_name].add(candidate_id)
        self._reviews[agent_name].append(assessment)
        self._counts[agent_name][f"review:{assessment.status}"] += 1
        if assessment.eligible_for_h:
            self._h_for(agent_name).observe(assessment)
        return assessment

    def h_snapshot(self, agent_name: str):
        h = self._h_for(agent_name)
        return {
            "H_vec": dict(h.values),
            "H": h.magnitude,
            "theta": h.theta,
            "shouldReconstructDiagnostic": h.should_reconstruct,
            "authority": "diagnostic-only",
        }

    def snapshot(self):
        names = set(self._records) | set(self._h)
        return {
            "modelRef": self.model_ref,
            "dimensions": VILLAGE_OBSERVER_DIMENSIONS,
            "coefficients": dict(self.coefficients),
            "theta": self.theta,
            "agents": {
                name: {
                    "counts": dict(self._counts[name]),
                    "latest": dict(self._records[name][-1]) if self._records[name] else None,
                    "reviewCandidates": len(self._review_candidates[name]),
                    "reviews": len(self._reviews[name]),
                    "H": self.h_snapshot(name),
                }
                for name in names
            },
            "authority": "read-only-sidecar",
        }


def attach_v23_observer(
    simulation,
    coefficients: Optional[Mapping[str, float]] = None,
    *,
    theta: float = 1.0,
):
    """Attach the canonical observer without altering village policy authority."""

    existing = getattr(simulation, "v23_observer", None)
    if existing is not None:
        return existing

    observer = VillageCanonicalObserver(coefficients=coefficients, theta=theta)
    simulation.v23_observer = observer

    for agent in simulation.agents:
        original = agent.update_boundary

        def observed_update(self, perception, _original=original, _observer=observer):
            _observer.capture(self, perception, perception.t)
            return _original(perception)

        agent.update_boundary = MethodType(observed_update, agent)

    return observer
