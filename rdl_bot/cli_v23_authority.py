"""Opt-in canonical action-authority CLI for rdl_bot Core v2.3 migration.

This entrypoint is the controlled authority cutover test.  It leaves default
``main.py`` untouched, but disables the legacy H-based leap/correction decision
inside this process.  Ordinary response routing, legacy feedback recording,
LLM trust and maintenance continue to run; graph reconstruction mutation is
available only through the reviewed canonical ``/v23 execute`` path installed
by :mod:`cli_v23`.

Usage::

    python cli_v23_authority.py
    python cli_v23_authority.py --seed

Safety properties:
- no automatic legacy leap/correction graph mutation;
- non-zero canonical E remains pending until explicit review;
- canonical H changes only after explicit unresolved review;
- mutation requires explicit ``/v23 execute``;
- default ``main.py`` behavior is unaffected outside this entrypoint.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    from .cli_v23 import V23_SESSION_STATE_PATH, install_shadow_session
except ImportError:
    from cli_v23 import V23_SESSION_STATE_PATH, install_shadow_session  # type: ignore


def install_canonical_action_authority(legacy_main: Any) -> Callable[..., Any]:
    """Disable legacy leap/correction decisions for this process only.

    The returned callable is the original ``_decide_leap`` so tests or embedding
    code can restore it explicitly.  We intentionally intercept the decision
    boundary rather than rewriting legacy H state: feedback/load can remain
    observable while no longer authorizing mutation in this mode.
    """

    original = legacy_main._decide_leap

    def canonical_authority_no_legacy_leap(*_args, **_kwargs):
        return None

    legacy_main._decide_leap = canonical_authority_no_legacy_leap
    return original


def main() -> None:
    try:
        from . import main as legacy_main
    except ImportError:
        import main as legacy_main  # type: ignore

    install_canonical_action_authority(legacy_main)
    session = install_shadow_session(legacy_main, state_path=V23_SESSION_STATE_PATH)

    print("  [v2.3 authority] legacy H-based leap/correction authority DISABLED")
    print("  [v2.3 authority] canonical comparison/review state is durable")
    print("  [v2.3 authority] graph reconstruction mutation requires explicit /v23 execute")
    print(
        f"  [v2.3 authority] last_turn_id={session.shadow.last_assigned_index} "
        f"pending={len(session.pending_records)} reviews={len(session.reviews)} "
        f"executions={len(session.executions)}"
    )
    legacy_main.main()


if __name__ == "__main__":
    main()
