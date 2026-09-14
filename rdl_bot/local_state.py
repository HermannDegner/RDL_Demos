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


class ThresholdNeutralQueueView:
    """Compatibility view that preserves queue writes but exposes zero pressure.

    The legacy response path obtains its local threshold pressure from
    ``len(xi_pool)``.  This view deliberately reports length zero while routing
    ``append`` and iteration to the real unresolved-input queue.  It therefore
    lets migration tests cut only the queue->threshold coupling without losing
    deferred inputs.

    This is a transition mechanism, not a Core object.
    """

    def __init__(self, queue: UnresolvedInputQueue | list[str]) -> None:
        self.queue = queue

    def __len__(self) -> int:
        return 0

    def __bool__(self) -> bool:
        return False

    def append(self, value: str) -> None:
        self.queue.append(str(value))

    def __iter__(self):
        return iter(self.queue)

    def __getitem__(self, index):
        return self.queue[index]

    def pending(self) -> tuple[str, ...]:
        return tuple(self.queue)


# Historical vocabulary note only; do not introduce a XiPool alias here.
# Existing main.py arguments named ``xi_pool`` continue to accept
# UnresolvedInputQueue because it is list-compatible.  New code should use the
# role name above.  ThresholdNeutralQueueView is only for the staged step that
# removes the legacy queue-length -> threshold coupling.
