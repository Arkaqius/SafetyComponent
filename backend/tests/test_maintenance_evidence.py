"""Host and backup evidence must never falsely clear maintenance faults."""

from datetime import datetime, timedelta, timezone

import pytest

from components.core.maintenance_evidence import ResourceRule, aware_time
from components.core.types_common import SMState
from test_functional_safety_monitor import POLICY, FakeBus, FakeEntities, FakeHass, snapshot
from components.core.functional_safety_monitor import FunctionalSafetyMonitor


def _monitor(states: dict, backup: dict | None = None) -> tuple:
    policy = {**POLICY, "disk_low_free_mib": 1024, "disk_recovery_free_mib": 2048, "host_temperature_high_c": 80, "host_temperature_recovery_c": 70, "resource_qualification_seconds": 1, "resource_recovery_seconds": 1, "backup_max_age_hours": 48, "backup_stale_after_seconds": 86400}
    bindings = {"host_disk_free_entity": "sensor.disk", "host_temperature_entity": "sensor.temperature", "battery_monitoring": {"enabled": False}}
    if backup:
        bindings["backup"] = backup
    bus, mqtt = FakeBus(), FakeEntities()
    monitor = FunctionalSafetyMonitor(FakeHass(states), bus, mqtt, bindings, policy, wan_entity=None)
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, {})
    for name, symptom in symptoms.items():
        monitor.init_safety_mechanism(symptom.sm_name, name, {})
        monitor.enable_safety_mechanism(name, SMState.ENABLED)
    return monitor, bus, mqtt


def test_resource_hysteresis_and_unknown_interrupt_qualification(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("components.core.maintenance_evidence.monotonic", lambda: clock[0])
    rule = ResourceRule(10, 20, 2, 2, low=True)
    assert rule.observe(5) == "qualifying"
    clock[0] = 2
    assert rule.observe(5) == "low"
    assert rule.observe(None) == "unknown"
    assert rule.active
    assert rule.observe(21) == "low"
    clock[0] = 3
    assert rule.observe(15) == "low"
    clock[0] = 10
    assert rule.observe(21) == "low"
    clock[0] = 12
    assert rule.observe(21) == "normal"
    assert not rule.active


@pytest.mark.parametrize("value", [None, "bad", "2026-01-01T00:00:00", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()])
def test_invalid_dates_rejected(value: object) -> None:
    assert aware_time(value) is None


def test_host_units_staleness_and_l4_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [10.0]
    monkeypatch.setattr("components.core.maintenance_evidence.monotonic", lambda: clock[0])
    states = {"sensor.disk": snapshot("0.5", unit="GiB", kind="data_size"), "sensor.temperature": snapshot("85", unit="°C", kind="temperature")}
    monitor, bus, mqtt = _monitor(states)
    monitor.evaluate()
    assert mqtt.states[-1][2]["disk"]["free_mib"] == 512
    clock[0] = 11
    monitor.evaluate()
    assert mqtt.states[-1][2]["disk"]["status"] == "low"
    assert mqtt.states[-1][2]["host_temperature"]["status"] == "high"
    assert all(value["level"] == 4 for value in monitor.get_fault_definitions().values())
    events = len(bus.events)
    states["sensor.disk"] = snapshot("99999", unit="%", kind="data_size")
    states["sensor.temperature"] = snapshot("25", unit="°C", kind="temperature", old=True)
    monitor.evaluate()
    assert len(bus.events) == events
    assert mqtt.states[-1][2]["disk"]["reason"] == "wrong_unit"
    assert mqtt.states[-1][2]["host_temperature"]["reason"] == "stale"


def test_backup_failure_and_invalid_evidence_never_clear_active_fault() -> None:
    now = datetime.now(timezone.utc)
    states = {"sensor.backup": snapshot((now - timedelta(hours=60)).isoformat(), kind="timestamp"), "binary_sensor.failure": snapshot("off", kind="problem")}
    monitor, bus, mqtt = _monitor(states, {"last_success_entity": "sensor.backup", "failure_entity": "binary_sensor.failure"})
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "overdue"
    events = len(bus.events)
    states["sensor.backup"] = snapshot("unavailable", kind="timestamp")
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "unknown"
    assert len(bus.events) == events
    states["binary_sensor.failure"] = snapshot("on", kind="problem")
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "failed"
    states["sensor.backup"] = snapshot(now.isoformat(), kind="timestamp")
    states["binary_sensor.failure"] = snapshot("off", kind="problem")
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "current"


def test_backup_stale_failure_and_timestamp_are_unknown() -> None:
    states = {"sensor.backup": snapshot(datetime.now(timezone.utc).isoformat(), kind="timestamp"), "binary_sensor.failure": snapshot("off", kind="problem")}
    states["binary_sensor.failure"]["last_reported"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    monitor, _, mqtt = _monitor(states, {"last_success_entity": "sensor.backup", "failure_entity": "binary_sensor.failure"})
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["reason"] == "failure_source_unavailable"


def test_backup_event_age_not_report_time_and_malformed_attributes() -> None:
    states = {"sensor.backup": snapshot(datetime.now(timezone.utc).isoformat(), kind="timestamp")}
    states["sensor.backup"]["last_reported"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    monitor, bus, mqtt = _monitor(states, {"last_success_entity": "sensor.backup"})
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "current"
    states["sensor.backup"]["state"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "overdue"
    events = len(bus.events)
    states["sensor.backup"]["attributes"] = ["malformed"]
    monitor.evaluate()
    assert mqtt.states[-1][2]["backup"]["status"] == "unknown"
    assert len(bus.events) == events


def test_new_installation_bindings_validate_and_default_checks() -> None:
    from pydantic import ValidationError
    from configuration_model import FunctionalSafetyBindings

    binding = FunctionalSafetyBindings(host_disk_free_entity="sensor.disk", backup={"last_success_entity": "sensor.backup"})
    assert binding.periodic_tests.notification_delivery
    assert not binding.periodic_tests.backup_restore
    for value in ({"host_disk_free_entity": "binary_sensor.disk"}, {"backup": {"last_success_entity": "sensor.backup", "failure_entity": "sensor.problem"}}, {"periodic_tests": {"unapproved_test": True}}):
        with pytest.raises(ValidationError):
            FunctionalSafetyBindings(**value)
