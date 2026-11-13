"""Concurrency and serialized-dispatch tests for the external API runtime."""

from __future__ import annotations

import time
from concurrent.futures import Future
from datetime import datetime, timezone
from threading import Event
from typing import Any
from collections.abc import Callable

from components.core.event_bus import EventBus
from components.external_apis.core.api_runtime import ExternalApiRuntime
from components.external_apis.core.models import ApiResult, ProviderHealth, ProviderHealthState


class RuntimeHass:
    def __init__(self) -> None:
        self.timers: list[Any] = []
        self.logs: list[tuple[str, str]] = []

    def run_every(self, callback: Any, start: Any, interval: int, **kwargs: Any) -> Any:
        handle = callback, start, interval, kwargs
        self.timers.append(handle)
        return handle

    def cancel_timer(self, handle: Any) -> None:
        self.timers.remove(handle)

    def log(self, message: str, *, level: str = "INFO") -> None:
        self.logs.append((level, message))


class StubProvider:
    def __init__(self, name: str, gate: Event | None = None) -> None:
        self.name = name
        self.gate = gate
        self.poll_interval_seconds = 300
        self.calls = 0

    def poll(self) -> ApiResult:
        self.calls += 1
        if self.gate is not None:
            assert self.gate.wait(timeout=2)
        now = datetime.now(timezone.utc)
        return ApiResult(
            provider=self.name,
            observations=(),
            health=ProviderHealth(
                provider=self.name,
                state=ProviderHealthState.OK,
                last_attempt_at=now,
                last_success_at=now,
                consecutive_failures=0,
                stale_after_seconds=900,
            ),
        )


def test_stalled_provider_does_not_block_other_provider_and_one_call_is_in_flight() -> None:
    hass = RuntimeHass()
    bus = EventBus()
    delivered: list[str] = []
    bus.subscribe(
        "external_api_result", lambda *, result: delivered.append(result.provider)
    )
    gate = Event()
    slow = StubProvider("SlowProvider", gate)
    fast = StubProvider("FastProvider")
    runtime = ExternalApiRuntime(hass, bus, {"SlowProvider": slow, "FastProvider": fast})

    assert runtime.request_poll("SlowProvider") is True
    assert runtime.request_poll("SlowProvider") is False
    assert runtime.request_poll("FastProvider") is True

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not delivered:
        runtime.drain_results()
        time.sleep(0.01)
    assert delivered == ["FastProvider"]

    gate.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and delivered != ["FastProvider", "SlowProvider"]:
        runtime.drain_results()
        time.sleep(0.01)
    assert delivered == ["FastProvider", "SlowProvider"]
    assert slow.calls == 1

    runtime.stop()


def _wait_for(predicate: Callable[[], bool]) -> None:
    """Wait only for bounded local worker completion, never a real provider."""
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert predicate()


def test_start_preserves_each_provider_schedule_and_stop_cancels_all() -> None:
    """Provider polling cadences remain independent from serialized dispatch."""
    hass = RuntimeHass()
    first = StubProvider("FirstProvider")
    second = StubProvider("SecondProvider")
    second.poll_interval_seconds = 600
    runtime = ExternalApiRuntime(hass, EventBus(), {
        "FirstProvider": first, "SecondProvider": second,
    })
    try:
        runtime.start()
        schedules = {handle[3]["provider"]: handle[2] for handle in hass.timers if "provider" in handle[3]}
        assert schedules == {"FirstProvider": 300, "SecondProvider": 600}
        assert any(handle[2] == 1 and not handle[3] for handle in hass.timers)
        _wait_for(lambda: not runtime._in_flight)
        assert first.calls == second.calls == 1
    finally:
        runtime.stop()
    assert hass.timers == []
    assert runtime.request_poll("FirstProvider") is False


def test_stop_suppresses_in_flight_result_and_late_dispatch() -> None:
    """A result completing after shutdown must never reach decision consumers."""
    hass = RuntimeHass()
    bus = EventBus()
    delivered: list[str] = []
    bus.subscribe("external_api_result", lambda *, result: delivered.append(result.provider))
    gate = Event()
    runtime = ExternalApiRuntime(hass, bus, {"SlowProvider": StubProvider("SlowProvider", gate)})
    assert runtime.request_poll("SlowProvider")
    runtime.stop()
    gate.set()
    _wait_for(lambda: not runtime._in_flight)
    runtime.drain_results()
    assert delivered == []
    assert runtime.request_poll("SlowProvider") is False


def test_result_queue_is_bounded_and_overflow_keeps_latest_snapshot() -> None:
    """Backpressure drops old results explicitly without blocking worker peers."""
    hass = RuntimeHass()
    bus = EventBus()
    delivered: list[str] = []
    bus.subscribe("external_api_result", lambda *, result: delivered.append(result.provider))
    runtime = ExternalApiRuntime(hass, bus, {
        "FirstProvider": StubProvider("FirstProvider"),
        "SecondProvider": StubProvider("SecondProvider"),
    }, max_queue_size=1)
    try:
        assert runtime.request_poll("FirstProvider")
        _wait_for(lambda: not runtime._in_flight and runtime._results.qsize() == 1)
        assert runtime.request_poll("SecondProvider")
        _wait_for(lambda: not runtime._in_flight and bool(hass.logs))
        assert runtime._results.qsize() == 1
        runtime.drain_results()
        assert delivered == ["SecondProvider"]
        assert any("overflowed" in message for _, message in hass.logs)
    finally:
        runtime.stop()


def test_shutdown_during_worker_completion_cannot_enqueue_or_dispatch() -> None:
    """Shutdown can race a completed result after the first stopping check."""
    bus = EventBus()
    delivered: list[str] = []
    bus.subscribe("external_api_result", lambda *, result: delivered.append(result.provider))
    provider = StubProvider("FirstProvider")
    runtime = ExternalApiRuntime(RuntimeHass(), bus, {provider.name: provider})

    class StopDuringResult(Future[ApiResult]):
        def result(self, timeout: float | None = None) -> ApiResult:
            runtime.stop()
            return super().result(timeout)

    future = StopDuringResult()
    future.set_result(provider.poll())
    runtime._poll_completed(provider.name, future)
    runtime.drain_results()
    assert runtime._results.empty()
    assert delivered == []
