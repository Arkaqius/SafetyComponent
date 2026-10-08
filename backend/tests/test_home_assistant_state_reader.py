"""Verify shared polling cadence, nonblocking reads, and failed evidence."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from components.core.types_common import FaultState, SMState
from components.external_apis.home_assistant_state_reader import HomeAssistantStateReader
from tests.test_entity_monitor_component import _component, _config, _snapshot
from tests.test_functional_safety_monitor import make_monitor, snapshot


@pytest.fixture
def scheduled_reader(monkeypatch):
    clock = [100.0]
    jobs = []
    provider = MagicMock()
    provider.poll.return_value = {}

    class QueuedThread:
        def __init__(self, *, target, args, **_):
            self.job = lambda: target(*args)

        def start(self):
            jobs.append(self.job)

    monkeypatch.setattr(
        "components.external_apis.home_assistant_state_reader.Thread", QueuedThread
    )
    monkeypatch.setattr(
        "components.external_apis.home_assistant_state_reader.monotonic",
        lambda: clock[0],
    )
    monkeypatch.setattr(
        "components.core.functional_safety_monitor.monotonic", lambda: clock[0]
    )
    return HomeAssistantStateReader(provider), provider, clock, jobs


def test_batches_due_groups_and_keeps_maintenance_hourly(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("runtime", {"sensor.temperature"}, 60)
    reader.register("maintenance", {"sensor.battery", "update.core"}, 3600)
    reader.tick()
    reader.tick()
    assert len(jobs) == 1
    assert not provider.poll.called
    assert reader.reports("runtime") == {}
    jobs.pop()()
    provider.poll.assert_called_once_with(
        {"sensor.temperature", "sensor.battery", "update.core"}, timeout_seconds=120
    )

    clock[0] += 59
    reader.tick()
    assert jobs == []
    clock[0] += 1
    reader.tick()
    jobs.pop()()
    assert provider.poll.call_args.args[0] == {"sensor.temperature"}
    clock[0] = 3700
    reader.tick()
    jobs.pop()()
    assert provider.poll.call_args.args[0] == {
        "sensor.temperature",
        "sensor.battery",
        "update.core",
    }


def test_failure_discards_previous_reports_and_preserves_source_time(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("runtime", {"sensor.temperature"}, 60)
    row = snapshot("21.21")
    provider.poll.return_value = {"sensor.temperature": row}
    reader.tick()
    jobs.pop()()
    assert (
        reader.report("runtime", "sensor.temperature")["last_reported"]
        == row["last_reported"]
    )
    clock[0] += 59
    copied = reader.reports("runtime")
    copied["sensor.temperature"]["state"] = "99"
    assert reader.report("runtime", "sensor.temperature")["state"] == "21.21"
    clock[0] += 1
    provider.poll.side_effect = OSError("offline")
    reader.tick()
    jobs.pop()()
    assert reader.reports("runtime") == {}
    assert reader.revision("runtime") == 2


def test_stalled_schedule_expires_and_shutdown_rejects_late_response(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("runtime", {"sensor.temperature"}, 60)
    provider.poll.return_value = {"sensor.temperature": snapshot("21.21")}
    reader.tick()
    jobs.pop()()
    clock[0] += 186
    assert reader.reports("runtime") == {}
    assert reader.revision("runtime") == -1
    reader.tick()
    app = MagicMock()
    reader.start(app)
    reader.stop()
    jobs.pop()()
    assert reader.reports("runtime") == {}
    assert reader._groups["runtime"].revision == 1
    app.cancel_timer.assert_called_once()


def test_late_response_is_not_accepted_as_recovery_evidence(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("runtime", {"sensor.temperature"}, 60)
    provider.poll.return_value = {"sensor.temperature": snapshot("21.21")}
    reader.tick()
    clock[0] += 121
    jobs.pop()()
    assert reader.reports("runtime") == {}
    assert reader.revision("runtime") == 1


def test_stalled_fast_read_still_sets_unavailability_within_30_seconds(
    scheduled_reader, mocked_hass_app_basic
):
    reader, provider, clock, jobs = scheduled_reader
    app, bus, component = _component(mocked_hass_app_basic)
    base = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)
    row = _snapshot("on", base)
    app.get_state = MagicMock(return_value=row)
    provider.poll.return_value = {"binary_sensor.window": row}
    component._now = lambda: base + timedelta(seconds=clock[0] - 100)
    component.state_reader = reader
    config = _config("binary_sensor.window")
    dependency = config["component_entities"][0]
    dependency.update(
        checks={}, detection_budget_seconds=30, failure_debounce_seconds=15
    )
    symptoms, _ = component.get_symptoms_data(
        {component.component_name: component}, config
    )
    for symptom in symptoms.values():
        component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    assert (
        component._report_groups["binary_sensor.window"] == "EntityMonitorComponent:5"
    )
    reader.tick()
    jobs.pop()()
    component._evaluate_entity("TemperatureOffice")

    # No event arrives after transport loss immediately following the last read.
    clock[0] = 105
    reader.tick()
    for elapsed in (8, 13, 18, 23, 28):
        clock[0] = 100 + elapsed
        reader.tick()
        component._evaluate_entity("TemperatureOffice")
    assert len(jobs) == 1
    check = component._entities["TemperatureOffice"].checks["availability"]
    assert check.active
    assert check.reason == "source_report_unavailable"
    assert (
        component.symptom_states["EntityHealthFailureTemperatureOfficeAvailability"]
        == FaultState.SET
    )


def test_hourly_maintenance_does_not_follow_runtime_reads_or_heal_on_failure(
    scheduled_reader,
):
    reader, provider, clock, jobs = scheduled_reader
    monitor, bus, _ = make_monitor({})
    monitor.state_reader = reader
    fast, maintenance = monitor._report_entities()
    reader.register("FunctionalSafetyMonitor:runtime", fast, 60)
    reader.register("FunctionalSafetyMonitor:maintenance", maintenance, 3600)
    reports = {
        "sensor.battery": snapshot("5", unit="%", kind="battery"),
        "update.core": snapshot("on"),
    }
    provider.poll.side_effect = lambda entities, **_: {
        entity: reports[entity] for entity in entities if entity in reports
    }
    reader.tick()
    jobs.pop()()
    monitor.evaluate()
    assert (
        monitor._maintenance_diagnostics["remote_batteries"]["Remote"]["status"]
        == "low"
    )
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.SET
    event_count = len(bus.events)

    reports["sensor.battery"] = snapshot("90", unit="%", kind="battery")
    reports["update.core"] = snapshot("off")
    clock[0] += 60
    reader.tick()
    jobs.pop()()
    monitor.evaluate()
    assert (
        monitor._maintenance_diagnostics["remote_batteries"]["Remote"]["status"]
        == "low"
    )
    assert len(bus.events) == event_count

    clock[0] = 3700
    provider.poll.side_effect = OSError("offline")
    reader.tick()
    jobs.pop()()
    monitor.evaluate()
    assert (
        monitor._maintenance_diagnostics["remote_batteries"]["Remote"]["status"]
        == "unknown"
    )
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.SET
    assert len(bus.events) == event_count
    clock[0] += 3600
    provider.poll.side_effect = lambda entities, **_: {
        entity: reports[entity] for entity in entities if entity in reports
    }
    reader.tick()
    jobs.pop()()
    monitor.evaluate()
    assert monitor.symptom_states["fsm_RemoteBatteryLowRemote"] == FaultState.CLEARED


@pytest.mark.parametrize("elapsed", [119, 120])
def test_ordinary_read_accepts_response_within_two_minutes(scheduled_reader, elapsed):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("temperature", {"sensor.temperature"}, 120)
    row = snapshot("21.21")
    provider.poll.return_value = {"sensor.temperature": row}
    reader.tick()
    clock[0] += elapsed
    jobs.pop()()
    assert reader.report("temperature", "sensor.temperature") == row
    provider.poll.assert_called_once_with({"sensor.temperature"}, timeout_seconds=120)


def test_temperature_poll_and_delayed_response_do_not_expire_healthy_cache(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("temperature", {"sensor.temperature"}, 120)
    row = snapshot("21.21")
    provider.poll.return_value = {"sensor.temperature": row}
    reader.tick()
    jobs.pop()()
    clock[0] += 119
    reader.tick()
    assert not jobs
    clock[0] += 6  # A five-second scheduling delay at the next acquisition.
    reader.tick()
    clock[0] += 119
    assert reader.report("temperature", "sensor.temperature") == row
    jobs.pop()()
    assert reader.report("temperature", "sensor.temperature") == row
    assert reader.revision("temperature") == 2


def test_slow_request_cannot_block_fast_reconciliation(scheduled_reader):
    reader, provider, clock, jobs = scheduled_reader
    reader.register("temperature", {"sensor.temperature"}, 120)
    reader.register("fast", {"binary_sensor.window"}, 5)
    provider.poll.return_value = {
        "sensor.temperature": snapshot("21.21"),
        "binary_sensor.window": snapshot("on"),
    }
    reader.tick()
    assert len(jobs) == 2
    slow_job, fast_job = jobs
    jobs.clear()
    fast_job()
    clock[0] += 5
    reader.tick()
    assert len(jobs) == 1
    jobs.pop()()
    assert reader.revision("fast") == 2
    assert reader.report("fast", "binary_sensor.window")["state"] == "on"
    assert reader.revision("temperature") == 0
    clock[0] += 116
    slow_job()
    assert reader.report("temperature", "sensor.temperature") is None
    assert provider.poll.call_args.kwargs["timeout_seconds"] == 120
