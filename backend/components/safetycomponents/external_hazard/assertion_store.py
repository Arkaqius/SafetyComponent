"""Bound active real exposure state across provider selection and process restarts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from components.core.sqlite_state_store import SqliteStateDatabase, SqliteStateStore

MAX_ASSERTIONS = 4096
MAX_CHECKPOINT_BYTES = 1_048_576


class AssertionRecord(BaseModel):
    """A real qualified assertion, retained without restoring timers or commands."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    symptom_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    fault_id: Literal["ExternalWeatherExposure", "OutdoorAirQualityExposure"]
    opening: str = Field(min_length=1, max_length=128)
    hazard: Literal["frost", "wind", "rain", "storm", "outdoor_air_pollution"]
    source: str = Field(min_length=1, max_length=128)
    asserted_at: str
    context: dict[str, Any]

    @model_validator(mode="after")
    def coherent_identity(self) -> "AssertionRecord":
        """Prevent corrupted scope from being cleared by another opening or hazard."""
        air_quality = self.hazard == "outdoor_air_pollution"
        expected_fault = "OutdoorAirQualityExposure" if air_quality else "ExternalWeatherExposure"
        prefix = expected_fault if air_quality else expected_fault + self.hazard.capitalize()
        if self.fault_id != expected_fault or self.symptom_id != prefix + self.opening:
            raise ValueError("Assertion fault, hazard, opening and symptom identity disagree")
        for key, expected in (("source", self.source), ("opening_id", self.opening), ("hazard_code", self.hazard)):
            if key in self.context and self.context[key] != expected:
                raise ValueError("Assertion context disagrees with its scope")
        return self

    @field_validator("asserted_at")
    @classmethod
    def valid_time(cls, value: str) -> str:
        """Reject unknown source-age semantics rather than inventing a timestamp."""
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Assertion timestamp must be timezone-aware")
        return value

    @field_validator("context")
    @classmethod
    def json_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Keep retained context finite JSON data with bounded nesting."""
        def visit(item: Any, depth: int = 0) -> None:
            if depth > 8:
                raise ValueError("Assertion context exceeds depth 8")
            if isinstance(item, dict):
                if any(not isinstance(key, str) for key in item):
                    raise ValueError("Assertion context keys must be strings")
                for child in item.values():
                    visit(child, depth + 1)
            elif isinstance(item, list):
                for child in item:
                    visit(child, depth + 1)
        visit(value)
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class RealAssertionStore:
    """Persist complete assertion snapshots atomically in an isolated SQLite store."""

    def __init__(self, database: SqliteStateDatabase) -> None:
        self.storage: SqliteStateStore = database.record_store(
            "external_hazard_assertions", max_bytes=MAX_CHECKPOINT_BYTES
        )
        payload = self.storage.load()
        self.initialized: bool = bool(payload)
        self._records: dict[str, AssertionRecord] = {}
        if payload:
            version = payload.get("schema_version")
            if set(payload) != {"schema_version", "assertions"} or isinstance(version, bool) or not isinstance(version, int) or version != 1:
                raise ValueError("Invalid real assertion checkpoint schema")
            raw = payload["assertions"]
            if not isinstance(raw, dict):
                raise ValueError("Checkpoint assertions must be a mapping")
            self._records = self._validate(raw)
            self._bounded(payload)

    @property
    def records(self) -> dict[str, AssertionRecord]:
        """Return detached records so callers cannot mutate committed state."""
        return {key: value.model_copy(deep=True) for key, value in self._records.items()}

    @staticmethod
    def _validate(raw: Mapping[str, Any]) -> dict[str, AssertionRecord]:
        if len(raw) > MAX_ASSERTIONS:
            raise ValueError("Real assertion checkpoint exceeds 4096 records")
        result = {}
        for key, value in raw.items():
            record = AssertionRecord.model_validate(value)
            if key != record.symptom_id:
                raise ValueError("Assertion identity does not match record key")
            result[key] = record
        return result

    @staticmethod
    def _bounded(payload: Mapping[str, Any]) -> None:
        size = len(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8"))
        if size > MAX_CHECKPOINT_BYTES:
            raise ValueError("Real assertion checkpoint exceeds 1 MiB bound")

    def replace(self, records: Mapping[str, AssertionRecord]) -> None:
        """Commit a validated checkpoint; a failed write leaves memory unchanged."""
        raw = {key: value.model_dump(mode="json") for key, value in records.items()}
        validated = self._validate(raw)
        payload = {"schema_version": 1, "assertions": raw}
        self._bounded(payload)
        self.storage.save(payload)
        self._records = validated
        self.initialized = True

    def assert_real(self, record: AssertionRecord) -> None:
        """Retain one real assertion before its activation is published."""
        self.replace({**self._records, record.symptom_id: record})

    def clear_real(self, symptom_id: str) -> None:
        """Remove an assertion only after a qualified positive clear decision."""
        self.replace({key: value for key, value in self._records.items() if key != symptom_id})
