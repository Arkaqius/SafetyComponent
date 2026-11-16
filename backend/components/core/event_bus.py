"""Simple synchronous event bus with deterministic ordering."""

from __future__ import annotations

from itertools import count
from dataclasses import dataclass
from collections import deque
from typing import Any, Callable

from components.core.lifecycle import CancellationKind, LifecycleScope
from components.core.response_events import FaultResponseEvent


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
    isolated: bool = False
    immutable: bool = False

    def cancel(self) -> None:
        """Stop delivery without changing another subscriber's ownership."""
        self._remove(self)


class EventBus:
    """Publish/subscribe event bus with priority-based ordering."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscription]] = {}
        self._tokens: list[Subscription] = []
        self._counter = count()
        self.admission_failures = 0
        self.last_admission_error: str | None = None
        self._response_catalog: frozenset[str] = frozenset()
        self._response_runtime: str | None = None
        self._response_receipts: dict[str, dict[int, tuple[str, int]]] = {}
        self._response_pending: deque[tuple[FaultResponseEvent, dict[str, Any]]] = deque()
        self._response_dispatching = False

    def subscribe(
        self, event_type: str, handler: Callable[..., None], *, priority: int = 0,
        scope: LifecycleScope | None = None,
        isolated: bool = False, immutable: bool = False,
    ) -> Subscription:
        """Register once per handler/priority/owner, optionally owned by a scope."""
        for token in self._tokens:
            if (token.event_type == event_type and token.handler == handler
                    and token.priority == priority and token.scope is scope
                    and token.isolated == isolated and token.immutable == immutable):
                return token
        order = next(self._counter)
        token = Subscription(event_type, handler, priority, order, scope, self._unsubscribe)
        token.isolated, token.immutable = isolated, immutable
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
        for receipts in self._response_receipts.values():
            receipts.pop(token.order, None)

    def subscribe_response(
        self, handler: Callable[[FaultResponseEvent], None], *, priority: int = 0,
        scope: LifecycleScope | None = None,
    ) -> Subscription:
        """Register an explicitly isolated immutable response-consumer boundary."""
        return self.subscribe("fault", handler, priority=priority, scope=scope,
                              isolated=True, immutable=True)

    def configure_response_catalog(self, fault_ids: frozenset[str], *, runtime_id: str | None = None) -> None:
        """Bound consumer receipts to the current trusted fault catalog."""
        self._response_catalog = fault_ids
        self._response_runtime = runtime_id
        self._response_receipts = {key: value for key, value in self._response_receipts.items()
                                   if key in fault_ids}

    def publish_response(self, event: FaultResponseEvent, **legacy: Any) -> None:
        """Admit one revision once per consumer without recursively publishing errors."""
        if event.fault_id not in self._response_catalog:
            raise ValueError("Response fault is outside the trusted catalog")
        if self._response_runtime is not None and event.runtime_id != self._response_runtime:
            return
        if len(self._response_pending) >= 1024:
            self.admission_failures += 1
            self.last_admission_error = "response_admission_overload"
            return
        copied = dict(legacy)
        if "additional_info" in copied:
            copied["additional_info"] = event.context
        self._response_pending.append((event, copied))
        if self._response_dispatching:
            return
        self._response_dispatching = True
        try:
            for _ in range(1024):
                if not self._response_pending:
                    break
                current, payload = self._response_pending.popleft()
                self._deliver_response(current, payload)
            if self._response_pending:
                self.admission_failures += len(self._response_pending)
                self.last_admission_error = "response_admission_work_limit"
                self._response_pending.clear()
        except Exception:
            self._response_pending.clear()
            raise
        finally:
            self._response_dispatching = False

    def _deliver_response(self, event: FaultResponseEvent, legacy: dict[str, Any]) -> None:
        receipts = self._response_receipts.setdefault(event.fault_id, {})
        deliveries = tuple((token, token.callback) for token in self._subscribers.get("fault", []))
        for token, callback in deliveries:
            previous = receipts.get(token.order)
            if previous is not None and previous[1] >= event.revision:
                continue
            if not token.active or callback is None:
                continue
            if not token.immutable and not legacy:
                continue
            # Store attempted admission before invoking reentrant owner code; never replay a command.
            receipts[token.order] = (event.incident_id, event.revision)
            try:
                if token.immutable:
                    callback(event)
                elif legacy:
                    callback(**legacy)
            except Exception as exc:
                if not token.isolated:
                    raise
                self._admission_failed(token, exc)

    def _admission_failed(self, token: Subscription, exc: Exception) -> None:
        self.admission_failures += 1
        self.last_admission_error = f"{token.event_type}:{token.order}:{type(exc).__name__}"[:512]

    def publish(self, event_type: str, **payload: Any) -> None:
        """Publish an event to all subscribers synchronously."""
        deliveries = tuple((token, token.callback) for token in self._subscribers.get(event_type, []))
        for token, callback in deliveries:
            if token.active and callback is not None:
                try:
                    if token.immutable:
                        raise ValueError("Immutable responses require publish_response")
                    callback(**payload)
                except Exception as exc:
                    if not token.isolated:
                        raise
                    self._admission_failed(token, exc)

    def clear(self) -> None:
        """Remove all subscriptions (primarily for tests)."""
        for token in tuple(self._tokens):
            token.cancel()
        self._subscribers.clear()
        self._tokens.clear()
        self._response_receipts.clear()
        self._response_pending.clear()
