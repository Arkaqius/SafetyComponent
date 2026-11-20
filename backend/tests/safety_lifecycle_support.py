"""Deterministic, household-free lifecycle and callback transport fixtures."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any


FAMILY_INPUTS = {
    "temperature": ("sensor.fixture_temperature", "sensor.fixture_temperature_rate"),
    "doors": ("binary_sensor.fixture_door", "input_boolean.fixture_condition"),
    "entity_monitor": ("sensor.fixture_health",),
    "heating": ("sensor.fixture_flow",),
    "indoor": ("binary_sensor.fixture_smoke",),
    "external": ("binary_sensor.fixture_window",),
}


@dataclass
class FakeMonotonicClock:
    """Advance receiver time explicitly without sleeping or wall-clock credit."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move time forwards; callbacks are driven separately by each test."""
        if seconds < 0:
            raise ValueError("Monotonic clock cannot move backwards")
        self.now += seconds


class LifecycleHass:
    """Account for handles and retain cancelled callbacks for late-delivery tests."""

    def __init__(self) -> None:
        self.clock = FakeMonotonicClock()
        self.handles: dict[int, tuple[str, Callable[..., Any], Any, dict[str, Any]]] = {}
        self.cancelled: set[int] = set()
        self.fail_cancellation = False
        self._sequence = 0
        self.logs: list[tuple[str, str]] = []
        self.evaluations: list[tuple[str, bool]] = []

    def _register(
        self, kind: str, callback: Callable[..., Any], subject: Any, kwargs: dict[str, Any]
    ) -> int:
        self._sequence += 1
        self.handles[self._sequence] = (kind, callback, subject, kwargs)
        return self._sequence

    def listen_state(self, callback: Callable[..., Any], entity: str, **kwargs: Any) -> int:
        """Register an explicit source; never deliver an initial snapshot implicitly."""
        return self._register("state", callback, entity, kwargs)

    def listen_event(self, callback: Callable[..., Any], event: str, **kwargs: Any) -> int:
        """Record the exact event and subscription options."""
        return self._register("event", callback, event, kwargs)

    def run_in(self, callback: Callable[..., Any], delay: float, **kwargs: Any) -> int:
        """Schedule one owned callback without executing it recursively."""
        return self._register("timer", callback, self.clock() + delay, kwargs)

    def run_every(
        self, callback: Callable[..., Any], start: Any, interval: float, **kwargs: Any
    ) -> int:
        """Record a periodic source sampler under one handle."""
        return self._register("periodic", callback, (start, interval), kwargs)

    def cancel_timer(self, handle: int) -> None:
        """Inject cancellation failure without losing the original callback."""
        if self.fail_cancellation:
            raise RuntimeError("injected cancellation failure")
        self.cancelled.add(handle)

    cancel_listen_state = cancel_timer
    cancel_listen_event = cancel_timer

    def deliver(self, handle: int, *args: Any) -> Any:
        """Deliver even a cancelled callback, modeling an already queued event."""
        _, callback, _, kwargs = self.handles[handle]
        return callback(*args, **kwargs)

    def log(self, message: str, *, level: str = "INFO") -> None:
        """Retain local diagnostics without publishing another fault event."""
        self.logs.append((level, message))

    def record_safety_evaluation(self, owner: str, *, success: bool = True) -> None:
        """Capture once-only telemetry for a real evaluation."""
        self.evaluations.append((owner, success))


class CallbackServiceAdapter:
    """Model immediate, delayed, duplicate and permanently absent completions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.callbacks: list[Callable[..., Any]] = []
        self.mode = "delayed"
        self.result: Any = None

    def call_service(
        self, service: str, *, callback: Callable[..., Any], **payload: Any
    ) -> str:
        """Return scheduling identity independently of callback acceptance."""
        forbidden = {"return_result", "timeout", "hass_timeout"}.intersection(payload)
        if forbidden:
            raise AssertionError(f"Unsupported service parameters: {sorted(forbidden)}")
        self.calls.append((service, payload))
        self.callbacks.append(callback)
        if self.mode in {"immediate", "duplicate"}:
            callback(self.result)
            if self.mode == "duplicate":
                callback(self.result)
        return f"scheduled-{len(self.calls)}"

    def complete(self, index: int, result: Any = None) -> None:
        """Complete a recorded operation; repeated calls model duplicate delivery."""
        if self.mode != "never":
            self.callbacks[index](result)


class InlineStorageExecutor:
    """Complete explicitly fictional startup storage on the test thread."""

    def submit(self, function: Callable[..., Any], *args: Any) -> Future:
        """Preserve Future acknowledgements without production worker scheduling."""
        future: Future = Future()
        future.set_result(function(*args))
        return future


class ControlledExecutor:
    """Run exactly one admitted storage job when the test requests completion."""

    def __init__(self) -> None:
        self.jobs: list[tuple[Future, Callable[..., Any], tuple[Any, ...]]] = []

    def submit(self, function: Callable[..., Any], *args: Any) -> Future:
        """Retain a job without starting any real worker or storage operation."""
        future: Future = Future()
        self.jobs.append((future, function, args))
        return future

    def finish(self, index: int) -> None:
        """Complete a fictional worker job independently of owner admission."""
        future, function, args = self.jobs[index]
        future.set_result(function(*args))
