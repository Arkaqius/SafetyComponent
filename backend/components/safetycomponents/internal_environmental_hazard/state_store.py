"""Atomic bounded persistence for internal environmental detector state."""

from __future__ import annotations

import json
import builtins
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, cast
from uuid import uuid4
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from components.core.snapshot_writer import SnapshotWriter, process_snapshot_writer
from .observation import ClearCandidate, DetectorBinding, aware_utc

MAX_RECORDS = 4096
MAX_BYTES = 1_048_576
INDOOR_FAULTS = {
    "smoke": "InternalSmokeDetected", "flammable_gas": "InternalFlammableGasDetected",
    "carbon_monoxide": "InternalCarbonMonoxideDetected", "water_leak": "WaterLeakDetected",
}


def current_launch_id() -> str:
    """Return a process witness identity, never persisted as proof of a later launch."""
    return str(builtins.__dict__.setdefault("_safety_indoor_launch_v2", uuid4().hex))


def _storage_identity(store: InternalEnvironmentStateStore) -> str:
    database = getattr(store, "database", None)
    if database is not None:
        return "sqlite:" + str(database.path.resolve())
    path = getattr(store, "path", None)
    if isinstance(path, Path):
        return "json:" + str(path.resolve())
    identity = getattr(store, "witness_identity", None)
    return str(identity) if isinstance(identity, str) else "unverified_storage"


def _bounded_json(value: Any, *, maximum: int, depth: int = 0) -> None:
    if depth > 4:
        raise ValueError("Indoor context exceeds depth 4")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("Invalid indoor context key")
            _bounded_json(child, maximum=maximum, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _bounded_json(child, maximum=maximum, depth=depth + 1)
    elif isinstance(value, str) and len(value) > 256:
        raise ValueError("Indoor display text exceeds 256 characters")
    if depth == 0 and len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > maximum:
        raise ValueError("Indoor context exceeds byte bound")


class IndoorClearProof(BaseModel):
    """Historical reviewed clear identity; no reboot restores its elapsed timing."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)
    candidate_token: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(min_length=1, max_length=128)
    binding_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    receiver_session: str = Field(min_length=1, max_length=128)
    ha_context_id: str = Field(min_length=1, max_length=128)
    ha_changed_at: str
    ha_event_at: str
    generation: int = Field(ge=1)
    source_contract: Literal["ha_state_changed_v1"] = "ha_state_changed_v1"

    @model_validator(mode="after")
    def _order(self) -> IndoorClearProof:
        changed, event = aware_utc(self.ha_changed_at), aware_utc(self.ha_event_at)
        if changed is None or event is None or changed > event:
            raise ValueError("Invalid historical clear source order")
        return self


class IndoorRecord(BaseModel):
    """Persist actual known identity or explicitly missing legacy identity."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["known", "legacy_unattributed"]
    record_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_]+$")
    detector_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9]+$")
    symptom_id: str | None = Field(default=None, min_length=1, max_length=128)
    fault_id: str | None = Field(default=None, min_length=1, max_length=128)
    incident_id: str | None = Field(default=None, min_length=1, max_length=128)
    hazard: Literal["smoke", "flammable_gas", "carbon_monoxide", "water_leak"] | None = None
    entity_id: str | None = Field(default=None, min_length=1, max_length=255)
    profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    profile_version: str | None = Field(default=None, min_length=1, max_length=128)
    binding_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    activated_at: str | None = None
    historical_clear_at: str | None = None
    alarm_active: bool
    health_active: bool = False
    gas_switching_inhibited: bool
    context: dict[str, Any] = Field(default_factory=dict)
    clear_proof: IndoorClearProof | None = None

    @field_validator("activated_at", "historical_clear_at")
    @classmethod
    def _timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = aware_utc(value)
            if parsed is None or parsed.utcoffset() != datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset():
                raise ValueError("Indoor timestamp must be UTC-aware")
        return value

    @field_validator("context")
    @classmethod
    def _context(cls, value: dict[str, Any]) -> dict[str, Any]:
        _bounded_json(value, maximum=4096)
        return json.loads(json.dumps(value, allow_nan=False))

    @model_validator(mode="after")
    def _identity(self) -> IndoorRecord:
        identity = (self.symptom_id, self.fault_id, self.incident_id, self.hazard, self.entity_id,
                    self.profile_id, self.profile_version, self.binding_fingerprint, self.activated_at)
        if self.kind == "legacy_unattributed":
            if any(value is not None for value in identity):
                raise ValueError("Legacy identity must not be fabricated")
        elif any(value is None for value in identity):
            raise ValueError("Known indoor record requires complete original identity")
        elif self.fault_id != INDOOR_FAULTS.get(str(self.hazard)) or self.symptom_id != f"InternalEnv_{self.hazard}_{self.detector_key}":
            raise ValueError("Indoor fault/hazard/symptom identity disagrees with trusted catalog")
        if self.kind == "known" and self.gas_switching_inhibited != (self.hazard == "flammable_gas"):
            raise ValueError("Original gas activation must retain its independent latch")
        if self.clear_proof is not None and (self.kind != "known" or self.clear_proof.incident_id != self.incident_id
                or self.clear_proof.binding_fingerprint != self.binding_fingerprint):
            raise ValueError("Clear proof does not belong to original incident/binding")
        return self


class IndoorCheckpoint(BaseModel):
    """Strict whole-owner snapshot; current configuration does not own retention."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    version: Literal[2] = 2
    owner_session: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0)
    clean: bool
    history_unknown: bool
    gas_history_unknown: bool
    commissioning_id: str | None = Field(default=None, min_length=1, max_length=128)
    commissioned_at: str | None = None
    records: list[IndoorRecord] = Field(max_length=MAX_RECORDS)

    @field_validator("version", mode="before")
    @classmethod
    def _strict_version(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Indoor version must be an integer")
        return value

    @model_validator(mode="after")
    def _bounds(self) -> IndoorCheckpoint:
        ids = [record.record_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate indoor record identity")
        incidents = [record.incident_id for record in self.records if record.kind == "known"]
        bindings = [record.binding_fingerprint for record in self.records if record.kind == "known"]
        if len(set(incidents)) != len(incidents) or len(set(bindings)) != len(bindings):
            raise ValueError("Duplicate indoor incident or binding")
        if (self.commissioning_id is None) != (self.commissioned_at is None):
            raise ValueError("Incomplete commissioning evidence")
        if self.commissioned_at is not None and aware_utc(self.commissioned_at) is None:
            raise ValueError("Commissioning time must be timezone-aware")
        if not self.history_unknown and self.commissioning_id is None:
            raise ValueError("Known history requires explicit commissioning evidence")
        if len(json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BYTES:
            raise ValueError("Indoor checkpoint exceeds 1 MiB")
        return self


def commissioned_checkpoint(receipt_id: str, reviewed_at: datetime) -> dict[str, Any]:
    """Build offline reviewed virgin-installation evidence, never infer it from absence.

    Callers must have reviewed installation history; this is no runtime gas reset.
    It must never replace existing owner/journal evidence.
    """
    if reviewed_at.tzinfo is None:
        raise ValueError("Review time must be timezone-aware")
    return IndoorCheckpoint(owner_session="commissioned", generation=0, clean=True,
        history_unknown=False, gas_history_unknown=False, commissioning_id=receipt_id,
        commissioned_at=reviewed_at.astimezone(timezone.utc).isoformat(), records=[]).model_dump(mode="json")


def decode_checkpoint(raw: Mapping[str, Any]) -> IndoorCheckpoint:
    """Validate before use; upgrade legacy evidence without inventing lost identity."""
    if len(json.dumps(dict(raw), ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Indoor checkpoint exceeds 1 MiB")
    if isinstance(raw.get("version"), int) and not isinstance(raw.get("version"), bool) and raw["version"] == 1:
        detectors = raw.get("detectors")
        if not isinstance(detectors, dict) or len(detectors) > MAX_RECORDS:
            raise ValueError("Invalid legacy indoor records")
        records = []
        for key, item in detectors.items():
            if not isinstance(item, dict):
                raise ValueError("Invalid legacy indoor record")
            for flag in ("alarm_active", "health_active", "gas_switching_inhibited"):
                if not isinstance(item.get(flag, False), bool):
                    raise ValueError("Legacy indoor flags must be Boolean")
            if item.get("alarm_active") or item.get("gas_switching_inhibited") or item.get("health_active"):
                records.append(IndoorRecord(kind="legacy_unattributed", record_id="legacy_" + str(key),
                    detector_key=key, alarm_active=item.get("alarm_active", False),
                    health_active=item.get("health_active", False), gas_switching_inhibited=item.get("gas_switching_inhibited", False),
                    historical_clear_at=item.get("last_authoritative_clear_at")))
        return IndoorCheckpoint(owner_session="legacy_upgrade", generation=0, clean=False,
            history_unknown=True, gas_history_unknown=True, records=records)
    return IndoorCheckpoint.model_validate(dict(raw))


class IndoorStateOwner:
    """Retain danger independently of monitor presence and acknowledge CLEAR on owner drain."""

    def __init__(self, store: InternalEnvironmentStateStore, *, writer: SnapshotWriter | None = None,
                 session: str | None = None, launch_receipt: str | None = None) -> None:
        self.store = store
        self.writer = writer or process_snapshot_writer("internal_environment_state")
        self.session = session or uuid4().hex
        storage_identity = _storage_identity(store)
        prior_witness = builtins.__dict__.get("_safety_indoor_owner_witness_v2")
        # A single bounded process slot records every attempted owner session,
        # including one whose marker/storage never succeeds. It contains no
        # mutable component or inferred physical evidence.
        builtins.__dict__["_safety_indoor_owner_witness_v2"] = (storage_identity, self.session)
        self.writer.claim(self.session)
        # Read after the retired writer whenever it can finish within startup's
        # bound. If it cannot, this owner must never overwrite its eventual
        # snapshot with an earlier read. Positive admission remains in memory;
        # persistence/recovery stay unavailable until an orderly owner reload.
        self._prior_write_pending = self.writer.busy and not self.writer.wait_for_progress(5)
        self.records: dict[str, IndoorRecord] = {}
        self.history_unknown = self.gas_history_unknown = True
        self.commissioning_id: str | None = None
        self.commissioned_at: str | None = None
        self.persistence_error: str | None = None
        self.revision = self.durable_revision = 0
        self.marker_revision: int | None = None
        self.marker_durable = False
        self.stopped = False
        self.clean = False
        self._pending_clears: dict[str, tuple[str, ClearCandidate, Callable[[], bool]]] = {}
        try:
            raw = store.load()
            if raw:
                checkpoint = decode_checkpoint(raw)
                self.records = {item.record_id: item for item in checkpoint.records}
                self.revision = checkpoint.generation
                self.commissioning_id, self.commissioned_at = checkpoint.commissioning_id, checkpoint.commissioned_at
                continuity = prior_witness == (storage_identity, checkpoint.owner_session)
                reviewed_virgin = (launch_receipt == current_launch_id() and checkpoint.owner_session == "commissioned"
                    and not checkpoint.records and checkpoint.commissioning_id is not None
                    and not (isinstance(prior_witness, tuple) and prior_witness[0] == storage_identity))
                self.history_unknown = checkpoint.history_unknown or not checkpoint.clean or not (continuity or reviewed_virgin)
                self.gas_history_unknown = checkpoint.gas_history_unknown or not checkpoint.clean or not (continuity or reviewed_virgin)
            else:
                self.persistence_error = "history_missing"
        except Exception as exc:
            self.persistence_error = "load_" + type(exc).__name__
        if self._prior_write_pending:
            self.history_unknown = self.gas_history_unknown = True
            self.persistence_error = "prior_owner_write_pending"

    @property
    def gas_inhibited(self) -> bool:
        """Independent latch and lost-history restriction survive alarm recovery."""
        return self.gas_history_unknown or any(item.gas_switching_inhibited for item in self.records.values())

    @property
    def recovery_ready(self) -> bool:
        """Only a durable current-session marker can admit clear authorization."""
        return self.marker_durable and not self.stopped and self.persistence_error in {None, "history_unverified"}

    def checkpoint(self, *, staged: bool = False, clean: bool = False) -> IndoorCheckpoint:
        """Build a complete bounded snapshot; never evict active records."""
        records = []
        for item in self.records.values():
            if staged and item.record_id in self._pending_clears:
                candidate = self._pending_clears[item.record_id][1]
                proof = IndoorClearProof(candidate_token=candidate.token, incident_id=candidate.incident_id,
                    binding_fingerprint=candidate.binding_fingerprint, receiver_session=candidate.receiver_session,
                    ha_context_id=candidate.ha_context_id, ha_changed_at=candidate.ha_clear_changed_at.isoformat(),
                    ha_event_at=candidate.ha_event_at.isoformat(), generation=self.revision)
                item = item.model_copy(update={"alarm_active": False, "clear_proof": proof,
                    "historical_clear_at": candidate.ha_clear_changed_at.isoformat()})
            records.append(item)
        return IndoorCheckpoint(owner_session=self.session, generation=self.revision, clean=clean,
            history_unknown=self.history_unknown, gas_history_unknown=self.gas_history_unknown,
            commissioning_id=self.commissioning_id, commissioned_at=self.commissioned_at, records=records)

    def begin(self) -> None:
        """Queue dirty ownership before source registration; admission is not acknowledgement."""
        if self.marker_revision is None:
            self.marker_revision = self.revision + 1
            self._enqueue()

    def persist(self) -> bool:
        """Request a new complete snapshot without synchronous storage on alarm ingress."""
        return self._enqueue()

    def establish_session(self, *, timeout: float = 5) -> bool:
        """Acknowledge dirty ownership before registering observation ingress.

        One bounded startup wait uses the same process writer as every snapshot,
        including any older-generation write. Failure retains immediate positive
        admission but denies recovery and unapproved switching.
        """
        self.begin()
        if self._prior_write_pending:
            return False
        deadline = monotonic() + timeout
        while True:
            self.drain()
            if self.marker_durable:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0 or not self.writer.wait_for_progress(remaining):
                self.history_unknown = self.gas_history_unknown = True
                self.persistence_error = "dirty_marker_unacknowledged"
                self._enqueue()
                return False

    def _enqueue(self, *, clean: bool = False) -> bool:
        self.revision += 1
        if self._prior_write_pending:
            self.persistence_error = "prior_owner_write_pending"
            return False
        try:
            payload = self.checkpoint(staged=True, clean=clean).model_dump(mode="json")
            accepted = self.writer.enqueue(self.session, self.revision, payload, self.store.save)
        except (ValueError, TypeError, RecursionError):
            accepted = False
        if not accepted:
            self.persistence_error = "checkpoint_admission_failed"
        return accepted

    def current_record(self, binding: DetectorBinding) -> IndoorRecord | None:
        """Match only complete original technical identity, never display name/key alone."""
        return next((item for item in self.records.values() if item.kind == "known"
                     and item.binding_fingerprint == binding.fingerprint
                     and item.detector_key == binding.detector_key and item.entity_id == binding.entity_id
                     and item.hazard == binding.hazard and item.profile_id == binding.profile_id
                     and item.profile_version == binding.profile_version), None)

    def projection(self, bindings: Mapping[str, str], *, monitoring_enabled: bool,
                   localize: Callable[[str], str] | None = None) -> dict[str, Any]:
        """Bound presentation only; danger and restriction totals include every record."""
        details: list[dict[str, Any]] = []
        labels = {"current": "Current source", "retained_unverified": "Retained alarm; current source unverified",
                  "orphan": "Retained alarm; original source absent", "history_unknown": "Safety history unverified",
                  "gas_unknown": "Gas restriction history unknown; switching inhibited"}
        def label(key: str) -> str:
            return localize("indoor.retention." + key) if localize is not None else labels[key]
        for record in self.records.values():
            exact = bindings.get(record.detector_key) == record.binding_fingerprint and record.kind == "known"
            status = "current" if exact and monitoring_enabled else "retained_unverified" if exact else "orphan"
            detail = dict(record_id=record.record_id, detector_key=record.detector_key,
                symptom_id=record.symptom_id, fault_id=record.fault_id, incident_id=record.incident_id,
                hazard=record.hazard, source_entity_id=record.entity_id, profile=record.profile_id,
                profile_version=record.profile_version, activated_at=record.activated_at,
                alarm_active=record.alarm_active, gas_switching_inhibited=record.gas_switching_inhibited,
                retention_status=status, identity_available=record.kind == "known",
                retention_status_label=label(status),
                detector=record.context.get("detector"))
            if len(details) >= 64 or len(json.dumps(details + [detail], ensure_ascii=False).encode("utf-8")) > 60_000:
                break
            details.append(detail)
        return dict(monitoring_enabled=monitoring_enabled, history_unknown=self.history_unknown,
            gas_inhibition_unknown=self.gas_history_unknown, gas_switching_inhibited=self.gas_inhibited,
            retained_records_total=len(self.records), retained_records_omitted=len(self.records) - len(details),
            retained_active_hazards=sum(record.alarm_active for record in self.records.values()),
            retained_records=details, persistence_error=self.persistence_error,
            persistence_durable_revision=self.durable_revision, persistence_desired_revision=self.revision,
            dirty_marker_durable=self.marker_durable)

    def covers_older_journal_activation(self, fault_id: str, frame: Mapping[str, Any]) -> bool:
        """Reconcile only a matching incident covered by a later durable clear proof."""
        if self.history_unknown or any(item.fault_id == fault_id and item.alarm_active for item in self.records.values()):
            return False
        context = frame.get("context")
        if not isinstance(context, dict):
            return False
        generation = context.get("indoor_owner_generation")
        if isinstance(generation, bool) or not isinstance(generation, int):
            return False
        return any(item.fault_id == fault_id and item.symptom_id == frame.get("symptom")
                   and item.incident_id == context.get("indoor_incident_id") and not item.alarm_active
                   and item.clear_proof is not None and generation < item.clear_proof.generation <= self.durable_revision
                   for item in self.records.values())

    def set_alarm(self, binding: DetectorBinding, context: Mapping[str, Any], *, at: datetime) -> IndoorRecord:
        """Commit in-memory danger immediately, then enqueue independent persistence."""
        if self.stopped:
            raise ValueError("Indoor owner has stopped")
        previous = self.current_record(binding)
        if previous is not None and previous.alarm_active:
            if previous.record_id in self._pending_clears:
                self._pending_clears.pop(previous.record_id)
                self._enqueue()
            return previous
        identity = previous.record_id if previous is not None else uuid4().hex
        record = IndoorRecord(kind="known", record_id=identity, detector_key=binding.detector_key,
            symptom_id=f"InternalEnv_{binding.hazard}_{binding.detector_key}", fault_id=INDOOR_FAULTS[binding.hazard],
            incident_id=uuid4().hex, hazard=cast(Literal["smoke", "flammable_gas", "carbon_monoxide", "water_leak"], binding.hazard), entity_id=binding.entity_id,
            profile_id=binding.profile_id, profile_version=binding.profile_version, binding_fingerprint=binding.fingerprint,
            activated_at=at.astimezone(timezone.utc).isoformat(), alarm_active=True,
            gas_switching_inhibited=binding.hazard == "flammable_gas" or bool(previous and previous.gas_switching_inhibited), context=dict(context))
        self.records[identity] = record
        try:
            self.checkpoint()
        except (ValueError, TypeError):
            if previous is None:
                self.records.pop(identity)
            else:
                self.records[identity] = previous
            self.history_unknown = self.gas_history_unknown = True
            self.persistence_error = "record_capacity_exhausted"
            self._enqueue()
            return record
        self._pending_clears.pop(identity, None)
        self._enqueue()
        return record

    def request_clear(self, record_id: str, token: str, eligible: Callable[[], bool], *, candidate: ClearCandidate | None = None) -> bool:
        """Stage exact incident/token proof while keeping public danger active."""
        record = self.records.get(record_id)
        revision = self.revision
        if not self.recovery_ready or record is None or record.kind != "known" or not record.alarm_active:
            return False
        if (candidate is None or candidate.token != token or candidate.incident_id != record.incident_id
                or candidate.binding_fingerprint != record.binding_fingerprint):
            return False
        try:
            valid = eligible()
        except Exception:
            valid = False
        if not valid or not self.recovery_ready or self.revision != revision or self.records.get(record_id) is not record:
            return False
        self._pending_clears[record_id] = (str(record.incident_id), candidate, eligible)
        return self._enqueue()

    def cancel_clear(self, record_id: str) -> None:
        """Fence a queued CLEAR on discontinuity or positive evidence."""
        if self._pending_clears.pop(record_id, None) is not None:
            self._enqueue()

    def drain(self) -> list[str]:
        """Apply only the latest acknowledged snapshot and recheck current authority."""
        result = self.writer.drain(self.session)
        if result is None:
            return []
        if result.error is not None:
            if result.revision >= self.durable_revision:
                self.persistence_error = "write_" + result.error
            return []
        self.durable_revision = max(self.durable_revision, result.revision)
        if result.revision >= (self.marker_revision or 2**63):
            self.marker_durable = True
        if result.revision != self.revision:
            return []
        self.persistence_error = None if not self.history_unknown else "history_unverified"
        cleared = []
        for record_id, pending in list(self._pending_clears.items()):
            incident, candidate, eligible = pending
            record = self.records[record_id]
            try:
                valid = not self.stopped and record.incident_id == incident and eligible()
            except Exception:
                valid = False
            # Source/readback policy can reenter the owner. A newer positive,
            # cancellation or candidate must fence this exact acknowledgement.
            if (self.revision != result.revision or self.records.get(record_id) is not record
                    or self._pending_clears.get(record_id) is not pending):
                continue
            if valid and not self.stopped:
                staged = self.checkpoint(staged=True)
                self.records[record_id] = next(item for item in staged.records if item.record_id == record_id)
                cleared.append(record_id)
            else:
                self.persistence_error = "clear_authority_lost"
            if self._pending_clears.get(record_id) is pending:
                self._pending_clears.pop(record_id, None)
        if self.persistence_error == "clear_authority_lost":
            self._enqueue()
        return cleared

    def stop(self) -> bool:
        """Stay dirty unless ingress stopped and every prior write is acknowledged."""
        self.stopped = True
        for record_id in list(self._pending_clears):
            self.cancel_clear(record_id)
        self.drain()
        if self.persistence_error is not None or self.durable_revision != self.revision:
            return False
        # The worker can commit this clean marker after return; all domain ingress
        # and prior writes are already fenced. A failed/hung write leaves dirty.
        self.clean = self._enqueue(clean=True)
        return self.clean


class InternalEnvironmentStateStore(Protocol):
    """Persistence boundary used by the internal hazard monitor."""

    def load(self) -> dict[str, Any]:
        """Load the last valid state snapshot."""

    def save(self, snapshot: Mapping[str, Any]) -> None:
        """Atomically replace the stored state snapshot."""


class InMemoryInternalEnvironmentStateStore:
    """Deterministic state store for tests and disabled persistence."""

    def __init__(self, snapshot: Mapping[str, Any] | None = None) -> None:
        self.snapshot = dict(snapshot or {})
        self.witness_identity = "memory:" + uuid4().hex

    def load(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.snapshot))

    def save(self, snapshot: Mapping[str, Any]) -> None:
        self.snapshot = json.loads(json.dumps(dict(snapshot), default=str))


class JsonInternalEnvironmentStateStore:
    """Versioned JSON state stored outside the deployed application tree."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Indoor checkpoint exceeds 1 MiB")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("internal environment state root must be an object")
        return payload

    def save(self, snapshot: Mapping[str, Any]) -> None:
        if len(json.dumps(dict(snapshot), ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BYTES:
            raise ValueError("Indoor checkpoint exceeds 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(dict(snapshot), stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
