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
- canonical H is not updated automatically;
- no reconstruction mutation is executed automatically;
- ``/v23`` is read-only diagnostics.
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
    print(f"    turns={len(session.shadow.turns)} assessments={len(session.assessments)} pending={len(pending)}")
    print(f"    canonical_H={authority.h_magnitude:.3f} fixed_theta={authority.theta:.3f} reconstruct={authority.should_reconstruct}")
    if pending:
        latest = pending[-1]
        reasons = latest.candidate.mismatch.reasons if latest.candidate else ()
        refs = latest.candidate.evidence_refs if latest.candidate else ()
        print(f"    latest_pending={latest.earlier_index}->{latest.later_index} reasons={reasons} evidence={refs}")
    print("    mode=observation-only; /v23 never reviews or mutates")


def install_shadow_session(
    legacy_main: Any,
    *,
    session: CanonicalMigrationSession | None = None,
) -> CanonicalMigrationSession:
    """Wrap legacy response/command hooks with non-authoritative observation.

    The response wrapper preserves the legacy function signature because
    ``main.main`` calls the global ``respond`` symbol directly.  The command
    wrapper intercepts only ``/v23`` and delegates every other command to the
    original handler.  Neither wrapper changes legacy action authority.
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
            if cmd.strip().split()[0] == "/v23":
                _print_shadow_status(session)
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
    print("  [v2.3 shadow] canonical comparison enabled; legacy action authority unchanged")
    print("  [v2.3 shadow] non-zero canonical E is stored as pending-review only; use /v23 for read-only status")
    legacy_main.main()


if __name__ == "__main__":
    main()
