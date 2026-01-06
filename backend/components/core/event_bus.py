"""Simple synchronous event bus with deterministic ordering."""

from __future__ import annotations

from itertools import count
from typing import Any, Callable, Dict, List, Tuple


class EventBus:
    """Publish/subscribe event bus with priority-based ordering."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Tuple[int, int, Callable[..., None]]]] = {}
        self._counter = count()

    def subscribe(
        self, event_type: str, handler: Callable[..., None], *, priority: int = 0
    ) -> None:
        """Register a handler for an event type with an optional priority."""
        order = next(self._counter)
        self._subscribers.setdefault(event_type, []).append((priority, order, handler))
        self._subscribers[event_type].sort(key=lambda item: (item[0], item[1]))

    def publish(self, event_type: str, **payload: Any) -> None:
        """Publish an event to all subscribers synchronously."""
        for _, __, handler in self._subscribers.get(event_type, []):
            handler(**payload)

    def clear(self) -> None:
        """Remove all subscriptions (primarily for tests)."""
        self._subscribers.clear()
