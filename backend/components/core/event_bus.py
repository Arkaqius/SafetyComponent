"""Simple synchronous event bus with deterministic ordering."""

from __future__ import annotations

from itertools import count
from dataclasses import dataclass
from typing import Any, Callable

from components.core.lifecycle import CancellationKind, LifecycleScope


@dataclass(eq=False)
class Subscription:
    """Stable registration identity and idempotent unsubscribe token."""

    event_type: str
    handler: Callable[..., None]
    priority: int
    order: int
    scope: LifecycleScope | None
    _remove: Callable[["Subscription"], None]
    active: bool = False
    callback: Callable[..., Any] | None = None

    def cancel(self) -> None:
        """Stop delivery without changing another subscriber's ownership."""
        self._remove(self)


class EventBus:
    """Publish/subscribe event bus with priority-based ordering."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscription]] = {}
        self._tokens: list[Subscription] = []
        self._counter = count()

    def subscribe(
        self, event_type: str, handler: Callable[..., None], *, priority: int = 0,
        scope: LifecycleScope | None = None,
    ) -> Subscription:
        """Register once per handler/priority/owner, optionally owned by a scope."""
        for token in self._tokens:
            if (token.event_type == event_type and token.handler == handler
                    and token.priority == priority and token.scope is scope):
                return token
        order = next(self._counter)
        token = Subscription(event_type, handler, priority, order, scope, self._unsubscribe)
        self._tokens.append(token)
        if scope is None:
            self._activate(token, handler)
        else:
            scope.declare(
                f"eventbus:{id(self)}:{order}", CancellationKind.EVENT_BUS,
                lambda callback: self._activate(token, callback), handler,
                self._remove,
            )
        return token

    def _activate(self, token: Subscription, callback: Callable[..., Any]) -> Subscription:
        token.active = True
        token.callback = callback
        subscribers = self._subscribers.setdefault(token.event_type, [])
        if token not in subscribers:
            subscribers.append(token)
            subscribers.sort(key=lambda item: (item.priority, item.order))
        return token

    def _remove(self, token: Subscription) -> None:
        token.active = False
        subscribers = self._subscribers.get(token.event_type, [])
        if token in subscribers:
            subscribers.remove(token)
        if token.scope is None and token in self._tokens:
            self._tokens.remove(token)

    def _unsubscribe(self, token: Subscription) -> None:
        if token.scope is not None:
            token.scope.undeclare(f"eventbus:{id(self)}:{token.order}")
        self._remove(token)
        if token in self._tokens:
            self._tokens.remove(token)

    def publish(self, event_type: str, **payload: Any) -> None:
        """Publish an event to all subscribers synchronously."""
        deliveries = tuple((token, token.callback) for token in self._subscribers.get(event_type, []))
        for token, callback in deliveries:
            if token.active and callback is not None:
                callback(**payload)

    def clear(self) -> None:
        """Remove all subscriptions (primarily for tests)."""
        for token in tuple(self._tokens):
            token.cancel()
        self._subscribers.clear()
        self._tokens.clear()
