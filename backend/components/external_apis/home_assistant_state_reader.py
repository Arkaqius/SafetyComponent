"""Share scheduled HA report reads without blocking safety callbacks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock, Thread
from time import monotonic
from typing import Any

from .home_assistant_state import HomeAssistantStateProvider, REPORT_TIMEOUT_SECONDS

STATE_POLL_SECONDS = 60
MAINTENANCE_POLL_SECONDS = 3600


@dataclass
class ReportGroup:
    """Keep one subscription's schedule and latest completed attempt."""

    entities: set[str]
    interval: int
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
        self._refreshing = False
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
            self._groups[key] = ReportGroup(set(entities), interval)

    def start(self, app: Any) -> None:
        """Start reads after application initialization; callbacks never wait."""
        self._app = app
        self._timer = app.run_every(self.tick, "now", 5)

    def stop(self) -> None:
        """Prevent late responses and cancel the schedule on shutdown."""
        with self._lock:
            self._closed = True
            for group in self._groups.values():
                group.reports = {}
        if self._timer is not None:
            self._app.cancel_timer(self._timer)

    def tick(self, *_: Any, **__: Any) -> None:
        """Submit due groups once; an in-flight request cannot overlap."""
        now = monotonic()
        with self._lock:
            if self._closed or self._refreshing:
                return
            due = {
                key: set(group.entities)
                for key, group in self._groups.items()
                if now >= group.next_poll
            }
            if not due:
                return
            for key in due:
                self._groups[key].next_poll = now + self._groups[key].interval
            self._refreshing = True
        try:
            Thread(
                target=self._refresh,
                args=(due, now),
                name="ha-source-reports",
                daemon=True,
            ).start()
        except RuntimeError:
            self._complete(due, {}, now)

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

    def _refresh(self, due: dict[str, set[str]], started_at: float) -> None:
        reports: dict[str, dict[str, Any]] = {}
        try:
            reports = self.provider.poll(set().union(*due.values()))
        except Exception:
            # A provider exception is missing evidence, not a healthy cache hit.
            reports = {}
        finally:
            if monotonic() - started_at > REPORT_TIMEOUT_SECONDS:
                reports = {}
            self._complete(due, reports, started_at)

    def _complete(
        self,
        due: dict[str, set[str]],
        reports: dict[str, dict[str, Any]],
        started_at: float,
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
                        started_at + group.interval + REPORT_TIMEOUT_SECONDS
                    )
                    group.revision += 1
            self._refreshing = False
