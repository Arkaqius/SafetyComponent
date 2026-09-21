"""Concurrent provider polling with serialized EventBus dispatch."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any, Mapping

from components.core.event_bus import EventBus

from .api_component import ExternalApiComponent
from .models import ApiResult


class ExternalApiRuntime:
    """Run providers independently and return results on AppDaemon's callback thread."""

    def __init__(
        self,
        hass_app: Any,
        event_bus: EventBus,
        components: Mapping[str, ExternalApiComponent],
        *,
        max_queue_size: int = 64,
    ) -> None:
        self.hass_app = hass_app
        self.event_bus = event_bus
        self.components = dict(components)
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, len(self.components)),
            thread_name_prefix="external-api",
        )
        self._results: Queue[ApiResult] = Queue(maxsize=max_queue_size)
        self._in_flight: set[str] = set()
        self._lock = Lock()
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
        future.add_done_callback(
            lambda completed, provider_name=provider: self._poll_completed(
                provider_name, completed
            )
        )
        return True

    def _scheduled_poll(self, **kwargs: Any) -> None:
        self.request_poll(str(kwargs["provider"]))

    def _poll_completed(self, provider: str, future: Future[ApiResult]) -> None:
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
        try:
            self._results.put_nowait(result)
        except Full:
            try:
                self._results.get_nowait()
            except Empty:
                pass
            self._results.put_nowait(result)
            self.hass_app.log(
                "External provider result queue overflowed; oldest result discarded",
                level="WARNING",
            )

    def drain_results(self, **_: Any) -> None:
        """Publish queued results synchronously through the EventBus."""

        while True:
            try:
                result = self._results.get_nowait()
            except Empty:
                return
            self.event_bus.publish("external_api_result", result=result)

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
