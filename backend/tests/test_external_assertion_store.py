"""Durability and fail-closed validation of retained real exposure assertions."""

from datetime import datetime, timezone
import json

import pytest

from components.core.sqlite_state_store import SqliteStateDatabase
from components.safetycomponents.external_hazard.assertion_store import (
    AssertionRecord,
    RealAssertionStore,
)


def record(**overrides):
    return AssertionRecord(
        **{
            "symptom_id": "ExternalWeatherExposureWindWindow",
            "fault_id": "ExternalWeatherExposure",
            "opening": "Window",
            "hazard": "wind",
            "source": "ImgwWarningsApiComponent",
            "asserted_at": datetime.now(timezone.utc).isoformat(),
            "context": {"source": "ImgwWarningsApiComponent", "hazard": "wind"},
            **overrides,
        }
    )


def test_assertion_roundtrip_and_positive_clear(tmp_path):
    database = SqliteStateDatabase(tmp_path / "safety.sqlite3")
    store = RealAssertionStore(database)
    assert store.records == {} and not store.initialized
    entry = record()
    store.assert_real(entry)
    restarted = RealAssertionStore(database)
    assert restarted.records == {entry.symptom_id: entry}
    assert restarted.initialized
    restarted.clear_real(entry.symptom_id)
    assert RealAssertionStore(database).records == {}


def test_failed_clear_does_not_drop_assertion(tmp_path, monkeypatch):
    store = RealAssertionStore(SqliteStateDatabase(tmp_path / "safety.sqlite3"))
    entry = record()
    store.assert_real(entry)
    monkeypatch.setattr(store.storage, "save", lambda _: (_ for _ in ()).throw(OSError("disk failure")))
    with pytest.raises(OSError):
        store.clear_real(entry.symptom_id)
    assert store.records == {entry.symptom_id: entry}


@pytest.mark.parametrize("invalid", [{"unknown": 1}, {"schema_version": 99, "assertions": {}}, {"schema_version": 1, "assertions": {"wrong": record().model_dump()}}])
def test_corrupt_checkpoint_is_not_a_cold_start(tmp_path, invalid):
    database = SqliteStateDatabase(tmp_path / "safety.sqlite3")
    database.record_store("external_hazard_assertions", max_bytes=1_048_576).save(invalid)
    with pytest.raises(ValueError):
        RealAssertionStore(database)


@pytest.mark.parametrize("changes", [{"source": ""}, {"hazard": "alien"}, {"fault_id": "SafetyAppHealth"}, {"asserted_at": "2026-11-13T10:00:00"}, {"context": {"value": float("nan")}}, {"opening": "OtherWindow"}, {"hazard": "rain"}, {"context": {"source": "OtherProvider"}}, {"context": {"opening_id": "OtherWindow"}}])
def test_invalid_real_record_rejected(changes):
    with pytest.raises(ValueError):
        record(**changes)


def test_checkpoint_record_and_byte_budgets(tmp_path):
    store = RealAssertionStore(SqliteStateDatabase(tmp_path / "safety.sqlite3"))
    entries = {f"ExternalWeatherExposureWindOpening{i}": record(symptom_id=f"ExternalWeatherExposureWindOpening{i}", opening=f"Opening{i}") for i in range(4096)}
    assert len(store._validate({key: value.model_dump() for key, value in entries.items()})) == 4096
    # Count validation is independent of the serialized byte limit.
    with pytest.raises(ValueError, match="4096"):
        store.replace({**entries, "ExternalWeatherExposureWindExtra": record(symptom_id="ExternalWeatherExposureWindExtra", opening="Extra")})
    with pytest.raises(ValueError, match="bound|MiB"):
        store.assert_real(record(context={"text": "x" * 1_048_576}))
    assert store.records == {}


def test_exact_utf8_checkpoint_limit_is_accepted_and_one_over_rejected(tmp_path):
    store = RealAssertionStore(SqliteStateDatabase(tmp_path / "safety.sqlite3"))
    entry = record(context={"text": ""})
    payload = {"schema_version": 1, "assertions": {entry.symptom_id: entry.model_dump()}}
    overhead = len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    entry = entry.model_copy(update={"context": {"text": "x" * (1_048_576 - overhead)}})
    store.assert_real(entry)
    with pytest.raises(ValueError, match="MiB"):
        store.assert_real(entry.model_copy(update={"context": {"text": entry.context["text"] + "x"}}))
    assert store.records[entry.symptom_id] == entry
