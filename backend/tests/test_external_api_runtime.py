"""Concurrency and serialized-dispatch tests for the external API runtime."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Event
from typing import Any

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
