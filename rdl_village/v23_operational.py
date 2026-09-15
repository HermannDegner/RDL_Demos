"""Operational coverage helpers for the completed Village v2.3 path.

This layer makes finite-context migration easier to operate without changing the
semantic gates.  It can install the explicit canonical runtime and report where
repeated finite evidence suggests that an explicit review would be useful.

It does *not* submit reviews, classify unresolved mismatch, fabricate Probe or
Selection evidence, or generalize an installed context to another finite B.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Optional

from .v23_review_assist import VillageReviewAdvisor
from .v23_runtime import VillageCanonicalRuntimeDriver, install_village_canonical_runtime


class VillageOperationalCoverage:
    def __init__(
        self,
        simulation,
        runtime: VillageCanonicalRuntimeDriver,
        *,
        required_review_windows: int = 3,
        minimum_abs_residual: float = 0.0,
    ) -> None:
        self.simulation = simulation
        self.runtime = runtime
        self.observer = runtime.observer
        self.authority = runtime.authority
        self.advisor = VillageReviewAdvisor(
            required_distinct_windows=required_review_windows,
            minimum_abs_residual=minimum_abs_residual,
        )
        simulation.v23OperationalCoverage = self

    def recommendations_for(self, agent_name: str):
        """Return advisory-only repeated-window review recommendations."""
        return self.advisor.recommendations_for(self.observer, agent_name)

    def review_queue_for(self, agent_name: str) -> tuple[Mapping[str, Any], ...]:
        """Return finite review work items without pre-filling review conclusions."""
        items = []
        candidates = {
            candidate.candidate_id: candidate
            for candidate in self.observer.review_candidates_for(agent_name)
        }
        for recommendation in self.recommendations_for(agent_name):
            latest_id = recommendation.candidate_ids[-1]
            latest = candidates.get(latest_id)
            if latest is None:
                continue
            items.append(
                MappingProxyType(
                    {
                        "recommendationId": recommendation.recommendation_id,
                        "agent": agent_name,
                        "context": recommendation.context_key,
                        "candidateId": latest_id,
                        "dimension": recommendation.dimension,
                        "direction": recommendation.direction,
                        "candidateDimensions": latest.candidate_dimensions,
                        "evidenceRefs": recommendation.evidence_refs,
                        "basis": recommendation.basis,
                        "reviewStatus": "not-performed",
                        "ordinaryTemporalChangeExcluded": False,
                        "boundaryOrCoverageChangeExcluded": False,
                        "authority": "review-work-item-only",
                    }
                )
            )
        return tuple(items)

    def snapshot(self) -> Mapping[str, Any]:
        agents = {}
        for agent in self.simulation.agents:
            recommendations = self.recommendations_for(agent.name)
            queue = self.review_queue_for(agent.name)
            controller = self.authority.controller(agent.name)
            installed = tuple(model.snapshot() for model in controller.models.values())
            agents[agent.name] = MappingProxyType(
                {
                    "reviewRecommendations": tuple(item.snapshot() for item in recommendations),
                    "reviewQueue": queue,
                    "installedFiniteContexts": installed,
                    "activeRuntimeSessions": tuple(
                        session.snapshot()
                        for (name, _), session in self.runtime.sessions.items()
                        if name == agent.name
                    ),
                }
            )
        return MappingProxyType(
            {
                "agents": MappingProxyType(agents),
                "reviewPolicy": "explicit-review-required",
                "recommendationAuthority": "advisory-only",
                "finiteContextPolicy": "no-cross-context-generalization",
                "xiStatus": "unrecovered-relations-remain",
            }
        )


def install_village_operational_coverage(
    simulation,
    *,
    theta: float,
    coefficients: Optional[Mapping[str, float]] = None,
    required_shadow_validations: int = 2,
    reentry_validation_windows: int = 2,
    required_review_windows: int = 3,
    minimum_abs_residual: float = 0.0,
) -> VillageOperationalCoverage:
    """Install the explicit canonical runtime plus advisory coverage reporting."""

    existing = getattr(simulation, "v23OperationalCoverage", None)
    if existing is not None:
        return existing

    runtime = getattr(simulation, "v23CanonicalRuntime", None)
    if runtime is None:
        runtime = install_village_canonical_runtime(
            simulation,
            theta=theta,
            coefficients=coefficients,
            required_shadow_validations=required_shadow_validations,
            reentry_validation_windows=reentry_validation_windows,
        )
    elif abs(float(runtime.observer.theta) - float(theta)) > 1e-12:
        raise ValueError("existing Village canonical runtime theta does not match coverage theta")

    return VillageOperationalCoverage(
        simulation,
        runtime,
        required_review_windows=required_review_windows,
        minimum_abs_residual=minimum_abs_residual,
    )
