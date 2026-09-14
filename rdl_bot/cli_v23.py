"""Opt-in Core v2.3 shadow CLI for rdl_bot.

Usage::

    python cli_v23.py
    python cli_v23.py --seed

The default ``main.py`` entrypoint is intentionally untouched.  This module
installs narrow wrappers around ``main.respond`` and ``main.handle_command`` so
the ordinary CLI loop, feedback handling, persistence, LLM trust and legacy
action authority all keep working exactly as before while
``CanonicalMigrationSession`` records adjacent turn comparisons.

Canonical observations are non-authoritative here:

- non-zero E becomes pending-review;
- canonical H is never updated automatically;
- ``/v23`` is read-only diagnostics;
- ``/v23 resolve ...`` and ``/v23 unresolved ...`` are explicit human reviews;
- no v2.3 command in this module mutates the node graph.
"""

from __future__ import annotations

from typing import Any, Callable

try:  # package-style imports
    from .migration_session_v23 import CanonicalMigrationSession
except ImportError:  # direct ``python cli_v23.py`` execution
    from migration_session_v23 import CanonicalMigrationSession  # type: ignore


def _print_shadow_status(session: CanonicalMigrationSession) -> None:
    authority = session.controller.authority
    pending = session.pending_records
    print("  v2.3 shadow status:")
    print(
        f"    turns={len(session.shadow.turns)} assessments={len(session.assessments)} "
        f"pending={len(pending)} reviews={len(session.reviews)}"
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
        latest_review = session.reviews[-1]
        print(
            f"    latest_review={latest_review.earlier_index}->{latest_review.later_index} "
            f"disposition={latest_review.disposition} "
            f"assessor={latest_review.assessment.assessor}"
        )
    print("    /v23 alone is read-only; shadow CLI never mutates the node graph")


def _review_latest_pending(
    session: CanonicalMigrationSession,
    *,
    disposition: str,
    reason: str,
) -> None:
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


def _handle_v23_command(cmd: str, session: CanonicalMigrationSession) -> bool:
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

    print("  v2.3 shadow commands:")
    print("    /v23")
    print("    /v23 resolve <reason>")
    print("    /v23 unresolved <reason>")
    print("  reviewはcanonical状態だけを更新し、node graphは変更しません。")
    return True


def install_shadow_session(
    legacy_main: Any,
    *,
    session: CanonicalMigrationSession | None = None,
) -> CanonicalMigrationSession:
    """Wrap legacy response/command hooks with opt-in canonical observation.

    The response wrapper preserves the legacy function signature because
    ``main.main`` calls the global ``respond`` symbol directly.  The command
    wrapper intercepts only ``/v23`` commands and delegates every other command
    to the original handler.  Graph mutation authority remains legacy.
    """

    if session is None:
        session = CanonicalMigrationSession()

    original_respond: Callable[..., tuple[str, str]] = legacy_main.respond
    original_handle_command: Callable[..., bool] | None = getattr(legacy_main, "handle_command", None)

    def shadowed_respond(
        user_input,
        graph,
        h,
        llm,
        sfo_profile,
        unresolved_queue,
        llm_trust,
    ):
        return session.respond(
            user_input,
            graph,
            h,
            llm,
            sfo_profile,
            unresolved_queue,
            llm_trust,
            legacy_respond=original_respond,
        )

    legacy_main.respond = shadowed_respond

    if original_handle_command is not None:
        def shadowed_handle_command(cmd, *args, **kwargs):
            if _handle_v23_command(cmd, session):
                return True
            return original_handle_command(cmd, *args, **kwargs)

        legacy_main.handle_command = shadowed_handle_command

    return session


def main() -> None:
    try:
        from . import main as legacy_main
    except ImportError:
        import main as legacy_main  # type: ignore

    install_shadow_session(legacy_main)
    print("  [v2.3 shadow] canonical comparison enabled; legacy graph-mutation authority unchanged")
    print("  [v2.3 shadow] non-zero canonical E is pending until explicit /v23 review")
    print("  [v2.3 shadow] /v23 reviews can update canonical H but never mutate the graph")
    legacy_main.main()


if __name__ == "__main__":
    main()
