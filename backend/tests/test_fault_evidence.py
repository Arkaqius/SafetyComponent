"""Regression tests for bounded, first-activation fault evidence."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.sqlite_state_store import SqliteStateDatabase
from components.core.types_common import Fault, FaultState, Symptom
from components.faults_manager.evidence import (
    FRAME_FIELDS,
    LIFECYCLE_FIELDS,
    FaultEvidenceJournal,
)
from components.faults_manager.evidence_store import (
    InMemoryFaultEvidenceStore,
    FaultEvidenceStore,
    JsonFaultEvidenceStore,
)
from components.faults_manager.fault_manager import FaultManager


def _model() -> tuple[Fault, Symptom]:
    fault = Fault("RiskyTemperatureOffice", ["sm_tc_1"], 2)
    symptom = Symptom(
        "RiskyTemperatureOffice",
        "sm_tc_1",
        Mock(),
        {
            "temperature_sensor": "sensor.office_temperature",
            "CAL_LOW_TEMP_THRESHOLD": 18.0,
        },
    )
    return fault, symptom


def _journal(
    store: FaultEvidenceStore,
    now: list[datetime],
    elapsed: list[float],
    **bounds: int,
) -> FaultEvidenceJournal:
    return FaultEvidenceJournal(
        store,
        clock=lambda: now[0],
        elapsed_clock=lambda: elapsed[0],
        **bounds,
    )


@pytest.mark.parametrize("durable", [False, True])
def test_first_activation_is_immutable_through_refresh_and_source_change(tmp_path, durable) -> None:
    """Quiet SET refreshes never replace first evidence or increment count."""

    fault, symptom = _model()
    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    elapsed = [100.0]
    store = (
        SqliteStateDatabase(tmp_path / "state.sqlite3").store("fault_evidence_state", tmp_path / "evidence.json")
        if durable else InMemoryFaultEvidenceStore()
    )
    journal = _journal(store, now, elapsed)
    hass = Mock()
    hass.get_state.return_value = {
        "state": "17.2",
        "last_updated": "2026-10-03T07:59:55+00:00",
        "attributes": {"api_token": "must-not-capture"},
    }
    mqtt = Mock(spec=MqttEntityManager)
    mqtt.get_attributes.return_value = {"extended_data": {"activation_count": 99}}
    manager = FaultManager(
        hass,
        {},
        {symptom.name: symptom},
        {fault.name: fault},
        EventBus(),
        mqtt,
        evidence_journal=journal,
    )

    manager.set_symptom(symptom.name, {"location": "Office", "reason": "cold"})
    original = journal.get(fault.name)
    assert original is not None
    first_published = mqtt.publish_sensor_state.call_args.kwargs["attributes"]
    assert first_published["freeze_frame"] == original["freeze_frame"]
    assert original["freeze_frame"]["source"]["state"] == "17.2"
    assert (
        original["freeze_frame"]["source"]["entity_id"] == "sensor.office_temperature"
    )
    assert original["freeze_frame"]["configuration"]["CAL_LOW_TEMP_THRESHOLD"] == 18.0
    assert original["freeze_frame"]["activation_count"] == 1
    assert "extended_data" not in original
    assert "extended_data" not in first_published
    detached = journal.get(fault.name)
    detached["freeze_frame"]["context"]["location"] = "Changed by reader"
    assert journal.get(fault.name) == original

    hass.get_state.return_value = {
        "state": "12.0",
        "last_updated": "2026-10-03T08:01:00+00:00",
    }
    now[0] += timedelta(minutes=1)
    manager.set_symptom(symptom.name, {"location": "Office", "reason": "colder"})
    assert journal.get(fault.name) == original
    assert hass.get_state.call_count == 1
    manager.mark_evaluation_unavailable(symptom.name)
    assert journal.get(fault.name) == original
    assert journal.get(fault.name)["active"] is True
    assert _journal(store, now, elapsed).get(fault.name) == {
        **original, "freeze_frame": {**original["freeze_frame"], "clock_uncertain": True}
    }


def test_predicate_sample_is_not_replaced_by_later_ha_readback() -> None:
    """The actual SM value wins, and timestamp provenance stays explicit."""

    fault, symptom = _model()
    journal = FaultEvidenceJournal(InMemoryFaultEvidenceStore())
    hass = Mock()
    hass.get_state.return_value = {
        "state": "25",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "attributes": {"secret": "never-persist"},
    }
    mqtt = Mock(spec=MqttEntityManager)
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(
        hass,
        {},
        {symptom.name: symptom},
        {fault.name: fault},
        EventBus(),
        mqtt,
        evidence_journal=journal,
    )
    manager.handle_symptom_event(
        symptom_id=symptom.name,
        state=FaultState.SET,
        additional_info={"location": "Office"},
        diagnostic_evidence={"state": 17.2, "threshold": 18.0, "unit": "°C"},
    )
    source = journal.get(fault.name)["freeze_frame"]["source"]
    assert source["state"] == 17.2
    assert source["threshold"] == 18.0
    assert source["unit"] == "°C"
    assert source["value_origin"] == "predicate"
    assert source["quality"] == "eligible"
    assert source["timestamp_relation"] == "readback"
    assert "secret" not in str(journal.get(fault.name))


def test_clear_and_new_activation_replaces_frame_without_episode_identity() -> None:
    """Only valid recovery opens the way for a second first-activation frame."""

    fault, symptom = _model()
    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    elapsed = [100.0]
    journal = _journal(InMemoryFaultEvidenceStore(), now, elapsed)
    journal.activate(fault, symptom, {"reason": "first"})
    elapsed[0] = 115.5
    now[0] += timedelta(minutes=2)
    journal.clear(fault.name)
    cleared = journal.get(fault.name)
    assert cleared is not None
    assert cleared["freeze_frame"]["active_duration_seconds"] == 15.5
    assert cleared["freeze_frame"]["last_valid_pass_at"] is not None

    now[0] += timedelta(minutes=1)
    journal.activate(fault, symptom, {"reason": "second"})
    next_record = journal.get(fault.name)
    assert next_record is not None
    assert next_record["freeze_frame"]["activation_count"] == 2
    assert next_record["freeze_frame"]["context"]["reason"] == "second"
    assert (
        next_record["freeze_frame"]["first_failure_at"]
        == cleared["freeze_frame"]["first_failure_at"]
    )
    assert "episode" not in str(next_record).lower()


def test_allowlist_rejects_secrets_nested_payloads_and_enforces_frame_bound() -> None:
    """Neither unexpected keys nor secret-looking values enter persisted data."""

    fault, symptom = _model()
    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    journal = _journal(InMemoryFaultEvidenceStore(), now, [0.0], max_frame_bytes=800)
    journal.activate(
        fault,
        symptom,
        {
            "location": "Office",
            "reason": "Bearer hidden",
            "token": "hidden",
            "current_value": {"nested": "secret"},
            "failed_check": "freshness",
            "providers": "x" * 300,
        },
        source={
            "entity_id": "sensor.office_temperature",
            "state": "secret-value",
            "attributes": {"password": "hidden"},
        },
    )
    record = journal.get(fault.name)
    assert record is not None
    serialized = str(record).lower()
    assert "hidden" not in serialized
    assert "secret-value" not in serialized
    assert "nested" not in serialized
    assert record["freeze_frame"]["context"]["location"] == "Office"
    captured = {key: record["freeze_frame"][key] for key in FRAME_FIELDS}
    assert len(json.dumps(captured).encode("utf-8")) <= 800


def test_restart_preserves_active_frame_without_inventing_elapsed_time() -> None:
    """A restarted process cannot infer what happened during its absence."""

    fault, symptom = _model()
    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    store = InMemoryFaultEvidenceStore()
    journal = _journal(store, now, [10.0])
    journal.activate(fault, symptom, {"reason": "first"})
    now[0] += timedelta(hours=2)
    restored = _journal(store, now, [1.0])
    restored.activate(fault, symptom, {"reason": "refresh"})
    record = restored.get(fault.name)
    assert record is not None
    assert record["freeze_frame"]["activation_count"] == 1
    assert record["freeze_frame"]["context"]["reason"] == "first"
    assert record["freeze_frame"]["clock_uncertain"] is True
    restored.clear(fault.name)
    assert restored.get(fault.name)["freeze_frame"]["active_duration_seconds"] is None


def test_first_valid_pass_after_restart_closes_old_activation() -> None:
    """An old active record must not suppress a truly new activation forever."""

    fault, symptom = _model()
    store = InMemoryFaultEvidenceStore()
    journal = FaultEvidenceJournal(store)
    journal.activate(fault, symptom, {"reason": "first"})
    restored = FaultEvidenceJournal(store)
    mqtt = Mock(spec=MqttEntityManager)
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(
        Mock(),
        {},
        {symptom.name: symptom},
        {fault.name: fault},
        EventBus(),
        mqtt,
        evidence_journal=restored,
    )
    manager.clear_symptom(symptom.name, {})
    assert restored.get(fault.name)["active"] is False
    manager.set_symptom(symptom.name, {"reason": "second"})
    assert restored.get(fault.name)["freeze_frame"]["activation_count"] == 2


def test_capacity_evicts_oldest_inactive_but_never_active() -> None:
    """Full active capacity drops diagnostics, not the safety event."""

    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    journal = _journal(InMemoryFaultEvidenceStore(), now, [0.0], max_records=2)
    for name in ("First", "Second"):
        fault = Fault(name, ["sm_tc_1"], 2)
        symptom = Symptom(name, "sm_tc_1", Mock(), {})
        journal.activate(fault, symptom, {})
        now[0] += timedelta(minutes=1)
    third = Fault("Third", ["sm_tc_1"], 2)
    journal.activate(third, Symptom("Third", "sm_tc_1", Mock(), {}), {})
    assert journal.get("Third") is None
    journal.clear("First")
    journal.activate(third, Symptom("Third", "sm_tc_1", Mock(), {}), {})
    assert journal.get("First") is None
    assert journal.get("Second") is not None
    assert journal.get("Third") is not None


def test_failed_recapture_does_not_present_old_frame_as_current() -> None:
    """An old cleared frame is discarded if active capacity blocks replacement."""

    observed = Mock()
    journal = FaultEvidenceJournal(
        InMemoryFaultEvidenceStore(),
        max_records=6,
        max_frame_bytes=800,
        max_total_bytes=4096,
        diagnostics_observer=observed,
    )
    first = Fault("First", ["sm_tc_1"], 2)
    others = [
        Fault(name, ["sm_tc_1"], 2)
        for name in (
            "Second",
            "Third",
            "Fourth",
            "Fifth",
            "Sixth",
        )
    ]
    for fault in (first, *others):
        journal.activate(fault, Symptom(fault.name, "sm_tc_1", Mock(), {}), {})
    journal.clear("First")
    journal.activate(
        first,
        Symptom("First", "sm_tc_1", Mock(), {}),
        {"location": "a" * 160, "reason": "b" * 160},
    )
    assert journal.get("First") is None
    assert all(journal.get(fault.name) is not None for fault in others)
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="capacity"
    )


def test_total_storage_bound_evicts_inactive_records() -> None:
    """The serialized snapshot stays below the configured byte budget."""

    store = InMemoryFaultEvidenceStore()
    journal = FaultEvidenceJournal(
        store, max_records=20, max_frame_bytes=800, max_total_bytes=4096
    )
    for index in range(10):
        name = f"BoundedFault{index}"
        fault = Fault(name, ["sm_tc_1"], 2)
        symptom = Symptom(name, "sm_tc_1", Mock(), {})
        journal.activate(fault, symptom, {"reason": "test"})
        journal.clear(name)
    assert len(json.dumps(store.snapshot, ensure_ascii=False).encode("utf-8")) <= 4096
    assert journal.get("BoundedFault0") is None
    assert journal.get("BoundedFault9") is not None


class FailingStore(InMemoryFaultEvidenceStore):
    """Simulate unavailable diagnostic storage without altering fault handling."""

    def save(self, snapshot: dict[str, object]) -> None:
        raise OSError("disk unavailable")


def test_storage_failure_is_reported_without_blocking_fault_activation() -> None:
    """Persistence loss asserts App Health but leaves the H fault active."""

    fault, symptom = _model()
    observed = Mock()
    journal = FaultEvidenceJournal(
        FailingStore(),
        diagnostics_observer=observed,
    )
    mqtt = Mock(spec=MqttEntityManager)
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(
        Mock(),
        {},
        {symptom.name: symptom},
        {fault.name: fault},
        EventBus(),
        mqtt,
        evidence_journal=journal,
    )
    manager.set_symptom(symptom.name, {"reason": "cold"})
    assert fault.evaluation.active is True
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="save"
    )


def test_runtime_defers_disk_io_until_after_fault_response_and_retries() -> None:
    """A blocked disk must not delay the synchronous safety response path."""

    fault, symptom = _model()
    scheduled: list[tuple[object, int]] = []
    observed = Mock()
    store = FailingStore()
    journal = FaultEvidenceJournal(
        store,
        diagnostics_observer=observed,
        schedule_flush=lambda callback, delay: scheduled.append((callback, delay)),
    )
    bus = EventBus()
    events: list[str] = []
    bus.subscribe("fault", lambda **_: events.append("response"))
    mqtt = Mock(spec=MqttEntityManager)
    mqtt.get_attributes.return_value = {}
    manager = FaultManager(
        Mock(),
        {},
        {symptom.name: symptom},
        {fault.name: fault},
        bus,
        mqtt,
        evidence_journal=journal,
    )

    manager.set_symptom(symptom.name, {"reason": "cold"})
    assert events == ["response"]
    assert journal.get(fault.name) is not None
    assert len(scheduled) == 1 and scheduled[0][1] == 0
    assert store.snapshot == {}
    callback = scheduled.pop(0)[0]
    callback()
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="save"
    )
    assert len(scheduled) == 1 and scheduled[0][1] == 60


def test_atomic_json_store_restarts_and_rejects_oversized_file(tmp_path) -> None:
    """Diagnostic storage is independent, versioned and bounded on read."""

    fault, symptom = _model()
    path = tmp_path / "fault_evidence.json"
    store = JsonFaultEvidenceStore(str(path), max_bytes=1048576)
    journal = FaultEvidenceJournal(store)
    journal.activate(fault, symptom, {"reason": "first"})
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))
    restored = FaultEvidenceJournal(store)
    assert restored.get(fault.name)["freeze_frame"]["activation_count"] == 1
    observed = Mock()
    too_small = FaultEvidenceJournal(
        JsonFaultEvidenceStore(str(path), max_bytes=16),
        diagnostics_observer=observed,
    )
    assert too_small.get(fault.name) is None
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="load"
    )


def test_tampered_store_cannot_republish_unallowlisted_secrets() -> None:
    """A previously stored object is validated before MQTT can expose it."""

    fault, symptom = _model()
    store = InMemoryFaultEvidenceStore()
    FaultEvidenceJournal(store).activate(fault, symptom, {"reason": "first"})
    store.snapshot["records"][fault.name]["freeze_frame"]["context"]["token"] = "hidden"
    observed = Mock()
    restored = FaultEvidenceJournal(store, diagnostics_observer=observed)
    assert restored.get(fault.name) is None
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="load"
    )


def test_version_one_store_migrates_all_fields_to_one_freeze_frame() -> None:
    """Migration retains capture and counters, then writes only the new shape."""

    fault, symptom = _model()
    store = InMemoryFaultEvidenceStore()
    journal = FaultEvidenceJournal(store, max_frame_bytes=800)
    journal.activate(
        fault, symptom, {"location": "Office", "reason": "x" * 160, "providers": "y" * 160}
    )
    journal.clear(fault.name)
    expected = journal.get(fault.name)
    frame = expected["freeze_frame"]
    assert len(json.dumps(frame).encode("utf-8")) > 800
    store.snapshot = {
        "version": 1,
        "records": {
            fault.name: {
                "active": False,
                "freeze_frame": {
                    **{key: frame[key] for key in FRAME_FIELDS},
                    "version": 1,
                },
                "extended_data": {key: frame[key] for key in LIFECYCLE_FIELDS},
            }
        },
    }

    restored = FaultEvidenceJournal(store, max_frame_bytes=800)
    assert restored.get(fault.name) == expected
    assert store.snapshot["version"] == 2
    assert store.snapshot["records"][fault.name] == expected
    assert "extended_data" not in json.dumps(store.snapshot)


def test_version_one_migration_rejects_unallowlisted_lifecycle_fields() -> None:
    """Legacy diagnostics cannot bypass validation on the way to MQTT."""

    fault, symptom = _model()
    store = InMemoryFaultEvidenceStore()
    FaultEvidenceJournal(store).activate(fault, symptom, {})
    frame = store.snapshot["records"][fault.name]["freeze_frame"]
    store.snapshot = {
        "version": 1,
        "records": {
            fault.name: {
                "active": True,
                "freeze_frame": {
                    **{key: frame[key] for key in FRAME_FIELDS},
                    "version": 1,
                },
                "extended_data": {
                    **{key: frame[key] for key in LIFECYCLE_FIELDS},
                    "token": "hidden",
                },
            }
        },
    }
    observed = Mock()

    restored = FaultEvidenceJournal(store, diagnostics_observer=observed)
    assert restored.get(fault.name) is None
    observed.assert_any_call(
        "persistence", True, detail="fault_evidence_state", operation="load"
    )


def test_lifecycle_updates_keep_captured_fields_and_capture_bound() -> None:
    """Clear and restart change lifecycle fields without rewriting the sample."""

    fault, symptom = _model()
    store = InMemoryFaultEvidenceStore()
    now = [datetime(2026, 10, 3, 8, tzinfo=timezone.utc)]
    elapsed = [10.0]
    journal = _journal(store, now, elapsed, max_frame_bytes=1024)
    journal.activate(fault, symptom, {"reason": "x" * 160, "location": "Office"})
    captured = journal.get(fault.name)["freeze_frame"]
    now[0] += timedelta(minutes=1, microseconds=1)
    elapsed[0] += 60.123
    journal.clear(fault.name)
    cleared = journal.get(fault.name)["freeze_frame"]
    assert {key: captured[key] for key in FRAME_FIELDS} == {
        key: cleared[key] for key in FRAME_FIELDS
    }
    assert cleared["active_duration_seconds"] == 60.123
    capture = {key: cleared[key] for key in FRAME_FIELDS}
    assert len(json.dumps(capture, ensure_ascii=False).encode("utf-8")) <= 1024
    assert FaultEvidenceJournal(store, max_frame_bytes=1024).get(fault.name) is not None


def test_entity_registration_publishes_only_unified_freeze_frame(
    mocked_hass_app_with_temp_component,
) -> None:
    """Initial discovery exposes the same schema as subsequent fault updates."""

    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    fault = app.faults["RiskyTemperature"]
    symptom = app.symptoms["RiskyTemperatureOffice"]
    app.fault_evidence.activate(fault, symptom, {"reason": "cold"})
    app.mqtt_entities = Mock(spec=MqttEntityManager)

    app.register_entities()

    registration = next(
        call for call in app.mqtt_entities.register_sensor.call_args_list
        if call.args[0] == "sensor.fault_RiskyTemperature"
    )
    attributes = registration.kwargs["attributes"]
    assert attributes["freeze_frame"] == app.fault_evidence.get(fault.name)["freeze_frame"]
    assert attributes["freeze_frame"]["activation_count"] == 1
    assert "extended_data" not in attributes
