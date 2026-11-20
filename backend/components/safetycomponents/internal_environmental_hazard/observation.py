"""Receiver provenance and reviewed authority for indoor alarm recovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any
from uuid import uuid4


class Provenance(str, Enum):
    """Describe how input was obtained without inventing producer evidence."""

    LIVE_EVENT = "live_event"
    STARTUP_SNAPSHOT = "startup_snapshot"
    READBACK = "readback"
    RESTORED_CHECKPOINT = "restored_checkpoint"


class ObservationState(str, Enum):
    """Keep alarm, recovery and explicitly ineligible source states distinct."""

    ALARM = "alarm"
    CLEAR = "clear"
    TEST = "test"
    HUSH = "hush"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


def aware_utc(value: Any) -> datetime | None:
    """Accept only actual timezone-aware source timestamps; never supply a default."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass(frozen=True)
class DetectorBinding:
    """Immutable equipment/source contract, excluding mutable display names."""

    detector_key: str
    entity_id: str
    hazard: str
    profile_id: str
    profile_version: str
    fingerprint: str
    alarm_states: frozenset[str]
    clear_states: frozenset[str]
    test_states: frozenset[str]
    hush_states: frozenset[str]
    unavailable_states: frozenset[str]
    clear_seconds: int
    reviewed_clear: bool

    @classmethod
    def from_config(cls, key: str, config: Mapping[str, Any], profile: Mapping[str, Any]) -> DetectorBinding:
        """Fingerprint technical binding and the exact interpretation contract."""
        contract = {
            "detector_key": key, "entity_id": config["entity_id"], "hazard": config["hazard"],
            "profile_id": config["profile"], "profile": dict(profile), "channel": "state",
        }
        fingerprint = hashlib.sha256(json.dumps(contract, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
        def states(name: str) -> frozenset[str]:
            return frozenset(str(value).strip().lower() for value in profile.get(name, ()))
        return cls(key, str(config["entity_id"]), str(config["hazard"]), str(config["profile"]),
                   str(profile["version"]), fingerprint, states("alarm_states"), states("clear_states"),
                   states("test_states"), states("hush_states"), states("unavailable_states"),
                   int(profile["clear_duration_seconds"]),
                   profile.get("authoritative_clear") is True and profile.get("clear_event_contract") == "ha_state_changed_v1")

    def classify(self, state: Any) -> ObservationState:
        """Normalize only meanings explicitly admitted by this profile."""
        normalized = str(state or "").strip().lower()
        for values, kind in (
            (self.alarm_states, ObservationState.ALARM), (self.clear_states, ObservationState.CLEAR),
            (self.test_states, ObservationState.TEST), (self.hush_states, ObservationState.HUSH),
            (self.unavailable_states, ObservationState.UNAVAILABLE),
        ):
            if normalized in values:
                return kind
        return ObservationState.UNKNOWN


@dataclass(frozen=True)
class IndoorObservation:
    """Detached HA evidence; receiver identity is never a producer epoch/order."""

    binding: DetectorBinding
    state: ObservationState
    raw_state: str
    provenance: Provenance
    receiver_session: str
    received_monotonic: float
    ha_changed_at: datetime | None = None
    ha_updated_at: datetime | None = None
    ha_old_state: str | None = None
    ha_old_changed_at: datetime | None = None
    ha_event_at: datetime | None = None
    ha_context_id: str | None = None
    local_ha_event: bool = False
    producer_epoch: str | None = None
    producer_sequence: int | None = None
    producer_time: datetime | None = None
    receiver_utc: datetime | None = None

    @classmethod
    def snapshot(
        cls, binding: DetectorBinding, raw: Any, *, provenance: Provenance,
        session: str, received: float, received_at: datetime | None = None,
    ) -> IndoorObservation:
        """Retain source metadata when available; a snapshot cannot create an edge."""
        if not math.isfinite(received) or received < 0:
            raise ValueError("Invalid receiver receipt time")
        record = raw if isinstance(raw, Mapping) else {"state": raw}
        state = record.get("state")
        kind = binding.classify(state)
        if record.get("entity_id", binding.entity_id) != binding.entity_id:
            kind = ObservationState.UNKNOWN
        return cls(binding, kind, str(state or ""), provenance, session, received,
                   aware_utc(record.get("last_changed")), aware_utc(record.get("last_updated")),
                   receiver_utc=aware_utc(received_at) if received_at is not None else datetime.now(timezone.utc))

    @classmethod
    def event(
        cls, binding: DetectorBinding, data: Mapping[str, Any], *, session: str, received: float,
        received_at: datetime | None = None,
    ) -> IndoorObservation:
        """Read the actual packaged HASS state_changed callback envelope."""
        current = cls.snapshot(binding, data.get("new_state"), provenance=Provenance.LIVE_EVENT,
                               session=session, received=received, received_at=received_at)
        old = data.get("old_state")
        old = old if isinstance(old, Mapping) else {}
        metadata = data.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        context = metadata.get("context")
        context = context if isinstance(context, Mapping) else {}
        identity = context.get("id")
        identity = identity if isinstance(identity, str) and 0 < len(identity) <= 128 else None
        return cls(
            binding, current.state if data.get("entity_id") == binding.entity_id else ObservationState.UNKNOWN,
            current.raw_state, Provenance.LIVE_EVENT, session, received,
            current.ha_changed_at, current.ha_updated_at,
            str(old["state"]) if "state" in old else None, aware_utc(old.get("last_changed")),
            aware_utc(metadata.get("time_fired")), identity, metadata.get("origin") == "LOCAL",
            receiver_utc=current.receiver_utc,
        )

    @property
    def source_time_valid(self) -> bool:
        """Reject future source metadata against actual receiver wall-clock evidence."""
        return bool(self.receiver_utc is not None and self.ha_changed_at is not None
            and self.ha_updated_at is not None and self.ha_changed_at <= self.ha_updated_at <= self.receiver_utc
            and (self.ha_event_at is None or self.ha_updated_at <= self.ha_event_at <= self.receiver_utc))

    @property
    def reviewed_edge(self) -> bool:
        """Require real HA transition metadata with strict, unambiguous source order."""
        return bool(
            self.provenance == Provenance.LIVE_EVENT and self.binding.reviewed_clear
            and self.source_time_valid
            and self.local_ha_event and self.ha_context_id
            and self.ha_changed_at is not None and self.ha_old_changed_at is not None
            and self.ha_updated_at is not None and self.ha_event_at is not None
            and self.ha_old_changed_at < self.ha_changed_at <= self.ha_updated_at <= self.ha_event_at
            and self.ha_old_state != self.raw_state
        )


@dataclass(frozen=True)
class ClearCandidate:
    """One full newly observed interval, bound to incident, source and session."""

    token: str
    incident_id: str
    binding_fingerprint: str
    receiver_session: str
    started_monotonic: float
    deadline_monotonic: float
    ha_clear_changed_at: datetime
    ha_event_at: datetime
    ha_context_id: str


class ClearAuthority:
    """Own source continuity only; durable state and physical outputs live elsewhere."""

    def __init__(self, binding: DetectorBinding, session: str) -> None:
        self.binding = binding
        self.session = session
        self.connected = True
        self.last_alarm: IndoorObservation | None = None
        self.last_source_state = ObservationState.UNKNOWN
        self.last_event_at: datetime | None = None
        self.candidate: ClearCandidate | None = None
        self.reason = "awaiting_authoritative_transition"

    def new_session(self, session: str, *, connected: bool = True) -> None:
        """Invalidate all source authority without modifying retained alarm state."""
        self.session, self.connected = session, connected
        self.last_alarm = None
        self.last_source_state = ObservationState.UNKNOWN
        self.last_event_at = None
        self.candidate = None
        self.reason = "source_session_changed"

    def observe(self, observation: IndoorObservation, incident_id: str) -> ClearCandidate | None:
        """Admit alarms conservatively and accept only a reviewed new clear edge."""
        if (observation.binding.fingerprint != self.binding.fingerprint
                or observation.receiver_session != self.session or not self.connected):
            self.candidate = None
            self.reason = "obsolete_source_identity"
            return None
        if observation.state == ObservationState.ALARM:
            self.candidate = None
            if observation.provenance != Provenance.RESTORED_CHECKPOINT:
                previous = self.last_alarm
                if (observation.ha_changed_at is None or previous is not None
                        and previous.ha_changed_at is not None and observation.ha_changed_at < previous.ha_changed_at
                        or observation.ha_event_at is not None and self.last_event_at is not None
                        and observation.ha_event_at < self.last_event_at):
                    self.last_source_state = ObservationState.UNKNOWN
                    self.reason = "positive_source_order_unverified"
                    return None
                self.last_alarm = observation
                self.last_source_state = ObservationState.ALARM
                if observation.ha_event_at is not None:
                    self.last_event_at = observation.ha_event_at
            self.reason = "alarm_active"
            return None
        if observation.state != ObservationState.CLEAR:
            self.candidate = None
            self.last_source_state = observation.state
            self.reason = "source_continuity_unverified"
            return None
        if observation.provenance != Provenance.LIVE_EVENT:
            if self.candidate is not None and (not observation.source_time_valid or observation.ha_changed_at != self.candidate.ha_clear_changed_at):
                self.candidate = None
                self.last_source_state = ObservationState.UNKNOWN
                self.reason = "clear_readback_inconsistent"
                return None
            self.reason = "clear_readback_only" if self.candidate is None else "clear_qualifying"
            return self.candidate
        if (observation.ha_event_at is None or self.last_event_at is not None
                and observation.ha_event_at < self.last_event_at):
            self.candidate = None
            self.last_source_state = ObservationState.UNKNOWN
            self.reason = "source_order_unverified"
            return None
        self.last_event_at = observation.ha_event_at
        candidate = self.candidate
        if candidate is not None and observation.ha_changed_at == candidate.ha_clear_changed_at:
            metadata_valid = (
                observation.local_ha_event and observation.ha_context_id and observation.ha_updated_at is not None
                and observation.source_time_valid
                and observation.ha_changed_at is not None and observation.ha_changed_at <= observation.ha_updated_at <= observation.ha_event_at
            )
            same_event = observation.ha_context_id == candidate.ha_context_id and observation.ha_event_at == candidate.ha_event_at
            same_clear = (observation.binding.classify(observation.ha_old_state) == ObservationState.CLEAR
                          and observation.ha_old_changed_at == candidate.ha_clear_changed_at)
            if metadata_valid and (same_event or same_clear):
                return candidate
        alarm = self.last_alarm
        if not (
            observation.reviewed_edge and alarm is not None and alarm.ha_changed_at is not None
            and self.last_source_state == ObservationState.ALARM
            and observation.binding.classify(observation.ha_old_state) == ObservationState.ALARM
            and observation.ha_old_changed_at == alarm.ha_changed_at
            and observation.ha_changed_at is not None and observation.ha_changed_at > alarm.ha_changed_at
            and observation.received_monotonic >= alarm.received_monotonic
        ):
            self.candidate = None
            self.last_source_state = ObservationState.CLEAR
            self.reason = "alarm_to_clear_transition_unverified"
            return None
        self.candidate = ClearCandidate(
            uuid4().hex, incident_id, self.binding.fingerprint, self.session,
            observation.received_monotonic, observation.received_monotonic + self.binding.clear_seconds,
            observation.ha_changed_at, observation.ha_event_at, str(observation.ha_context_id),
        )
        self.last_source_state = ObservationState.CLEAR
        self.reason = "clear_qualifying"
        return self.candidate

    def eligible(self, candidate: ClearCandidate, incident_id: str, now: float, readback: IndoorObservation) -> bool:
        """Check exact current identity and readback after a complete monotonic interval."""
        return bool(
            self.connected and self.candidate is candidate and candidate.incident_id == incident_id
            and candidate.receiver_session == self.session and candidate.binding_fingerprint == self.binding.fingerprint
            and math.isfinite(now) and now >= candidate.deadline_monotonic
            and readback.receiver_session == self.session and readback.binding.fingerprint == self.binding.fingerprint
            and readback.state == ObservationState.CLEAR and readback.ha_changed_at == candidate.ha_clear_changed_at
            and readback.source_time_valid
            and self.last_source_state == ObservationState.CLEAR
        )
