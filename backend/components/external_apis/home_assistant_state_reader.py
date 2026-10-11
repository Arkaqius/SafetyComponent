"""Share scheduled HA report reads without blocking safety callbacks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock, Thread
from time import monotonic
from typing import Any

from .home_assistant_state import (
    FAST_REPORT_TIMEOUT_SECONDS,
    HomeAssistantStateProvider,
    REPORT_TIMEOUT_SECONDS,
)

STATE_POLL_SECONDS = 60
TEMPERATURE_POLL_SECONDS = 120
MAINTENANCE_POLL_SECONDS = 3600
SCHEDULE_SECONDS = 5


@dataclass
class ReportGroup:
    """Keep one subscription's schedule and latest completed attempt."""

    entities: set[str]
    interval: int
    timeout_seconds: int
    scheduling_margin_seconds: int
    next_poll: float = 0.0
    completed_at: float | None = None
    valid_until: float = 0.0
    revision: int = 0
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)


class HomeAssistantStateReader:
    """Batch due subscriptions into one bounded background request."""

    def __init__(self, provider: HomeAssistantStateProvider) -> None:
        self.provider = provider
        self._groups: dict[str, ReportGroup] = {}
        self._lock = Lock()
        self._refreshing: set[int] = set()
        self._closed = False
        self._timer: Any = None
        self._app: Any = None

    def register(self, key: str, entities: set[str], interval: int) -> None:
        """Register a fixed group before starting network activity."""
        if interval < 1:
            raise ValueError("Report polling interval must be positive")
        with self._lock:
            if key in self._groups:
                raise ValueError(f"Duplicate HA report group: {key}")
            fast = interval <= SCHEDULE_SECONDS
            self._groups[key] = ReportGroup(
                set(entities),
                interval,
                FAST_REPORT_TIMEOUT_SECONDS if fast else REPORT_TIMEOUT_SECONDS,
                0 if fast else SCHEDULE_SECONDS,
            )

    def start(self, app: Any) -> None:
        """Start reads after application initialization; callbacks never wait."""
        self._app = app
        self._timer = app.run_every(self.tick, "now", SCHEDULE_SECONDS)

    def stop(self) -> None:
        """Prevent late responses and cancel the schedule on shutdown."""
        with self._lock:
            self._closed = True
            for group in self._groups.values():
                group.reports = {}
        if self._timer is not None:
            self._app.cancel_timer(self._timer)

    def tick(self, *_: Any, **__: Any) -> None:
        """Keep fast and ordinary requests independent, with one worker each."""
        now = monotonic()
        batches: dict[int, dict[str, set[str]]] = {}
        with self._lock:
            if self._closed:
                return
            for key, group in self._groups.items():
                # Fast groups run on every five-second scheduler tick. Comparing
                # against the preceding callback's actual start time can skip
                # a whole cycle when the next callback arrives slightly earlier.
                if (
                    (group.interval <= SCHEDULE_SECONDS or now >= group.next_poll)
                    and group.timeout_seconds not in self._refreshing
                ):
                    batches.setdefault(group.timeout_seconds, {})[key] = set(group.entities)
                    group.next_poll = now + group.interval
            self._refreshing.update(batches)
        for timeout_seconds, due in batches.items():
            try:
                Thread(
                    target=self._refresh,
                    args=(due, now, timeout_seconds),
                    name=f"ha-source-reports-{timeout_seconds}",
                    daemon=True,
                ).start()
            except RuntimeError:
                self._complete(due, {}, now, timeout_seconds)

    def reports(self, key: str) -> dict[str, dict[str, Any]]:
        """Return source evidence, never a new timestamp for a cached read."""
        with self._lock:
            group = self._groups[key]
            # Expiry is anchored to acquisition start, not delivery time.
            if (
                self._closed
                or group.completed_at is None
                or monotonic() > group.valid_until
            ):
                return {}
            return deepcopy(group.reports)

    def revision(self, key: str) -> int:
        """Identify a completed attempt, including a failed attempt."""
        with self._lock:
            group = self._groups[key]
            if self._closed or (
                group.completed_at is not None and monotonic() > group.valid_until
            ):
                return -group.revision
            return group.revision

    def report(self, key: str, entity: str) -> dict[str, Any] | None:
        """Copy one report without copying the entire monitored inventory."""
        with self._lock:
            group = self._groups[key]
            if (
                self._closed
                or group.completed_at is None
                or monotonic() > group.valid_until
            ):
                return None
            return deepcopy(group.reports.get(entity))

    def _refresh(
        self, due: dict[str, set[str]], started_at: float, timeout_seconds: int
    ) -> None:
        reports: dict[str, dict[str, Any]] = {}
        try:
            reports = self.provider.poll(
                set().union(*due.values()), timeout_seconds=timeout_seconds
            )
        except Exception:
            # A provider exception is missing evidence, not a healthy cache hit.
            reports = {}
        finally:
            if monotonic() - started_at > timeout_seconds:
                reports = {}
            self._complete(due, reports, started_at, timeout_seconds)

    def _complete(
        self,
        due: dict[str, set[str]],
        reports: dict[str, dict[str, Any]],
        started_at: float,
        timeout_seconds: int,
    ) -> None:
        """Invalidate failed/late reads without extending old evidence's life."""
        with self._lock:
            if not self._closed:
                for key, entities in due.items():
                    group = self._groups[key]
                    group.reports = {
                        entity: reports[entity]
                        for entity in entities
                        if entity in reports
                    }
                    group.completed_at = monotonic()
                    group.valid_until = (
                        started_at + group.interval + group.timeout_seconds
                        + group.scheduling_margin_seconds
                    )
                    group.revision += 1
            self._refreshing.discard(timeout_seconds)
