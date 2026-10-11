"""Check live report transport, failure isolation, and source timestamps."""

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

from components.external_apis.home_assistant_state import HomeAssistantStateProvider, parse_device_contact
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
