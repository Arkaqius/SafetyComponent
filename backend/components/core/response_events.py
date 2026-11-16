"""Bounded immutable identities admitted independently to fault-response consumers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping
from uuid import uuid4

from components.core.types_common import FaultState

ALLOWED_CONTEXT = frozenset({
    "location", "Location", "area_id", "area_name", "hazard", "source", "source_entity",
    "entity_id", "detector", "detector_key", "gas_identity", "reason", "recommendation",
    "openings", "doors", "failed_check", "observed_value", "threshold", "unit",
    "temperature", "temperature_rate", "forecast", "affected_subjects", "friendly_name",
    "incident_id", "installation_key", "rule_key", "room_key", "phase", "confidence", "profile_version",
    "evidence_kind", "providers", "capability", "source_time", "valid_to", "freshness",
    "freshness_age", "source_reference", "severity", "confirmation", "stations",
    "response_deadline_monotonic", "response_elapsed_seconds", "dispatch_delay_seconds", "dispatch_overrun",
})


@dataclass(frozen=True)
class FaultResponseEvent:
    """Copy identities and allowlisted evidence, never references to domain objects."""

    event_id: str
    runtime_id: str
    incident_id: str
    revision: int
    fault_id: str
    symptom_id: str
    state: FaultState
    level: int
    context_json: str
    detail_omitted: bool = False

    @property
    def context(self) -> dict[str, Any]:
        """Return a fresh copy so a consumer cannot mutate another's evidence."""
        result: dict[str, Any] = json.loads(self.context_json)
        return result

    def to_json(self) -> str:
        """Encode the event within its total 32 KiB infrastructure allocation."""
        return json.dumps({
            "event_id": self.event_id, "runtime_id": self.runtime_id,
            "incident_id": self.incident_id, "revision": self.revision,
            "fault_id": self.fault_id, "symptom_id": self.symptom_id,
            "state": self.state.name, "level": self.level, "context": self.context,
            "detail_omitted": self.detail_omitted,
        }, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    @classmethod
    def create(
        cls, *, runtime_id: str, incident_id: str, revision: int, fault_id: str,
        symptom_id: str, state: FaultState, level: int,
        context: Mapping[str, Any] | None = None,
    ) -> FaultResponseEvent:
        """Omit excess context explicitly while retaining activation and identity."""
        for identity in (runtime_id, incident_id, fault_id, symptom_id):
            if not isinstance(identity, str) or not identity or len(identity) > 128:
                raise ValueError("Invalid response identity")
        if level not in (1, 2, 3, 4) or revision < 1:
            raise ValueError("Invalid response severity/revision")
        safe: dict[str, Any] = {}
        omitted = False
        for key, value in (context or {}).items():
            if key not in ALLOWED_CONTEXT:
                omitted = True
                continue
            try:
                encoded = json.dumps({key: value}, ensure_ascii=False, allow_nan=False)
                if len(encoded.encode("utf-8")) > 4096:
                    omitted = True
                    continue
                candidate = {**safe, key: json.loads(encoded)[key]}
                if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
                    omitted = True
                    continue
                safe = candidate
            except (ValueError, TypeError, RecursionError):
                omitted = True
        event = cls(uuid4().hex, runtime_id, incident_id, revision, fault_id,
                    symptom_id, state, level, json.dumps(safe, ensure_ascii=False), omitted)
        if len(event.to_json().encode("utf-8")) > 32 * 1024:
            raise ValueError("Response envelope exceeds infrastructure bound")
        return event
