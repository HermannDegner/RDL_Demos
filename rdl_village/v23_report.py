"""Read-only operational baseline report for Village v2.3.

This entrypoint runs the live Village with the operational coverage layer
installed and reports where finite review candidates/recommendations are
forming.  It performs no explicit reviews and therefore cannot create
unresolved H, M_delta, Probe, Selection, or M_B' by itself.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any

from .simulation import VillageSimulation
from .v23_compatibility import compatibility_snapshot
from .v23_operational import install_village_operational_coverage


def _context_payload(context_key: tuple[Any, ...]) -> dict[str, Any]:
    boundary_id, purpose, dimensions, condition_items = context_key
    return {
        "boundaryId": boundary_id,
        "purpose": purpose,
        "dimensions": list(dimensions),
        "conditions": dict(condition_items),
    }


def _context_label(context_key: tuple[Any, ...]) -> str:
    conditions = dict(context_key[3])
    return f"{conditions.get('place')}|{conditions.get('band')}"


def run_operational_baseline(
    *,
    ticks: int = 640,
    seed: int = 7,
    theta: float = 1.0,
    required_review_windows: int = 3,
    minimum_abs_residual: float = 0.0,
) -> dict[str, Any]:
    if ticks < 0:
        raise ValueError("ticks must be non-negative")

    simulation = VillageSimulation(seed=seed)
    coverage = install_village_operational_coverage(
        simulation,
        theta=theta,
        required_review_windows=required_review_windows,
        minimum_abs_residual=minimum_abs_residual,
    )
    simulation.run(ticks)

    observer = coverage.observer
    agents = {}
    for agent in simulation.agents:
        candidates = observer.review_candidates_for(agent.name)
        recommendations = coverage.recommendations_for(agent.name)
        reviews = observer.reviews_for(agent.name)
        controller = coverage.authority.controller(agent.name)

        context_candidate_counts = Counter()
        context_dimensions = defaultdict(Counter)
        context_examples = {}
        for candidate in candidates:
            context = candidate.mismatch.context_key
            label = _context_label(context)
            context_candidate_counts[label] += 1
            context_examples[label] = _context_payload(context)
            for dimension in candidate.candidate_dimensions:
                context_dimensions[label][dimension] += 1

        recommendation_payloads = []
        for recommendation in recommendations:
            recommendation_payloads.append(
                {
                    "recommendationId": recommendation.recommendation_id,
                    "context": _context_payload(recommendation.context_key),
                    "dimension": recommendation.dimension,
                    "direction": recommendation.direction,
                    "windowCount": recommendation.window_count,
                    "candidateIds": list(recommendation.candidate_ids),
                    "evidenceRefs": list(recommendation.evidence_refs),
                    "classificationStatus": recommendation.classification_status,
                    "authority": recommendation.authority,
                }
            )

        context_payloads = []
        for label in sorted(context_candidate_counts):
            context_payloads.append(
                {
                    "label": label,
                    "context": context_examples[label],
                    "reviewCandidateCount": context_candidate_counts[label],
                    "candidateDimensions": dict(context_dimensions[label]),
                }
            )

        h = observer.h_snapshot(agent.name)
        agents[agent.name] = {
            "reviewCandidateCount": len(candidates),
            "explicitReviewCount": len(reviews),
            "reviewRecommendations": recommendation_payloads,
            "candidateContexts": context_payloads,
            "canonicalH": {
                "formedFromExplicitReviewsOnly": True,
                "H": h["H"],
                "theta": h["theta"],
                "shouldReconstructDiagnostic": h["shouldReconstructDiagnostic"],
            },
            "installedFiniteContextCount": len(controller.models),
            "activeRuntimeSessionCount": sum(
                1 for (name, _context) in coverage.runtime.sessions if name == agent.name
            ),
        }

    compatibility = compatibility_snapshot()
    return {
        "report": "village-v23-operational-baseline",
        "ticks": ticks,
        "seed": seed,
        "theta": theta,
        "requiredReviewWindows": required_review_windows,
        "minimumAbsResidual": minimum_abs_residual,
        "agents": agents,
        "reviewPolicy": "advisory-only-until-explicit-review",
        "finiteContextPolicy": "no-cross-context-generalization",
        "compatibilityPolicy": compatibility["policy"],
        "xiStatus": "unrecovered-relations-remain",
        "terminalTruthClaim": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a read-only Village v2.3 operational coverage baseline")
    parser.add_argument("--ticks", type=int, default=640)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--theta", type=float, default=1.0)
    parser.add_argument("--review-windows", type=int, default=3)
    parser.add_argument("--minimum-residual", type=float, default=0.0)
    args = parser.parse_args(argv)

    report = run_operational_baseline(
        ticks=args.ticks,
        seed=args.seed,
        theta=args.theta,
        required_review_windows=args.review_windows,
        minimum_abs_residual=args.minimum_residual,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
