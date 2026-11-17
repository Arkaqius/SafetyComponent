"""Qualify diagnostic reporting after restart without pausing hazard detection."""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Callable

from components.core.event_bus import EventBus
from components.core.types_common import FaultState


class StartupGrace:
    """Keep the latest diagnostic evidence while sources settle after startup."""

    def __init__(
        self,
        event_bus: EventBus,
        diagnostic_symptoms: set[str],
        seconds: int,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.event_bus = event_bus
        self.diagnostic_symptoms = frozenset(diagnostic_symptoms)
        self.seconds = seconds
        self._clock = clock
        self._deadline = clock() + seconds
        self._started_at = datetime.now(timezone.utc)
        self._complete = seconds == 0
        self._pending: dict[str, tuple[str, dict[str, Any]]] = {}
        event_bus.subscribe("symptom", self.observe)
        event_bus.subscribe("evaluation_unavailable", self.mark_unavailable)
        event_bus.subscribe("evaluation_pending", self.mark_pending)

    def mark_pending(self, *, symptom_id: str, violation: bool, **_: Any) -> None:
        """Keep diagnostic qualification behind the same startup boundary."""
        if symptom_id in self.diagnostic_symptoms and not self._complete:
            self._defer(symptom_id, "qualified_evaluation_pending", {
                "symptom_id": symptom_id, "violation": violation,
            })
            return
        self.event_bus.publish(
            "qualified_evaluation_pending", symptom_id=symptom_id, violation=violation
        )

    def defers(self, symptom_id: str) -> bool:
        """Report whether operator-facing evaluation is still held for a diagnostic."""
        return not self._complete and symptom_id in self.diagnostic_symptoms

    def observe(self, *, symptom_id: str, state: FaultState, **context: Any) -> None:
        """Defer diagnostic reporting; real hazards remain immediate."""
        if symptom_id not in self.diagnostic_symptoms or self._complete:
            self.event_bus.publish(
                "qualified_symptom", symptom_id=symptom_id, state=state, **context
            )
            return
        if state not in (FaultState.SET, FaultState.CLEARED):
            return
        self._defer(symptom_id, "qualified_symptom", {
            "symptom_id": symptom_id, "state": state, **context,
        })

    def mark_unavailable(self, *, symptom_id: str, **_: Any) -> None:
        """Discard superseded evidence instead of replaying it at expiry."""
        if symptom_id in self.diagnostic_symptoms and not self._complete:
            self._defer(symptom_id, "qualified_evaluation_unavailable", {"symptom_id": symptom_id})
            return
        self.event_bus.publish(
            "qualified_evaluation_unavailable", symptom_id=symptom_id
        )

    def _defer(self, symptom_id: str, event: str, payload: dict[str, Any]) -> None:
        """Keep only the latest result without publishing a startup failure."""
        self._pending[symptom_id] = (event, deepcopy(payload))
        if self._clock() >= self._deadline:
            self.finish()

    def finish(self) -> bool:
        """Release each latest valid observation once the monotonic deadline passes."""
        if self._complete or self._clock() < self._deadline:
            return False
        pending, self._pending = self._pending, {}
        self._complete = True
        for event, observation in pending.values():
            self.event_bus.publish(event, **observation)
        for symptom_id in sorted(self.diagnostic_symptoms.difference(pending)):
            self.event_bus.publish("qualified_evaluation_unavailable", symptom_id=symptom_id)
        return True

    def snapshot(self) -> dict[str, Any]:
        """Publish server-confirmed phase and countdown on the existing progress entity."""
        return {
            "phase": "complete" if self._complete else "settling",
            "duration_seconds": self.seconds,
            "remaining_seconds": 0
            if self._complete
            else max(0, math.ceil(self._deadline - self._clock())),
            "started_at": self._started_at.isoformat(),
            "ends_at": (self._started_at + timedelta(seconds=self.seconds)).isoformat(),
            "reported_at": datetime.now(timezone.utc).isoformat(),
            "deferred_symptom_count": len(self.diagnostic_symptoms),
        }
