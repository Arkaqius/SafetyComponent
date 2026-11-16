"""Own callback resources and fence obsolete safety evaluation generations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any
from uuid import uuid4

Callback = Callable[..., Any]
Registrar = Callable[[Callback], Any]
Canceller = Callable[[Any], Any]


class LifecyclePhase(str, Enum):
    """Registration lifetime, independent of evaluation eligibility."""

    CONSTRUCTED = "constructed"
    STARTED = "started"
    STOPPED = "stopped"


class CancellationKind(str, Enum):
    """Explicit cancellation adapter for an owned resource."""

    STATE = "state"
    EVENT = "event"
    TIMER = "timer"
    EVENT_BUS = "event_bus"


@dataclass(frozen=True)
class Registration:
    """Finite declared input recreated for a new callback generation."""

    kind: CancellationKind
    register: Registrar
    callback: Callback
    cancel: Canceller


@dataclass
class CancellationHandle:
    """Single resource slot installed before calling its registration adapter."""

    kind: CancellationKind
    cancel: Canceller
    value: Any = None


class LifecycleScope:
    """Own inputs and one timer per domain channel on the application thread.

    Assertions and process-owned external service leases do not belong here.
    Cancellation failure remains visible while identity fencing denies late effects.
    """

    def __init__(
        self, owner_id: str, *, runtime_id: str | None = None,
        enabled: bool = False, parent: LifecycleScope | None = None,
    ) -> None:
        self.owner_id = owner_id
        self.runtime_id: str = runtime_id or (parent.runtime_id if parent else uuid4().hex)
        self.generation = 0
        self.phase = LifecyclePhase.CONSTRUCTED
        self.enabled = enabled
        self.parent = parent
        self.cancellation_failures = 0
        self.last_cancellation_error: str | None = None
        self._declarations: dict[str, Registration] = {}
        self._handles: dict[str, CancellationHandle] = {}
        self._children: dict[str, LifecycleScope] = {}

    @property
    def handle_count(self) -> int:
        """Count handles belonging directly to this scope."""
        return len(self._handles)

    def handle(self, key: str) -> Any:
        """Return the current raw adapter handle for legacy domain bookkeeping."""
        current = self._handles.get(key)
        return current.value if current is not None else None

    @property
    def eligible(self) -> bool:
        """Require started enabled scope and eligible ancestors."""
        return (
            self.phase == LifecyclePhase.STARTED and self.enabled
            and (self.parent is None or self.parent.eligible)
        )

    def child(self, owner_id: str, *, enabled: bool = False) -> LifecycleScope:
        """Return a unique child without duplicating its parent's shared inputs."""
        if owner_id not in self._children:
            self._children[owner_id] = LifecycleScope(owner_id, enabled=enabled, parent=self)
        return self._children[owner_id]

    def declare(
        self, key: str, kind: CancellationKind, register: Registrar,
        callback: Callback, cancel: Canceller,
    ) -> None:
        """Declare a stable registration identity once; construction stays inert."""
        if key in self._declarations:
            return
        self._declarations[key] = Registration(kind, register, callback, cancel)
        if self.phase == LifecyclePhase.STARTED:
            self._register(key, self._declarations[key])

    def undeclare(self, key: str) -> None:
        """Permanently unsubscribe, including future generations of this scope."""
        self._declarations.pop(key, None)
        self.cancel(key)

    def start(self) -> None:
        """Register declared inputs once without implicitly enabling execution."""
        if self.phase == LifecyclePhase.STARTED:
            return
        self.generation += 1
        self.phase = LifecyclePhase.STARTED
        try:
            self._register_inputs()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        """Invalidate before cancellation and discard pending qualification."""
        if self.phase == LifecyclePhase.STOPPED:
            return
        self.generation += 1
        self.phase = LifecyclePhase.STOPPED
        self.enabled = False
        for child in self._children.values():
            child.stop()
        self._cancel_all()

    def set_enabled(self, enabled: bool) -> None:
        """Invalidate eligibility changes and replace old callback closures."""
        if self.enabled == enabled:
            return
        self.enabled = enabled
        if not enabled:
            self.invalidate()

    def invalidate(self) -> None:
        """Discard timers and rebind inputs while preserving enabled intent."""
        self.generation += 1
        self._cancel_all()
        for child in self._children.values():
            child.invalidate()
        if self.phase == LifecyclePhase.STARTED:
            self._register_inputs()

    def _identity(self) -> tuple[Any, ...]:
        return (self.runtime_id, self.generation,
                self.parent._identity() if self.parent else None)

    def guard(self, callback: Callback) -> Callback:
        """Capture owner identity to reject cancelled and already queued callbacks."""
        identity = self._identity()

        def guarded(*args: Any, **kwargs: Any) -> Any:
            if self.eligible and identity == self._identity():
                return callback(*args, **kwargs)
            return None

        return guarded

    def schedule(
        self, channel: str, register: Registrar, callback: Callback, cancel: Canceller,
    ) -> Any:
        """Replace one qualification timer; never accumulate historical handles."""
        key = f"timer:{channel}"
        self.cancel(key)
        if not self.eligible:
            return None
        return self._register(key, Registration(
            CancellationKind.TIMER, register, callback, cancel
        ), once=True)

    def cancel(self, key: str) -> None:
        """Drop ownership before cancelling so even failed cancellation is fenced."""
        handle = self._handles.pop(key, None)
        if handle is None or handle.value is None:
            return
        self._cancel_resource(handle)

    def _cancel_resource(self, handle: CancellationHandle) -> None:
        try:
            if handle.cancel(handle.value) is False:
                raise RuntimeError("Adapter reported cancellation failure")
        except Exception as exc:
            self.cancellation_failures += 1
            self.last_cancellation_error = f"{handle.kind.value}: {exc}"[:512]

    def cancel_handle(self, value: Any) -> None:
        """Cancel a legacy raw handle through its sole owning resource slot."""
        for key, handle in tuple(self._handles.items()):
            if handle.value is value:
                self.cancel(key)
                return

    def _register_inputs(self) -> None:
        for key, registration in self._declarations.items():
            self._register(key, registration)

    def _register(self, key: str, registration: Registration, *, once: bool = False) -> Any:
        if key in self._handles:
            return self._handles[key].value
        handle = CancellationHandle(registration.kind, registration.cancel)
        self._handles[key] = handle

        def deliver(*args: Any, **kwargs: Any) -> Any:
            if self._handles.get(key) is not handle:
                return None
            if once:
                self._handles.pop(key)
            return registration.callback(*args, **kwargs)

        try:
            guarded = wraps(registration.callback)(self.guard(deliver))
            handle.value = registration.register(guarded)
            if not once and self._handles.get(key) is not handle and handle.value is not None:
                self._cancel_resource(handle)
        except Exception:
            self._handles.pop(key, None)
            raise
        return handle.value

    def _cancel_all(self) -> None:
        for key in tuple(self._handles):
            self.cancel(key)
