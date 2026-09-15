"""Advisory review support for operational Village v2.3 coverage.

This module never classifies a mismatch as unresolved.  It only notices when
already-formed finite review candidates show the same signed residual in the
same finite context across multiple distinct observation windows.

A recommendation is therefore evidence for *where a human/explicit reviewer
may want to look next*, not evidence that ordinary temporal change has been
excluded and not permission to feed H or enter M_delta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class VillageReviewRecommendation:
    recommendation_id: str
    agent_name: str
    context_key: tuple[Any, ...]
    dimension: str
    direction: str
    window_count: int
    candidate_ids: tuple[str, ...]
    section_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    basis: tuple[str, ...]
    status: str = "review-recommended"
    authority: str = "advisory-only"
    classification_status: str = "not-performed"
    ordinary_temporal_change_excluded: bool = False
    boundary_or_coverage_change_excluded: bool = False
    xi_status: str = "unrecovered-relations-remain"

    def __post_init__(self) -> None:
        if self.direction not in {"positive", "negative"}:
            raise ValueError("review recommendation requires a signed residual direction")
        if self.window_count < 2:
            raise ValueError("review recommendation requires multiple distinct windows")
        if len(self.candidate_ids) != self.window_count:
            raise ValueError("candidate count must equal distinct recommendation windows")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("review recommendation candidate ids must be distinct")
        if len(self.section_ids) != self.window_count or len(set(self.section_ids)) != self.window_count:
            raise ValueError("review recommendation section ids must be distinct")
        if not self.evidence_refs or not self.basis:
            raise ValueError("review recommendation requires finite evidence and basis")

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "recommendationId": self.recommendation_id,
                "agent": self.agent_name,
                "context": self.context_key,
                "dimension": self.dimension,
                "direction": self.direction,
                "windowCount": self.window_count,
                "candidateIds": self.candidate_ids,
                "sectionIds": self.section_ids,
                "evidenceRefs": self.evidence_refs,
                "basis": self.basis,
                "status": self.status,
                "authority": self.authority,
                "classificationStatus": self.classification_status,
                "ordinaryTemporalChangeExcluded": self.ordinary_temporal_change_excluded,
                "boundaryOrCoverageChangeExcluded": self.boundary_or_coverage_change_excluded,
                "xiStatus": self.xi_status,
            }
        )


def _direction(value: float) -> str:
    return "positive" if value > 0.0 else "negative"


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item).strip()))


class VillageReviewAdvisor:
    """Find repeated finite evidence without performing the finite review itself."""

    def __init__(self, *, required_distinct_windows: int = 3, minimum_abs_residual: float = 0.0):
        if not isinstance(required_distinct_windows, int) or required_distinct_windows < 2:
            raise ValueError("review advisor requires at least two distinct windows")
        threshold = float(minimum_abs_residual)
        if not math.isfinite(threshold) or threshold < 0.0:
            raise ValueError("minimum_abs_residual must be finite and non-negative")
        self.required_distinct_windows = required_distinct_windows
        self.minimum_abs_residual = threshold

    def recommendations(self, candidates: Sequence[Any]) -> tuple[VillageReviewRecommendation, ...]:
        """Return latest repeated-window recommendations from explicit candidates.

        Re-reading the same candidate list cannot manufacture persistence because
        candidate and later-section identifiers are de-duplicated before window
        counting.  A sign reversal starts a new run for that dimension.
        """

        unique = []
        seen_candidates = set()
        for candidate in candidates:
            candidate_id = str(candidate.candidate_id)
            if candidate_id in seen_candidates:
                continue
            seen_candidates.add(candidate_id)
            unique.append(candidate)

        series: dict[tuple[Any, ...], list[tuple[Any, float]]] = {}
        for candidate in unique:
            mismatch = candidate.mismatch
            context = mismatch.context_key
            for dimension in candidate.candidate_dimensions:
                value = float(mismatch.values[dimension])
                if not math.isfinite(value) or abs(value) <= self.minimum_abs_residual:
                    continue
                key = (candidate.agent_name, context, str(dimension))
                series.setdefault(key, []).append((candidate, value))

        recommendations = []
        for (agent_name, context, dimension), entries in series.items():
            run = []
            run_direction = None
            seen_sections = set()
            for candidate, value in entries:
                section_id = str(candidate.mismatch.later_section_id)
                if section_id in seen_sections:
                    continue
                seen_sections.add(section_id)
                direction = _direction(value)
                if direction != run_direction:
                    run = []
                    run_direction = direction
                run.append((candidate, value))

            if len(run) < self.required_distinct_windows:
                continue
            selected = run[-self.required_distinct_windows :]
            candidate_ids = tuple(item.candidate_id for item, _ in selected)
            section_ids = tuple(item.mismatch.later_section_id for item, _ in selected)
            evidence_refs = _stable_unique(
                ref
                for item, _ in selected
                for ref in (
                    *item.evidence_refs,
                    item.local_absorption.evidence_ref,
                )
            )
            recommendation_id = (
                f"village-review-advice:{agent_name}:{dimension}:"
                f"{section_ids[0]}->{section_ids[-1]}"
            )
            basis = (
                f"same finite context retained across {len(selected)} distinct review-candidate windows",
                f"same signed {dimension} residual persisted across those windows",
                "each contributing window already carries bounded local absorption-attempt evidence",
                "recommendation does not exclude ordinary temporal change or boundary/coverage change",
            )
            recommendations.append(
                VillageReviewRecommendation(
                    recommendation_id=recommendation_id,
                    agent_name=agent_name,
                    context_key=context,
                    dimension=dimension,
                    direction=run_direction,
                    window_count=len(selected),
                    candidate_ids=candidate_ids,
                    section_ids=section_ids,
                    evidence_refs=evidence_refs,
                    basis=basis,
                )
            )

        return tuple(recommendations)

    def recommendations_for(self, observer, agent_name: str) -> tuple[VillageReviewRecommendation, ...]:
        return self.recommendations(observer.review_candidates_for(agent_name))
