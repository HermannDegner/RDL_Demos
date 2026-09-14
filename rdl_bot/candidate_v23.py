"""Opt-in candidate cutover for the next rdl_bot migration stage.

This module is deliberately not the default CLI path yet.  It keeps the real
``UnresolvedInputQueue`` for deferred inputs while presenting a threshold-neutral
view to the legacy ``main.respond`` function.  The only intended semantic
change is removal of the historical unresolved-queue-length -> local-threshold
coupling.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

try:
    from .local_state import ThresholdNeutralQueueView, UnresolvedInputQueue
    from .runtime_v23 import V23ConversationShadow, respond_with_shadow
except ImportError:
    from local_state import ThresholdNeutralQueueView, UnresolvedInputQueue  # type: ignore
    from runtime_v23 import V23ConversationShadow, respond_with_shadow  # type: ignore


def respond_without_queue_threshold(
    user_input: str,
    graph: Any,
    h: Any,
    llm: Any,
    sfo_profile: Any,
    unresolved_queue: UnresolvedInputQueue,
    llm_trust: Any,
    *,
    shadow: Optional[V23ConversationShadow] = None,
    legacy_respond: Optional[Callable[..., tuple[str, str]]] = None,
) -> tuple[str, str]:
    """Run one candidate turn with unresolved-queue pressure removed from theta.

    Deferred-input writes are preserved in ``unresolved_queue``.  This function
    does not yet replace the legacy feedback-load or leap path; those are later
    migration gates.
    """

    neutral_view = ThresholdNeutralQueueView(unresolved_queue)
    return respond_with_shadow(
        user_input,
        graph,
        h,
        llm,
        sfo_profile,
        neutral_view,
        llm_trust,
        shadow=shadow,
        legacy_respond=legacy_respond,
    )
