"""Provider health faults preserve adapter ownership and independent causes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from jinja2 import Environment

from components.core.event_bus import EventBus
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.types_common import FaultState, SMState
from components.external_apis.core.models import ApiResult, ProviderHealth, ProviderHealthState
from components.notification_manager.local_annunciator import LocalAnnunciator
from components.notification_manager.notification_manager import NotificationManager


def _result(provider: str, state: ProviderHealthState) -> ApiResult:
    return ApiResult(
        provider,
        (),
        ProviderHealth(provider, state, None, None, 1 if state != ProviderHealthState.OK else 0),
    )


def test_each_provider_fault_sets_and_clears_only_from_its_own_result() -> None:
    bus = EventBus()
    events: list[tuple[str, FaultState]] = []
    bus.subscribe(
        "symptom",
        lambda *, symptom_id, state, **_: events.append((symptom_id, state)),
    )
    providers = {
        "OpenMeteoWeatherApiComponent": Mock(),
        "ImgwWarningsApiComponent": Mock(),
    }
    diagnostics = SelfDiagnosticsComponent(Mock(), Mock(), bus, Mock(), providers)
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    for symptom in symptoms.values():
        assert diagnostics.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert diagnostics.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    weather = "ProviderHealthOpenMeteoWeather"
    imgw = "ProviderHealthImgwWarnings"
    bus.publish(
        "external_api_result",
        result=_result("OpenMeteoWeatherApiComponent", ProviderHealthState.UNAVAILABLE),
    )
    bus.publish(
        "external_api_result",
        result=_result("OpenMeteoWeatherApiComponent", ProviderHealthState.UNAVAILABLE),
    )
    bus.publish(
        "external_api_result",
        result=_result("ImgwWarningsApiComponent", ProviderHealthState.OK),
    )
    bus.publish(
        "external_api_result",
        result=_result("OpenMeteoWeatherApiComponent", ProviderHealthState.OK),
    )

    assert events == [
        (weather, FaultState.SET),
        (imgw, FaultState.CLEARED),
        (weather, FaultState.CLEARED),
    ]
    assert diagnostics.get_fault_definitions()[
        "ExternalProviderUnavailableOpenMeteoWeather"
    ]["category"] == "D"


def test_unallocated_adapter_is_rejected() -> None:
    with pytest.raises(ValueError, match="explicit fault allocation"):
        SelfDiagnosticsComponent(
            Mock(), Mock(), EventBus(), Mock(), {"UnknownProvider": Mock()}
        )


def test_unconfigured_local_output_has_no_phantom_d_contributor() -> None:
    diagnostics = SelfDiagnosticsComponent(
        Mock(), Mock(), EventBus(), Mock(), {}, local_outputs_enabled=False
    )
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    assert "AppHealthLocalOutput" not in symptoms
    assert "AppHealthLocalOutput" not in diagnostics.get_fault_definitions()[
        "SafetyAppHealth"
    ]["related_symptom_ids"]


def test_app_health_persistence_causes_clear_independently() -> None:
    bus = EventBus()
    events: list[tuple[str, FaultState]] = []
    bus.subscribe(
        "symptom",
        lambda *, symptom_id, state, **_: events.append((symptom_id, state)),
    )
    diagnostics = SelfDiagnosticsComponent(Mock(), Mock(), bus, Mock(), {})
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    for symptom_id in (
        "AppHealthPersistenceNotificationState",
        "AppHealthPersistenceRecoveryState",
    ):
        symptom = symptoms[symptom_id]
        diagnostics.init_safety_mechanism(symptom.sm_name, symptom.name, symptom.parameters)
        diagnostics.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    diagnostics.record_app_cause("persistence", True, detail="notification_state")
    diagnostics.record_app_cause("persistence", True, detail="recovery_state")
    diagnostics.record_app_cause("persistence", False, detail="notification_state")
    assert events == [
        ("AppHealthPersistenceNotificationState", FaultState.SET),
        ("AppHealthPersistenceRecoveryState", FaultState.SET),
        ("AppHealthPersistenceNotificationState", FaultState.CLEARED),
    ]
    diagnostics.record_app_cause("persistence", False, detail="recovery_state")
    assert events[-1] == ("AppHealthPersistenceRecoveryState", FaultState.CLEARED)


def test_successful_save_cannot_clear_failed_restore() -> None:
    bus = EventBus()
    events: list[FaultState] = []
    bus.subscribe(
        "symptom",
        lambda *, symptom_id, state, **_: (
            events.append(state)
            if symptom_id == "AppHealthPersistenceNotificationState"
            else None
        ),
    )
    diagnostics = SelfDiagnosticsComponent(Mock(), Mock(), bus, Mock(), {})
    symptoms, _ = diagnostics.get_symptoms_data({}, {})
    symptom = symptoms["AppHealthPersistenceNotificationState"]
    diagnostics.init_safety_mechanism(symptom.sm_name, symptom.name, symptom.parameters)
    diagnostics.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    diagnostics.record_app_cause(
        "persistence", True, detail="notification_state", operation="load"
    )
    diagnostics.record_app_cause(
        "persistence", False, detail="notification_state", operation="save"
    )
    assert events == [FaultState.SET]
    diagnostics.record_app_cause(
        "persistence", False, detail="notification_state", operation="load"
    )
    assert events == [FaultState.SET, FaultState.CLEARED]


def test_local_output_reports_actual_failure_but_not_inhibition() -> None:
    app = Mock()
    observed: list[tuple[str, bool, str]] = []
    output = LocalAnnunciator(
        app, {"light_entity": "light.warning"},
        diagnostics_observer=lambda cause, failed, *, detail: observed.append(
            (cause, failed, detail)
        ),
    )
    output.inhibit_switching("gas_switching_prohibition")
    output.activate(2, "gas")
    assert observed == []
    app.call_service.assert_not_called()

    output = LocalAnnunciator(
        app, {"light_entity": "light.warning"},
        diagnostics_observer=lambda cause, failed, *, detail: observed.append(
            (cause, failed, detail)
        ),
    )
    app.call_service.return_value = {"success": False}
    with pytest.raises(RuntimeError, match="Local output command rejected"):
        output.activate(2, "temperature")
    assert observed == [("local_output", True, "light/turn_on")]


def test_delivery_history_counter_is_not_current_failure() -> None:
    app = Mock()
    mqtt = Mock()
    observed: list[tuple[str, bool]] = []
    manager = NotificationManager(
        app, {}, mqtt_entities=mqtt,
        diagnostics_observer=lambda cause, failed, **_: observed.append(
            (cause, failed)
        ),
    )
    manager._counters["failed_attempts"] = 9
    manager._last_result = "accepted_by_home_assistant"
    manager._publish_diagnostics()
    assert observed[-1] == ("delivery", False)
    manager._last_result = "failed_exhausted"
    manager._channel_status[manager.mobile_provider.services[0]]["status"] = "failed"
    manager._publish_diagnostics()
    assert observed[-1] == ("delivery", True)


def test_targeted_app_health_causes_do_not_fan_out() -> None:
    bus = EventBus()
    events: list[tuple[str, FaultState]] = []
    bus.subscribe(
        "symptom",
        lambda *, symptom_id, state, **_: events.append((symptom_id, state)),
    )
    diagnostics = SelfDiagnosticsComponent(Mock(), Mock(), bus, Mock(), {})
    diagnostics.get_symptoms_data({}, {})
    targets = diagnostics.add_targeted_causes({"room_a", "room_b"}, {"room_a"})
    for symptom in targets.values():
        diagnostics.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        diagnostics.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    bus.publish("evaluation_exception", symptom_id="room_a")
    diagnostics.record_recovery("room_a", True)
    assert events == [
        ("AppHealthEvaluation_room_a", FaultState.SET),
        ("AppHealthRecovery_room_a", FaultState.SET),
    ]


def test_external_supervisor_example_uses_independent_non_actuating_alert() -> None:
    source = (
        Path(__file__).parents[1]
        / "config"
        / "ha_supervisor_automation.example.yml"
    )
    automations = yaml.safe_load(source.read_text(encoding="utf-8"))
    assert len(automations) == 1
    automation = automations[0]
    assert automation["triggers"] == [
        {"trigger": "homeassistant", "event": "start"},
        {"trigger": "time_pattern", "minutes": "/1"},
    ]
    actions = automation["actions"][0]
    assert actions["choose"][0]["sequence"][0]["action"] == (
        "persistent_notification.create"
    )
    assert actions["default"][0]["action"] == "persistent_notification.dismiss"
    template = Environment().from_string(
        actions["choose"][0]["conditions"][0]["value_template"]
    )
    for state in ("unknown", "unavailable", "stopped", "invalid_cfg"):
        assert template.render(states=lambda _, state=state: state).strip() == "True"
    assert template.render(states=lambda _: "running").strip() == "False"
