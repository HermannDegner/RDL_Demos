"""Demo-local naming bridge for the village dialogue subsystem.

The historical ``RelationalDialogueSystem.xi_pool`` stores unresolved
``(speech_act, topic)`` pairs.  It is a deferred dialogue-routing queue, not
Core xi.  This module exposes the actual role name without changing existing
simulation storage or seeded behaviour.
"""

from __future__ import annotations

from .dialogue import RelationalDialogueSystem


def _get_unresolved_dialogue_queue(self):
    return self.xi_pool


def _set_unresolved_dialogue_queue(self, value):
    self.xi_pool = value


if not hasattr(RelationalDialogueSystem, "unresolved_dialogue_queue"):
    RelationalDialogueSystem.unresolved_dialogue_queue = property(  # type: ignore[attr-defined]
        _get_unresolved_dialogue_queue,
        _set_unresolved_dialogue_queue,
    )
