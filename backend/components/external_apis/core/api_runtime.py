"""Concurrent provider polling with serialized EventBus dispatch."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic
from typing import Any, Mapping

from components.core.event_bus import EventBus

from .api_component import ExternalApiComponent
from .models import ApiResult, DispatchTiming


class ExternalApiRuntime:
    """Run providers independently and return results on AppDaemon's callback thread."""

    def __init__(
        self,
        hass_app: Any,
        event_bus: EventBus,
        components: Mapping[str, ExternalApiComponent],
        *,
        max_queue_size: int = 64,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if isinstance(max_queue_size, bool) or not isinstance(max_queue_size, int) or not 1 <= max_queue_size <= 64:
            raise ValueError("External result queue requires 1 through 64 slots")
        self.hass_app = hass_app
        self.event_bus = event_bus
        self.components = dict(components)
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, len(self.components)),
            thread_name_prefix="external-api",
        )
        self._results: Queue[tuple[ApiResult, float]] = Queue(maxsize=max_queue_size)
        self._drain_limit = max_queue_size
        self._clock = clock
        self.queue_overflows = 0
        self.dispatch_overruns = 0
        self.maximum_dispatch_delay_seconds = 0.0
        self._in_flight: set[str] = set()
        self._lock = Lock()
        self._continuity_lost: set[str] = set()
        self._pending_providers: dict[str, int] = {}
        self._timer_handles: list[Any] = []
        self._stopping = False

    def start(self) -> None:
        """Start dispatch and independent polling schedules."""

        if self._stopping:
            return
        self._timer_handles.append(self.hass_app.run_every(self.drain_results, "now", 1))
        for name, component in self.components.items():
            self.request_poll(name)
            start_at = datetime.now(timezone.utc) + timedelta(
                seconds=component.poll_interval_seconds
            )
            handle = self.hass_app.run_every(
                self._scheduled_poll,
                start_at,
                component.poll_interval_seconds,
                provider=name,
            )
            self._timer_handles.append(handle)

    def request_poll(self, provider: str) -> bool:
        """Submit one provider if it is not already in flight."""

        if self._stopping or provider not in self.components:
            return False
        with self._lock:
            if provider in self._in_flight:
                return False
            self._in_flight.add(provider)
        future = self._executor.submit(self.components[provider].poll)
        def completed_callback(completed: Future[ApiResult], provider_name: str = provider) -> None:
            self._poll_completed(provider_name, completed)

        future.add_done_callback(completed_callback)
        return True

    def _scheduled_poll(self, **kwargs: Any) -> None:
        self.request_poll(str(kwargs["provider"]))

    def _poll_completed(self, provider: str, future: Future[ApiResult]) -> None:
        received = self._clock()
        with self._lock:
            self._in_flight.discard(provider)
        if self._stopping:
            return
        try:
            result = future.result()
        except Exception as exc:  # defensive boundary around provider worker
            self.hass_app.log(
                f"Unhandled external provider failure for {provider}: {exc}",
                level="ERROR",
            )
            return
        if self._stopping:
            return
        if result.provider != provider or result.health.provider != provider:
            self.hass_app.log(
                f"External provider result identity mismatch for {provider}", level="ERROR"
            )
            return
        overflow = False
        with self._lock:
            if self._stopping:
                return
            try:
                self._results.put_nowait((result, received))
            except Full:
                dropped, _ = self._results.get_nowait()
                self._pending_providers[dropped.provider] -= 1
                self._continuity_lost.add(dropped.provider)
                self._results.put_nowait((result, received))
                self.queue_overflows += 1
                overflow = True
            self._pending_providers[provider] = self._pending_providers.get(provider, 0) + 1
        if overflow:
            self.hass_app.log(
                "External provider result queue overflowed; oldest result discarded",
                level="WARNING",
            )

    def continuity_available(self, provider: str) -> bool:
        """Let owner timers reject old cache while newer or dropped input is pending."""
        return self.continuity_state(provider) == "available"

    def continuity_state(self, provider: str) -> str:
        """Distinguish a normal queued snapshot from a proven dropped interval."""
        with self._lock:
            if self._stopping or provider not in self.components:
                return "stopped"
            if provider in self._continuity_lost:
                return "lost"
            return "pending" if self._pending_providers.get(provider, 0) else "available"

    def drain_results(self, **_: Any) -> None:
        """Publish queued results synchronously through the EventBus."""

        if self._stopping:
            return
        for _index in range(self._drain_limit):
            with self._lock:
                discontinuities = tuple(self._continuity_lost)
                self._continuity_lost.clear()
            for provider in discontinuities:
                self.event_bus.publish("external_api_discontinuity", provider=provider)
            with self._lock:
                try:
                    result, received = self._results.get_nowait()
                except Empty:
                    return
                self._pending_providers[result.provider] -= 1
            component = self.components.get(result.provider)
            if component is None:
                continue
            kind = component.data_kind
            if kind not in {"live", "synthetic"}:
                self.hass_app.log("Invalid trusted external provider data kind", level="ERROR")
                continue
            event = "external_api_test_result" if kind == "synthetic" else "external_api_result"
            timing = DispatchTiming(received, self._clock(), False)
            timing = replace(timing, overdue=timing.delay_seconds > 5)
            self.maximum_dispatch_delay_seconds = max(self.maximum_dispatch_delay_seconds, timing.delay_seconds)
            self.dispatch_overruns += int(timing.overdue)
            result = replace(result, dispatch_timing=timing)
            self.event_bus.publish(event, result=result)

    def stop(self) -> None:
        """Cancel schedules and reject further provider submissions."""

        self._stopping = True
        for handle in self._timer_handles:
            try:
                self.hass_app.cancel_timer(handle)
            except Exception as exc:
                self.hass_app.log(
                    f"Unable to cancel external provider timer: {exc}",
                    level="WARNING",
                )
        self._timer_handles.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
        while True:
            try:
                self._results.get_nowait()
            except Empty:
                break
