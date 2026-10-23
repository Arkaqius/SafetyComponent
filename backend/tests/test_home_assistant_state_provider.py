"""Check live report transport, failure isolation, and source timestamps."""

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from jinja2.sandbox import ImmutableSandboxedEnvironment

from components.external_apis.home_assistant_state import (
    REPORT_TEMPLATE,
    HomeAssistantStateProvider,
    parse_device_contact,
)
from tests.test_functional_safety_monitor import make_monitor, snapshot


def test_provider_keeps_actual_report_timestamp(monkeypatch):
    row = {"entity_id": "binary_sensor.wan", **snapshot("on")}
    def open_report(request, timeout):
        assert timeout == 120
        payload = json.loads(request.data)
        assert payload["variables"]["entities"] == ["binary_sensor.wan"]
        assert "last_reported" in payload["template"]
        return BytesIO(json.dumps([row]).encode())
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", open_report)
    assert HomeAssistantStateProvider("test").poll({"binary_sensor.wan"}) == {"binary_sensor.wan": row}


def test_provider_honors_independent_fast_timeout(monkeypatch):
    row = {"entity_id": "binary_sensor.window", **snapshot("on")}
    def open_report(request, timeout):
        assert timeout == 3
        return BytesIO(json.dumps([row]).encode())
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", open_report)
    assert HomeAssistantStateProvider("test").poll(
        {"binary_sensor.window"}, timeout_seconds=3
    ) == {"binary_sensor.window": row}


@pytest.mark.parametrize("payload", ["{}", "null", '[{"entity_id":"other"}]', "invalid", '[{"entity_id":"binary_sensor.wan","state":"on","attributes":{}}]'])
def test_invalid_responses_are_not_evidence(monkeypatch, payload):
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", lambda *_args, **_kwargs: BytesIO(payload.encode()))
    assert HomeAssistantStateProvider("test").poll({"binary_sensor.wan"}) == {}


def test_transport_failure_is_not_cached(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("offline")
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", fail)
    assert HomeAssistantStateProvider("test").poll({"binary_sensor.wan"}) == {}


def test_live_reports_override_unchanged_cache_and_failure_does_not_heal(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("components.core.functional_safety_monitor.monotonic", lambda: clock[0])
    monitor, bus, mqtt = make_monitor({"binary_sensor.wan": snapshot("on", old=True)})
    reports = {"binary_sensor.wan": snapshot("off")}
    class Provider:
        def poll(self, entities):
            assert "binary_sensor.wan" in entities
            return reports.copy()
    monitor.state_provider = Provider()
    monitor.evaluate()
    clock[0] = 101.0
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "offline"
    events = len(bus.events)
    reports.clear()
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "unknown"
    assert len(bus.events) == events
    reports["binary_sensor.wan"] = snapshot("on")
    reports["binary_sensor.wan"]["last_updated"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "recovering"
    clock[0] = 102.0
    monitor.evaluate()
    assert mqtt.states[-1][2]["wan"]["status"] == "online"


def test_absent_supervisor_token_uses_legacy_cache(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert HomeAssistantStateProvider.from_environment() is None


def test_discovery_uses_fixed_template_and_reports_transport_failure(monkeypatch):
    from tests.test_battery_inventory import row
    def open_inventory(request, timeout):
        payload = json.loads(request.data)
        assert "device_id(s.entity_id)" in payload["template"]
        assert timeout == 3
        return BytesIO(json.dumps([row()]).encode())
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", open_inventory)
    assert HomeAssistantStateProvider("test").discover_batteries()["status"] == "ready"
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", lambda *_args, **_kwargs: BytesIO(b"null"))
    assert HomeAssistantStateProvider("test").discover_batteries() == {"status": "error", "devices": []}


@pytest.mark.parametrize("value", [
    "1726315200", 1726315200, "1726315200000", 1726315200000,
    "2024-09-14T12:00:00Z", "2024-09-14T14:00:00+02:00",
])
def test_contact_supports_epoch_seconds_milliseconds_and_aware_iso(value):
    assert parse_device_contact(value) == datetime(2024, 9, 14, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [
    None, True, False, "unknown", "unavailable", "", "NaN", "inf", -1, 0,
    "2024-09-14T12:00:00", "9999-12-31T23:59:59+00:00", "1e100",
    10 ** 1000, "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00",
])
def test_invalid_or_future_contact_is_not_observed_evidence(value):
    assert parse_device_contact(value) is None


def test_contact_is_additional_evidence_and_never_replaces_unknown_alarm_state(monkeypatch):
    row = {"entity_id": "binary_sensor.example_water_leak", **snapshot("unknown")}
    row["device_last_seen"] = {"entity_id": "sensor.example_last_seen", "state": "1726315200000"}
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", lambda *_args, **_kwargs: BytesIO(json.dumps([row]).encode()))
    report = HomeAssistantStateProvider("test").poll({row["entity_id"]})[row["entity_id"]]
    assert report["state"] == "unknown"
    assert report["last_contact_at"] == "2024-09-14T12:00:00+00:00"
    assert report["last_contact_source_entity"] == "sensor.example_last_seen"
    row["device_last_seen"]["state"] = "unknown"
    report = HomeAssistantStateProvider("test").poll({row["entity_id"]})[row["entity_id"]]
    assert report["state"] == "unknown"
    assert "last_contact_at" not in report

    assert report["last_contact_source_entity"] == "sensor.example_last_seen"


@pytest.mark.parametrize("entity_id", [
    "sensor.example_temperature", "sensor.example_humidity",
    "sensor.example_battery", "binary_sensor.example_contact",
])
@pytest.mark.parametrize("siblings,contacts", [
    ([], []),
    (["sensor.example_last_seen"], ["sensor.example_last_seen"]),
    (["sensor.example_last_seen_2"], ["sensor.example_last_seen_2"]),
    (["sensor.example_last_seen_12"], ["sensor.example_last_seen_12"]),
    (["sensor.example_last_seen", "sensor.duplicate_last_seen"],
     ["sensor.example_last_seen", "sensor.duplicate_last_seen"]),
    (["sensor.example_last_seen", "sensor.example_last_seen_2"],
     ["sensor.example_last_seen", "sensor.example_last_seen_2"]),
    (["sensor.example_last_seen_2", "sensor.example_last_seen_3"],
     ["sensor.example_last_seen_2", "sensor.example_last_seen_3"]),
    (["sensor.example_last_seen_text", "sensor.example_last_seen_2_extra",
      "sensor.example_last_seen_", "sensor.example_last_seen_2_3",
      "binary_sensor.example_last_seen_2"], []),
])
def test_report_template_uses_only_one_contact_from_the_same_sensor_device(
    monkeypatch, entity_id, siblings, contacts,
):
    timestamp = datetime(2024, 9, 14, 12, tzinfo=timezone.utc)
    state = SimpleNamespace(
        entity_id=entity_id, state="21.5", attributes={},
        last_changed=timestamp, last_updated=timestamp, last_reported=timestamp,
    )
    environment = ImmutableSandboxedEnvironment()
    environment.filters["to_json"] = json.dumps
    environment.globals.update(
        expand=lambda entity: [state] if entity == entity_id else [],
        device_id=lambda entity: "example-device" if entity == entity_id else "other-device",
        device_entities=lambda device: siblings if device == "example-device" else ["sensor.other_last_seen"],
        states=lambda _: "1726315200000",
    )

    def render_report(request, timeout):
        payload = json.loads(request.data)
        return BytesIO(environment.from_string(payload["template"]).render(
            **payload["variables"],
        ).encode())

    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", render_report)
    report = HomeAssistantStateProvider("test").poll({entity_id})[entity_id]
    assert report["state"] == "21.5"
    assert report["last_contact_source_count"] == len(contacts)
    if len(contacts) == 1:
        assert report["last_contact_at"] == timestamp.isoformat()
        assert report["last_contact_source_entity"] == contacts[0]
    else:
        assert "last_contact_at" not in report
        assert "last_contact_source_entity" not in report


@pytest.mark.parametrize("value,status", [("16", "current"), ("1", "low")])
def test_suffixed_device_contact_qualifies_unchanged_battery(monkeypatch, value, status):
    """A recent suffixed heartbeat qualifies an old value on either side of the threshold."""
    battery = snapshot(value, unit="%", kind="battery", old=True)
    state = SimpleNamespace(
        entity_id="sensor.battery", state=value, attributes=battery["attributes"],
        last_changed=datetime.fromisoformat(battery["last_updated"]),
        last_updated=datetime.fromisoformat(battery["last_updated"]),
        last_reported=datetime.fromisoformat(battery["last_reported"]),
    )
    contact = snapshot("on")["last_reported"]
    environment = ImmutableSandboxedEnvironment()
    environment.filters["to_json"] = json.dumps
    environment.globals.update(
        expand=lambda entity: [state] if entity == state.entity_id else [],
        device_id=lambda _: "battery-device",
        device_entities=lambda _: ["sensor.remote_last_seen_2"],
        states=lambda _: contact,
    )

    def render_report(request, timeout):
        payload = json.loads(request.data)
        return BytesIO(environment.from_string(payload["template"]).render(
            **payload["variables"],
        ).encode())

    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", render_report)
    monitor, _, mqtt = make_monitor({"sensor.battery": battery})
    monitor.state_provider = HomeAssistantStateProvider("test")
    monitor.evaluate()
    result = mqtt.states[-1][2]["remote_batteries"]["Remote"]
    assert result["status"] == status
    assert result["percentage"] == float(value)


def test_temperature_without_registry_device_does_not_guess_a_contact_by_name(monkeypatch):
    environment = ImmutableSandboxedEnvironment()
    environment.filters["to_json"] = json.dumps
    timestamp = datetime(2024, 9, 14, 12, tzinfo=timezone.utc)
    state = SimpleNamespace(
        entity_id="sensor.example_temperature", state="21.5", attributes={},
        last_changed=timestamp, last_updated=timestamp, last_reported=timestamp,
    )
    environment.globals.update(
        expand=lambda _: [state], device_id=lambda _: None,
        device_entities=lambda _: pytest.fail("No device siblings without a registry device"),
        states=lambda _: pytest.fail("No last_seen lookup without a registry device"),
    )
    body = environment.from_string(REPORT_TEMPLATE).render(entities=[state.entity_id])
    monkeypatch.setattr("components.external_apis.home_assistant_state.urlopen", lambda *_args, **_kwargs: BytesIO(body.encode()))
    report = HomeAssistantStateProvider("test").poll({state.entity_id})[state.entity_id]
    assert "last_contact_at" not in report
