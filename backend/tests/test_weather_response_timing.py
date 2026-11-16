"""Usable-input to HA response budget with real policy, fault and delivery owners."""

from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.core.snapshot_writer import SnapshotWriter
from components.core.types_common import Fault, FaultState, Symptom
from components.external_apis.core.api_runtime import ExternalApiRuntime
from components.external_apis.core.models import ApiResult, HazardType, Measurement, WarningUrgency
from components.faults_manager.fault_manager import FaultManager
from components.notification_manager.mobile_push_provider import MobilePushProvider
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.schema import NotificationConfig
from safety_lifecycle_support import CallbackServiceAdapter, ControlledExecutor, FakeMonotonicClock

from .test_external_hazard_component import _component, _health, _observation, _wind_result


CASES = [
    (HazardType.FROST, {"current_temperature": 0, "forecast_min_temperature": -1}),
    (HazardType.WIND, {"current_wind_gust": 22, "forecast_max_wind_gust": 22}),
    (HazardType.RAIN, {"current_precipitation": 3, "current_rain": 3, "forecast_max_precipitation": 4, "forecast_max_rain": 4}),
    (HazardType.STORM, {"current_weather_code": 95}),
]


def pipeline(monkeypatch, hazard, values, kind, source, dispatch=5):
    clock = FakeMonotonicClock()
    monkeypatch.setattr("components.safetycomponents.external_hazard.external_hazard_component.monotonic", clock)
    component, app, mqtt, _ = _component(kind, persistence=75, aq_persistence=300)
    app.run_every = lambda callback, *_args, **_kwargs: callback
    transport = CallbackServiceAdapter()
    app.call_service = transport.call_service
    broker = ServiceDispatcher(app, [ResourceSpec("notify/fixture", Lane.MOBILE, frozenset({"notify/fixture"}))],
                               clock=clock, registry=ProcessLeaseRegistry())
    broker.start()
    config = NotificationConfig.model_validate({"mobile": {"services": ["notify/fixture"]}}).model_dump()
    observer = Mock()
    notify = NotificationManager(app, config, mobile_provider=MobilePushProvider(app, config["mobile"], dispatcher=broker),
                                 snapshot_writer=SnapshotWriter(ControlledExecutor()), clock=clock,
                                 mqtt_entities=mqtt, diagnostics_observer=observer)
    notify.start()
    symptom_id = f"ExternalWeatherExposure{hazard.value.capitalize()}OfficeWindow"
    symptom = Symptom(symptom_id, "sm_ext_weather_exposure", component, {})
    fault = Fault("ExternalWeatherExposure", [symptom.sm_name], 2, related_symptom_ids=(symptom_id,))
    bus = component.event_bus
    faults = FaultManager(app, {}, {symptom_id: symptom}, {fault.name: fault}, bus, mqtt)

    def commit(**payload):
        if payload["symptom_id"] != symptom_id:
            return
        if payload["state"] == FaultState.SET:
            clock.advance(1)  # The separate <=1 s decision allocation.
        faults.handle_symptom_event(**payload)

    bus.subscribe("symptom", commit)
    bus.subscribe("fault", notify.handle_fault_event, isolated=True)
    official = source != "model"
    provider = "ImgwWarningsApiComponent" if official else "OpenMeteoWeatherApiComponent"
    observation = _observation(provider, hazard, {key: Measurement(value) for key, value in values.items()}, confirmed=official)
    if official:
        observation = replace(observation, warning_urgency=WarningUrgency(source))
    result = ApiResult(provider, (observation,), _health(provider))
    runtime = ExternalApiRuntime(app, bus, {provider: SimpleNamespace(data_kind="live")}, clock=clock)
    component.dispatch_continuity_probe = runtime.continuity_state
    future = Future()
    future.set_result(result)
    runtime._poll_completed(provider, future)
    clock.advance(dispatch)
    runtime.drain_results()
    assert not fault.evaluation.active
    assert component._dispatch_timing[provider].delay_seconds == dispatch
    assert runtime.dispatch_overruns == int(dispatch > 5)
    clock.advance(74.999)
    component._evaluate_all()
    assert not fault.evaluation.active
    clock.advance(9.001)  # 75 s qualification plus 9 s reconciliation delay.
    component._evaluate_all()
    assert clock() == pytest.approx(dispatch + 85)
    assert fault.evaluation.active and notify.active_notification
    if clock() < 120:
        assert notify.pending_deliveries
        assert next(iter(broker._pending.values())).intent.deadline_at == pytest.approx(min(clock() + 30, 120))
    broker.tick()
    assert len(transport.calls) == int(clock() < 120)
    runtime.stop()
    return clock, broker, transport, notify, observer


@pytest.mark.parametrize("hazard,values", CASES, ids=["frost", "wind", "rain", "storm"])
@pytest.mark.parametrize("kind", ["window", "door"])
@pytest.mark.parametrize("source", ["model", "standard", "immediate"])
@pytest.mark.parametrize("endpoint", [119, 120, 121])
def test_full_120_second_response_counts_queue_qualification_decision_and_ha(
    monkeypatch, hazard, values, kind, source, endpoint,
) -> None:
    clock, broker, transport, notify, observer = pipeline(monkeypatch, hazard, values, kind, source)
    clock.advance(endpoint - clock())
    transport.complete(0, {"success": True, "result": None})
    broker.tick()
    assert notify._counters["accepted_attempts"] == 1
    assert notify._counters["deadline_misses"] == int(endpoint > 120)
    assert notify.notification_history[-1]["deadline_missed"] is (endpoint > 120)
    if endpoint > 120:
        assert notify._last_error == "deadline_missed"
        assert any(call.args[:2] == ("delivery", True) for call in observer.call_args_list)


@pytest.mark.parametrize("response", [None, {"success": False}, "stalled"])
def test_full_response_reports_failure_without_suppressing_danger(monkeypatch, response) -> None:
    clock, broker, transport, notify, _ = pipeline(monkeypatch, CASES[1][0], CASES[1][1], "door", "model")
    clock.advance(31)
    if response != "stalled":
        transport.complete(0, response)
    broker.tick()
    assert notify.active_notification
    assert notify._counters["accepted_attempts"] == 0
    assert notify._counters["deadline_misses"] == 1
    assert broker.registry.quarantined_count == int(response == "stalled")


def test_dispatch_overrun_cannot_grant_a_fresh_30_seconds_past_total_deadline(monkeypatch) -> None:
    clock, broker, transport, notify, _ = pipeline(monkeypatch, CASES[1][0], CASES[1][1], "door", "model", dispatch=20)
    assert clock() == 105
    assert broker.registry.lease_count == 1
    clock.advance(16)
    transport.complete(0, {"success": True})
    broker.tick()
    assert notify._counters["deadline_misses"] == 1
    assert notify.notification_history[-1]["deadline_missed"]


def test_already_expired_total_budget_reports_unsent_failure_and_retains_hazard(monkeypatch) -> None:
    _, broker, transport, notify, _ = pipeline(monkeypatch, CASES[1][0], CASES[1][1], "window", "model", dispatch=40)
    assert not transport.calls and broker.registry.lease_count == 0
    assert notify.active_notification and not notify.notification_history
    assert notify._counters["deadline_misses"] == 1
    assert notify._counters["accepted_attempts"] == 0


def test_completion_received_within_budget_remains_timely_when_owner_drains_later(monkeypatch) -> None:
    clock, broker, transport, notify, _ = pipeline(monkeypatch, CASES[1][0], CASES[1][1], "window", "model")
    clock.advance(29)
    transport.complete(0, {"success": True})
    clock.advance(2)
    notify.tick()
    broker.tick()
    assert notify._counters["accepted_attempts"] == 1
    assert notify._counters["deadline_misses"] == 0
    assert not notify.notification_history[-1]["deadline_missed"]


@pytest.mark.parametrize("next_provider", ["same", "other"])
def test_dropped_intervening_snapshot_resets_pending_continuity_before_owner_drain(monkeypatch, next_provider) -> None:
    clock = FakeMonotonicClock()
    monkeypatch.setattr("components.safetycomponents.external_hazard.external_hazard_component.monotonic", clock)
    component, app, _, _ = _component(persistence=75)
    positive = _wind_result()
    provider, other = positive.provider, "ImgwWarningsApiComponent"
    runtime = ExternalApiRuntime(app, component.event_bus, {
        provider: SimpleNamespace(data_kind="live"), other: SimpleNamespace(data_kind="live"),
    }, clock=clock, max_queue_size=1)
    component.dispatch_continuity_probe = runtime.continuity_state

    def receive(result):
        future = Future()
        future.set_result(result)
        runtime._poll_completed(result.provider, future)

    try:
        receive(positive)
        runtime.drain_results()
        clock.advance(74)
        receive(replace(positive, observations=()))
        receive(positive if next_provider == "same" else ApiResult(other, (), _health(other)))
        assert runtime.queue_overflows == 1
        clock.advance(1)
        component._evaluate_all()  # A timer can run before the next queue drain.
        symptom = "ExternalWeatherExposureWindOfficeWindow"
        assert component.symptom_states[symptom] != FaultState.SET
        runtime.drain_results()
        if next_provider == "other":
            assert provider in component._continuity_uncertain
            clock.advance(5)
            receive(positive)
            runtime.drain_results()
        start = clock()
        clock.advance(74.999)
        component._evaluate_all()
        assert component.symptom_states[symptom] != FaultState.SET
        clock.advance(start + 75 - clock())
        component._evaluate_all()
        assert component.symptom_states[symptom] == FaultState.SET
    finally:
        runtime.stop()


def test_ordinary_repeated_qualifying_input_does_not_restart_confirmation(monkeypatch) -> None:
    clock = FakeMonotonicClock()
    monkeypatch.setattr("components.safetycomponents.external_hazard.external_hazard_component.monotonic", clock)
    component, app, _, _ = _component(persistence=75)
    positive = _wind_result()
    runtime = ExternalApiRuntime(app, component.event_bus, {positive.provider: SimpleNamespace(data_kind="live")}, clock=clock)
    component.dispatch_continuity_probe = runtime.continuity_state
    try:
        for instant in (0, 74):
            clock.advance(instant - clock())
            future = Future()
            future.set_result(positive)
            runtime._poll_completed(positive.provider, future)
            if instant == 0:
                runtime.drain_results()
        clock.advance(1)
        component._evaluate_all()
        symptom = "ExternalWeatherExposureWindOfficeWindow"
        assert component.symptom_states[symptom] != FaultState.SET
        assert component._model_assertions[(positive.provider, HazardType.WIND)][0] == 0
        runtime.drain_results()
        assert component.symptom_states[symptom] == FaultState.SET
        assert component._last_context[symptom]["response_deadline_monotonic"] == 120
    finally:
        runtime.stop()
