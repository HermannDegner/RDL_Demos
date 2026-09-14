"""Opt-in Core v2.3 reviewed CLI for rdl_bot.

Usage::

    python cli_v23.py
    python cli_v23.py --seed

The default ``main.py`` entrypoint is intentionally untouched.  This module
wraps ``main.respond`` and ``main.handle_command`` so the ordinary legacy CLI
remains authoritative by default while canonical v2.3 state is observed beside
it.

- non-zero E becomes pending-review;
- canonical H is never updated automatically;
- ``/v23`` is read-only diagnostics;
- ``/v23 resolve ...`` / ``/v23 unresolved ...`` are explicit reviews;
- ``/v23 plan`` is a dry-run reconstruction/target preview;
- ``/v23 execute`` is the only explicit canonical mutation command;
- successful canonical mutation is one-shot per reviewed turn pair;
- canonical review/H/execution audit is persisted, but frozen evaluators are not.

After restart a fresh comparison window begins at the next monotonic turn id.
No cross-restart E is manufactured from a recreated evaluator.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    from .migration_session_v23 import CanonicalMigrationSession
    from .mutation_v23 import make_llm_revision_mutation
    from .persistence_v23 import load_session, save_session
except ImportError:
    from migration_session_v23 import CanonicalMigrationSession  # type: ignore
    from mutation_v23 import make_llm_revision_mutation  # type: ignore
    from persistence_v23 import load_session, save_session  # type: ignore


V23_SESSION_STATE_PATH = "data/v23_shadow_state.json"


def _print_shadow_status(session: CanonicalMigrationSession) -> None:
    authority = session.controller.authority
    pending = session.pending_records
    print("  v2.3 shadow status:")
    print(
        f"    turns_in_window={len(session.shadow.turns)} last_turn_id={session.shadow.last_assigned_index} "
        f"assessments={len(session.assessments)} pending={len(pending)} reviews={len(session.reviews)} "
        f"executions={len(session.executions)}"
    )
    print(
        f"    canonical_H={authority.h_magnitude:.3f} "
        f"fixed_theta={authority.theta:.3f} reconstruct={authority.should_reconstruct}"
    )
    if pending:
        latest = pending[-1]
        reasons = latest.candidate.mismatch.reasons if latest.candidate else ()
        refs = latest.candidate.evidence_refs if latest.candidate else ()
        print(
            f"    latest_pending={latest.earlier_index}->{latest.later_index} "
            f"reasons={reasons} evidence={refs}"
        )
    if session.reviews:
        review = session.reviews[-1]
        print(
            f"    latest_review={review.earlier_index}->{review.later_index} "
            f"disposition={review.disposition} assessor={review.assessment.assessor}"
        )
    if session.executions:
        execution = session.executions[-1]
        print(
            f"    latest_execution={execution.earlier_index}->{execution.later_index} "
            f"executor={execution.executor_status} mutation={execution.mutation_status} "
            f"target={execution.target_ref}"
        )
    print("    /v23 status/review/plan are non-mutating; only explicit /v23 execute may mutate")


def _review_latest_pending(session: CanonicalMigrationSession, *, disposition: str, reason: str) -> None:
    pending = session.pending_records
    if not pending:
        print("  [v2.3 shadow] pending-review はありません。")
        return
    if not reason.strip():
        print("  [v2.3 shadow] review理由が必要です。")
        print("    /v23 resolve <reason>")
        print("    /v23 unresolved <reason>")
        return

    record = pending[-1]
    review_ref = f"cli-review:{record.earlier_index}-{record.later_index}"
    if disposition == "resolved":
        assessment = session.review_resolved(
            record,
            reason=reason.strip(),
            assessor="cli-user",
            evidence_refs=(review_ref,),
        )
        print(
            f"  [v2.3 review] {record.earlier_index}->{record.later_index} "
            f"resolved: {assessment.reason}"
        )
        return

    observation = session.review_unresolved(
        record,
        reason=reason.strip(),
        assessor="cli-user",
        evidence_refs=(review_ref,),
    )
    print(
        f"  [v2.3 review] {record.earlier_index}->{record.later_index} unresolved: "
        f"H={observation.h_magnitude:.3f} θ={observation.theta:.3f} "
        f"reconstruct={observation.should_reconstruct}"
    )
    print("  [v2.3 review] canonical Hのみ更新。node graph mutationは実行しません。")


def _print_plan_preview(session: CanonicalMigrationSession) -> None:
    preview = session.preview_latest_reconstruction()
    print(f"  [v2.3 plan] status={preview.status}")
    if preview.request is not None:
        print(
            f"    H={preview.request.h_magnitude:.3f} θ={preview.request.theta:.3f} "
            f"reasons={preview.request.mismatch_reasons}"
        )
    if preview.plan is not None:
        print(
            f"    target={preview.plan.target_ref} "
            f"candidates={preview.plan.candidate_refs} "
            f"evidence_turns={preview.plan.evidence_turns}"
        )
    print("    dry-run only; node graph mutationは実行しません。")


def _execute_latest(session: CanonicalMigrationSession, *, graph: Any, llm: Any) -> None:
    if graph is None or llm is None:
        print("  [v2.3 execute] graph / llm context が利用できません。変更しません。")
        return

    result = session.execute_latest_reconstruction(
        mutate=make_llm_revision_mutation(graph, llm),
    )
    print(f"  [v2.3 execute] status={result.status}")
    if result.plan is not None:
        print(
            f"    target={result.plan.target_ref} candidates={result.plan.candidate_refs} "
            f"evidence_turns={result.plan.evidence_turns}"
        )
    if result.execution is not None:
        callback_result = result.execution.result
        mutation_status = getattr(callback_result, "status", None)
        replacement_ref = getattr(callback_result, "replacement_ref", None)
        print(
            f"    executor={result.execution.status} target={result.execution.target_ref} "
            f"mutation={mutation_status} replacement={replacement_ref}"
        )
    print("    canonical review済みtargetだけを使用。legacy H / hot-nodeは参照しません。")


def _handle_v23_command(
    cmd: str,
    session: CanonicalMigrationSession,
    *,
    graph: Any = None,
    llm: Any = None,
) -> bool:
    parts = cmd.strip().split(maxsplit=2)
    if not parts or parts[0] != "/v23":
        return False
    if len(parts) == 1 or parts[1] == "status":
        _print_shadow_status(session)
        return True

    subcommand = parts[1].lower()
    reason = parts[2] if len(parts) >= 3 else ""
    if subcommand == "resolve":
        _review_latest_pending(session, disposition="resolved", reason=reason)
        return True
    if subcommand == "unresolved":
        _review_latest_pending(session, disposition="unresolved", reason=reason)
        return True
    if subcommand == "plan":
        _print_plan_preview(session)
        return True
    if subcommand == "execute":
        _execute_latest(session, graph=graph, llm=llm)
        return True

    print("  v2.3 commands:")
    print("    /v23")
    print("    /v23 resolve <reason>")
    print("    /v23 unresolved <reason>")
    print("    /v23 plan")
    print("    /v23 execute")
    print("  executeだけが明示的なcanonical graph mutationを試行します。")
    return True


def install_shadow_session(
    legacy_main: Any,
    *,
    session: CanonicalMigrationSession | None = None,
    state_path: str | None = None,
) -> CanonicalMigrationSession:
    """Wrap legacy response/command hooks with opt-in canonical observation.

    When ``state_path`` is supplied, canonical review/H/execution state is loaded
    once and atomically saved after every observed turn and every ``/v23``
    command.  Frozen evaluators are never persisted; restored sessions start a
    fresh comparison window at the next turn id.
    """

    if session is None:
        session = load_session(state_path) if state_path else CanonicalMigrationSession()

    original_respond: Callable[..., tuple[str, str]] = legacy_main.respond
    original_handle_command: Callable[..., bool] | None = getattr(legacy_main, "handle_command", None)

    def persist() -> None:
        if state_path:
            save_session(state_path, session)

    def shadowed_respond(user_input, graph, h, llm, sfo_profile, unresolved_queue, llm_trust):
        result = session.respond(
            user_input,
            graph,
            h,
            llm,
            sfo_profile,
            unresolved_queue,
            llm_trust,
            legacy_respond=original_respond,
        )
        persist()
        return result

    legacy_main.respond = shadowed_respond

    if original_handle_command is not None:
        def shadowed_handle_command(cmd, *args, **kwargs):
            llm = args[0] if len(args) >= 1 else kwargs.get("llm")
            graph = args[1] if len(args) >= 2 else kwargs.get("graph")
            if _handle_v23_command(cmd, session, graph=graph, llm=llm):
                persist()
                return True
            return original_handle_command(cmd, *args, **kwargs)

        legacy_main.handle_command = shadowed_handle_command

    return session


def main() -> None:
    try:
        from . import main as legacy_main
    except ImportError:
        import main as legacy_main  # type: ignore

    session = install_shadow_session(legacy_main, state_path=V23_SESSION_STATE_PATH)
    print("  [v2.3] canonical comparison enabled; default legacy action authority remains unchanged")
    print("  [v2.3] non-zero canonical E is pending until explicit /v23 review")
    print("  [v2.3] /v23 plan is dry-run; /v23 execute is explicit one-shot canonical mutation")
    print(
        f"  [v2.3] durable state: last_turn_id={session.shadow.last_assigned_index} "
        f"pending={len(session.pending_records)} reviews={len(session.reviews)} "
        f"executions={len(session.executions)}"
    )
    try:
        legacy_main.main()
    finally:
        save_session(V23_SESSION_STATE_PATH, session)


if __name__ == "__main__":
    main()
