"""Named bot-local compatibility states that are not Core primitives.

The legacy runtime historically called its unresolved text backlog ``xi_pool``.
Its actual role is much narrower: it stores raw inputs that could not yet be
materialized as graph nodes and retries them during maintenance.  This module
provides the canonical implementation name without changing list semantics.
"""

from __future__ import annotations

from typing import Iterable, Iterator


class UnresolvedInputQueue(list[str]):
    """Raw inputs awaiting later graph materialization.

    This is a coverage / deferred-processing queue.  Its length can be used by
    the historical local threshold policy for compatibility, but the queue is
    not Core xi and its length is not a measurement of xi.
    """

    def __init__(self, values: Iterable[str] = ()) -> None:
        super().__init__(str(value) for value in values)

    def hold(self, text: str) -> None:
        self.append(str(text))

    def replace_pending(self, values: Iterable[str]) -> None:
        self[:] = [str(value) for value in values]

    def pending(self) -> tuple[str, ...]:
        return tuple(self)

    def __iter__(self) -> Iterator[str]:
        return super().__iter__()


# Historical vocabulary note only; do not introduce a XiPool alias here.
# Existing main.py arguments named ``xi_pool`` continue to accept this object
# because it is list-compatible.  New code should use UnresolvedInputQueue.
