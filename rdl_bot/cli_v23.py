"""Opt-in Core v2.3 shadow CLI for rdl_bot.

Usage::

    python cli_v23.py
    python cli_v23.py --seed

The default ``main.py`` entrypoint is intentionally untouched.  This module
installs a narrow wrapper around ``main.respond`` so the ordinary CLI loop,
feedback handling, persistence, LLM trust and legacy action authority all keep
working exactly as before while ``CanonicalMigrationSession`` records adjacent
turn comparisons.

Canonical observations are non-authoritative here:

- non-zero E becomes pending-review;
- canonical H is not updated automatically;
- no reconstruction mutation is executed automatically.
"""

from __future__ import annotations

from typing import Any, Callable

try:  # package-style imports
    from .migration_session_v23 import CanonicalMigrationSession
except ImportError:  # direct ``python cli_v23.py`` execution
    from migration_session_v23 import CanonicalMigrationSession  # type: ignore


def install_shadow_session(
    legacy_main: Any,
    *,
    session: CanonicalMigrationSession | None = None,
) -> CanonicalMigrationSession:
    """Wrap ``legacy_main.respond`` with a non-authoritative migration session.

    The wrapper preserves the legacy function signature because ``main.main``
    calls the global ``respond`` symbol directly.  Installing the wrapper changes
    observation only; the original response function remains the authoritative
    action path and is called exactly once per ordinary user turn.
    """

    if session is None:
        session = CanonicalMigrationSession()

    original_respond: Callable[..., tuple[str, str]] = legacy_main.respond

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
    return session


def main() -> None:
    try:
        from . import main as legacy_main
    except ImportError:
        import main as legacy_main  # type: ignore

    session = install_shadow_session(legacy_main)
    print("  [v2.3 shadow] canonical comparison enabled; legacy action authority unchanged")
    print("  [v2.3 shadow] non-zero canonical E is stored as pending-review only")
    legacy_main.main()


if __name__ == "__main__":
    main()
