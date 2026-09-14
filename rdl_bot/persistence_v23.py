"""JSON persistence for the opt-in rdl_bot Core v2.3 migration session.

Persisted:
- fixed theta / decay configuration;
- canonical unresolved-H coordinates;
- assessment/pending records;
- explicit review audit records;
- explicit execution audit records;
- greatest assigned turn id.

Not persisted:
- frozen graph evaluators / graph snapshots;
- live node-graph mutation authority.

A restored session therefore starts a fresh process-local comparison window at
``last_turn_index + 1``.  It never manufactures cross-restart E from a recreated
M_B snapshot.  Old pending/review evidence remains auditable and reviewable, but
target planning that requires an old frozen evaluator safely reports evidence
unavailable.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

try:  # package-style imports
    from .assessment_policy_v23 import ResolutionCandidate
    from .authority_v23 import AuthorityObservation
    from .canonical_runtime_v23 import RuntimeAssessmentRecord
    from .migration_session_v23 import CanonicalMigrationSession, SessionExecution, SessionReview
    from .resolution_v23 import ResolutionAssessment
    from .runtime_v23 import V23ConversationShadow
    from .v23_state import MismatchObservation
except ImportError:  # historical ``PYTHONPATH=rdl_bot:.`` execution
    from assessment_policy_v23 import ResolutionCandidate  # type: ignore
    from authority_v23 import AuthorityObservation  # type: ignore
    from canonical_runtime_v23 import RuntimeAssessmentRecord  # type: ignore
    from migration_session_v23 import CanonicalMigrationSession, SessionExecution, SessionReview  # type: ignore
    from resolution_v23 import ResolutionAssessment  # type: ignore
    from runtime_v23 import V23ConversationShadow  # type: ignore
    from v23_state import MismatchObservation  # type: ignore


FORMAT_VERSION = 1


def _assessment_to_dict(value: ResolutionAssessment) -> dict[str, Any]:
    return {
        "unresolved": bool(value.unresolved),
        "reason": value.reason,
        "assessor": value.assessor,
        "evidence_refs": list(value.evidence_refs),
    }


def _assessment_from_dict(value: Mapping[str, Any]) -> ResolutionAssessment:
    return ResolutionAssessment(
        unresolved=bool(value["unresolved"]),
        reason=str(value["reason"]),
        assessor=str(value["assessor"]),
        evidence_refs=tuple(str(ref) for ref in value.get("evidence_refs", ())),
    )


def _mismatch_to_dict(value: MismatchObservation) -> dict[str, Any]:
    return {
        "values": {str(key): float(number) for key, number in value.values.items()},
        "reasons": list(value.reasons),
    }


def _mismatch_from_dict(value: Mapping[str, Any]) -> MismatchObservation:
    return MismatchObservation(
        values={str(key): float(number) for key, number in dict(value.get("values", {})).items()},
        reasons=tuple(str(reason) for reason in value.get("reasons", ())),
    )


def _candidate_to_dict(value: ResolutionCandidate) -> dict[str, Any]:
    return {
        "status": value.status,
        "mismatch": _mismatch_to_dict(value.mismatch),
        "evidence_refs": list(value.evidence_refs),
        "assessment": _assessment_to_dict(value.assessment) if value.assessment is not None else None,
    }


def _candidate_from_dict(value: Mapping[str, Any]) -> ResolutionCandidate:
    assessment_raw = value.get("assessment")
    return ResolutionCandidate(
        status=str(value["status"]),
        mismatch=_mismatch_from_dict(value["mismatch"]),
        evidence_refs=tuple(str(ref) for ref in value.get("evidence_refs", ())),
        assessment=_assessment_from_dict(assessment_raw) if assessment_raw is not None else None,
    )


def _observation_to_dict(value: AuthorityObservation) -> dict[str, Any]:
    return {
        "status": value.status,
        "mismatch": _mismatch_to_dict(value.mismatch) if value.mismatch is not None else None,
        "assessment": _assessment_to_dict(value.assessment),
        "h_magnitude": float(value.h_magnitude),
        "theta": float(value.theta),
        "should_reconstruct": bool(value.should_reconstruct),
    }


def _observation_from_dict(value: Mapping[str, Any]) -> AuthorityObservation:
    mismatch_raw = value.get("mismatch")
    return AuthorityObservation(
        status=str(value["status"]),
        mismatch=_mismatch_from_dict(mismatch_raw) if mismatch_raw is not None else None,
        assessment=_assessment_from_dict(value["assessment"]),
        h_magnitude=float(value["h_magnitude"]),
        theta=float(value["theta"]),
        should_reconstruct=bool(value["should_reconstruct"]),
    )


def _record_to_dict(value: RuntimeAssessmentRecord) -> dict[str, Any]:
    return {
        "earlier_index": int(value.earlier_index),
        "later_index": int(value.later_index),
        "status": value.status,
        "candidate": _candidate_to_dict(value.candidate) if value.candidate is not None else None,
        "authority_observation": (
            _observation_to_dict(value.authority_observation)
            if value.authority_observation is not None else None
        ),
    }


def _record_from_dict(value: Mapping[str, Any]) -> RuntimeAssessmentRecord:
    candidate_raw = value.get("candidate")
    observation_raw = value.get("authority_observation")
    return RuntimeAssessmentRecord(
        earlier_index=int(value["earlier_index"]),
        later_index=int(value["later_index"]),
        status=str(value["status"]),
        candidate=_candidate_from_dict(candidate_raw) if candidate_raw is not None else None,
        authority_observation=(
            _observation_from_dict(observation_raw) if observation_raw is not None else None
        ),
    )


def _review_to_dict(value: SessionReview) -> dict[str, Any]:
    return {
        "earlier_index": int(value.earlier_index),
        "later_index": int(value.later_index),
        "assessment": _assessment_to_dict(value.assessment),
        "authority_observation": (
            _observation_to_dict(value.authority_observation)
            if value.authority_observation is not None else None
        ),
    }


def _review_from_dict(value: Mapping[str, Any]) -> SessionReview:
    observation_raw = value.get("authority_observation")
    return SessionReview(
        earlier_index=int(value["earlier_index"]),
        later_index=int(value["later_index"]),
        assessment=_assessment_from_dict(value["assessment"]),
        authority_observation=(
            _observation_from_dict(observation_raw) if observation_raw is not None else None
        ),
    )


def _execution_to_dict(value: SessionExecution) -> dict[str, Any]:
    return {
        "earlier_index": int(value.earlier_index),
        "later_index": int(value.later_index),
        "executor_status": value.executor_status,
        "target_ref": value.target_ref,
        "mutation_status": value.mutation_status,
    }


def _execution_from_dict(value: Mapping[str, Any]) -> SessionExecution:
    target_ref = value.get("target_ref")
    mutation_status = value.get("mutation_status")
    return SessionExecution(
        earlier_index=int(value["earlier_index"]),
        later_index=int(value["later_index"]),
        executor_status=str(value["executor_status"]),
        target_ref=str(target_ref) if target_ref is not None else None,
        mutation_status=str(mutation_status) if mutation_status is not None else None,
    )


def session_to_dict(session: CanonicalMigrationSession) -> dict[str, Any]:
    """Return a JSON-safe durable snapshot without frozen evaluator objects."""

    return {
        "format_version": FORMAT_VERSION,
        "theta": float(session.theta),
        "decay": float(session.decay),
        "last_turn_index": int(session.shadow.last_assigned_index),
        "h_snapshot": session.controller.authority.h_snapshot(),
        "assessments": [_record_to_dict(record) for record in session.assessments],
        "reviews": [_review_to_dict(review) for review in session.reviews],
        "executions": [_execution_to_dict(item) for item in session.executions],
        "restart_policy": "fresh-comparison-window-no-cross-restart-E",
    }


def session_from_dict(payload: Mapping[str, Any]) -> CanonicalMigrationSession:
    """Restore durable canonical state and start a fresh comparison window."""

    version = int(payload.get("format_version", 0))
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported v2.3 migration persistence format: {version}")

    last_turn_index = int(payload.get("last_turn_index", 0))
    if last_turn_index < 0:
        raise ValueError("last_turn_index must be non-negative")

    session = CanonicalMigrationSession(
        theta=float(payload.get("theta", 2.0)),
        decay=float(payload.get("decay", 1.0)),
        shadow=V23ConversationShadow(index_offset=last_turn_index),
    )
    records = [_record_from_dict(item) for item in payload.get("assessments", ())]
    reviews = [_review_from_dict(item) for item in payload.get("reviews", ())]
    executions = [_execution_from_dict(item) for item in payload.get("executions", ())]
    session.assessments = records
    session.controller.records = list(records)
    session.reviews = reviews
    session.executions = executions
    session.controller.authority.restore_h_snapshot(payload.get("h_snapshot", {}))
    return session


def save_session(path: str, session: CanonicalMigrationSession) -> None:
    """Atomically save canonical migration state as UTF-8 JSON."""

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(session_to_dict(session), handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def load_session(
    path: str,
    *,
    default_theta: float = 2.0,
    default_decay: float = 1.0,
) -> CanonicalMigrationSession:
    """Load persisted state or return a fresh session when no file exists."""

    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return CanonicalMigrationSession(theta=default_theta, decay=default_decay)
    return session_from_dict(payload)
