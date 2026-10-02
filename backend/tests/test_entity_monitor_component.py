"""Behavior tests for Entity Health Monitoring."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import FaultState, SMState
from components.safetycomponents.entity_monitor.entity_monitor_component import (
    EntityMonitorComponent,
)


def _config(entity_id: str = "sensor.office_temperature") -> dict:
    return {
        "startup_grace_seconds": 0,
        "default_failure_debounce_seconds": 10,
        "default_recovery_debounce_seconds": 10,
        "evaluation_interval_seconds": 5,
        "unhealthy_summary_limit": 32,
        "explicit_entities": [],
        "component_entities": [
            {
                "key": "TemperatureOffice",
                "entity_id": entity_id,
                "owner": "TemperatureComponent",
                "purpose": "Temperature input for Office",
                "source": "component",
                "fault_owner": "component",
                "fault_name": "TemperatureMonitoringUnavailable",
                "failure_debounce_seconds": 10,
                "recovery_debounce_seconds": 10,
                "area_id": "office",
                "area_name": "Biuro",
                "checks": {
                    "freshness": {
                        "timestamp_source": "last_updated",
                        "max_silence_seconds": 60,
                    },
                    "finite_number": {"target": "state"},
                },
            }
        ],
    }


def _snapshot(state: str, timestamp: datetime) -> dict:
    return {
        "state": state,
        "attributes": {"friendly_name": "Temperatura biura"},
        "last_changed": timestamp.isoformat(),
        "last_updated": timestamp.isoformat(),
    }


def _component(mocked_hass_app_basic):
    app, _, _ = mocked_hass_app_basic
    event_bus = EventBus()
    component = EntityMonitorComponent(
        app,
        CommonEntities(app, {"outside_temp": "sensor.outside_temperature"}),
        event_bus,
        MqttEntityManager(app),
    )
    return app, event_bus, component


def _mqtt_topic_calls(app, topic: str) -> list:
    return [
        call
        for call in app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs["topic"] == topic
    ]


def test_entity_monitor_routes_checks_to_component_fault(
    mocked_hass_app_basic,
):
    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    app.get_state = MagicMock(return_value=_snapshot("21.5", now))

    symptoms, recoveries = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, _config()
    )

    assert recoveries == {}
    assert set(symptoms) == {
        "EntityHealthFailureTemperatureOfficeAvailability",
        "EntityHealthFailureTemperatureOfficeFreshness",
        "EntityHealthFailureTemperatureOfficeFiniteNumber",
    }
    fault = component.get_fault_definitions()["TemperatureMonitoringUnavailable"]
    assert fault["level"] == 3
    assert fault["related_sms"] == ["sm_entity_health_temperature_office"]
    runtime = component._entities["TemperatureOffice"]
    attributes = component._diagnostic_attributes(runtime)
    assert attributes["source_entity_id"] == "sensor.office_temperature"


def test_entity_monitor_compiles_declared_group_b_and_external_only_group_a(
    mocked_hass_app_basic,
):
    app, _, component = _component(mocked_hass_app_basic)
    app.get_state = MagicMock(return_value=None)
    config = _config()
    config["component_entities"][0]["degradation_targets"] = (
        ("RiskyTemperatureOffice", "temperature_evaluation", "Office", "evaluation"),
    )
    config["explicit_entities"] = [{
        "key": "ExternalFan",
        "entity_id": "binary_sensor.external_fan",
        "owner": "EntityMonitorComponent",
        "purpose": "External automation",
        "source": "explicit",
        "failure_debounce_seconds": 10,
        "recovery_debounce_seconds": 10,
        "checks": {},
    }]
    component.get_symptoms_data({"EntityMonitorComponent": component}, config)

    bindings = component.get_degradation_bindings()
    room = [item for item in bindings if "TemperatureOffice" in item.symptom_id]
    external = [item for item in bindings if "ExternalFan" in item.symptom_id]
    assert len(room) == 3
    assert all(item.targets[0].symptom_id == "RiskyTemperatureOffice" for item in room)
    assert all(not item.external_only for item in room)
    assert len(external) == 1
    assert external[0].targets == ()
    assert external[0].external_only


def test_entity_monitor_debounces_failure_and_recovery(mocked_hass_app_basic):
    app, event_bus, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    clock = {"now": now}
    component._now = lambda: clock["now"]  # type: ignore[method-assign]
    app.get_state = MagicMock(return_value=_snapshot("unavailable", now))
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **event: events.append(event))
    symptoms, _ = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, _config()
    )
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    component._evaluate_entity("TemperatureOffice")
    assert events == []
    assert component._entities["TemperatureOffice"].checks["availability"].result == "pending_failure"

    clock["now"] += timedelta(seconds=11)
    component._evaluate_entity("TemperatureOffice")
    assert events[-1]["state"] == FaultState.SET
    assert events[-1]["symptom_id"].endswith("Availability")

    app.get_state = MagicMock(return_value=_snapshot("21.5", clock["now"]))
    component._evaluate_entity("TemperatureOffice")
    assert events[-1]["state"] == FaultState.SET
    clock["now"] += timedelta(seconds=11)
    app.get_state = MagicMock(return_value=_snapshot("21.5", clock["now"]))
    component._evaluate_entity("TemperatureOffice")
    assert any(
        event["state"] == FaultState.CLEARED
        and event["symptom_id"].endswith("Availability")
        for event in events
    )
    runtime = component._entities["TemperatureOffice"]
    assert runtime.last_valid_value == "21.5"
    assert runtime.last_valid_at == clock["now"]


def test_generated_rate_waits_for_second_sample_before_failure(
    mocked_hass_app_basic,
):
    app, event_bus, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    clock = {"now": now}
    component._now = lambda: clock["now"]  # type: ignore[method-assign]
    app.get_state = MagicMock(return_value=_snapshot("unknown", now))
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **event: events.append(event))

    config = _config("sensor.office_temperature_rate")
    config["component_entities"][0].update(
        key="TemperatureForecastOffice",
        failure_debounce_seconds=960,
        detection_budget_seconds=960,
        checks={"finite_number": {"target": "state"}},
    )
    symptoms, _ = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, config
    )
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    component._evaluate_entity("TemperatureForecastOffice")
    clock["now"] += timedelta(seconds=959)
    component._evaluate_entity("TemperatureForecastOffice")
    assert events == []
    assert (
        component._entities["TemperatureForecastOffice"]
        .checks["availability"]
        .result
        == "pending_failure"
    )

    clock["now"] += timedelta(seconds=1)
    component._evaluate_entity("TemperatureForecastOffice")
    assert len(events) == 1
    assert events[0]["state"] == FaultState.SET
    assert events[0]["symptom_id"].endswith("Availability")


def test_entity_monitor_recovery_dry_run_has_no_runtime_side_effects(
    mocked_hass_app_basic,
):
    app, event_bus, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    component._now = lambda: now  # type: ignore[method-assign]
    app.get_state = MagicMock(return_value=_snapshot("21.5", now))
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **event: events.append(event))
    symptoms, _ = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, _config()
    )
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    availability = component.safety_mechanisms[
        "EntityHealthFailureTemperatureOfficeAvailability"
    ]
    runtime = component._entities["TemperatureOffice"]
    runtime_before = (
        runtime.snapshot,
        runtime.last_valid_value,
        runtime.last_valid_at,
        dict(runtime.samples),
    )
    mqtt_calls_before = list(app.call_service.call_args_list)

    assert (
        component._evaluate_mechanism(
            availability,
            {"sensor.office_temperature": "unavailable"},
        )
        is True
    )
    finite_number = component.safety_mechanisms[
        "EntityHealthFailureTemperatureOfficeFiniteNumber"
    ]
    assert (
        component._evaluate_mechanism(
            finite_number,
            {"sensor.office_temperature": "nan"},
        )
        is True
    )

    assert (
        runtime.snapshot,
        runtime.last_valid_value,
        runtime.last_valid_at,
        runtime.samples,
    ) == runtime_before
    assert app.call_service.call_args_list == mqtt_calls_before
    assert events == []


def test_entity_monitor_publishes_stable_diagnostics_only_on_change(
    mocked_hass_app_basic,
):
    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    clock = {"now": now}
    component._now = lambda: clock["now"]  # type: ignore[method-assign]
    app.get_state = MagicMock(return_value=_snapshot("21.5", now))
    symptoms, _ = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, _config()
    )
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)

    topic = "safety_component/attributes/entity_health_temperature_office"
    component._evaluate_entity("TemperatureOffice")
    first_publish_count = len(_mqtt_topic_calls(app, topic))

    clock["now"] += timedelta(seconds=5)
    component._evaluate_entity("TemperatureOffice")

    assert len(_mqtt_topic_calls(app, topic)) == first_publish_count
    assert component._entities["TemperatureOffice"].last_valid_at == now

    app.get_state = MagicMock(return_value=_snapshot("22.0", clock["now"]))
    component._evaluate_entity("TemperatureOffice")
    source_change_publish_count = len(_mqtt_topic_calls(app, topic))

    assert source_change_publish_count == first_publish_count + 1

    clock["now"] += timedelta(seconds=61)
    component._evaluate_entity("TemperatureOffice")

    assert len(_mqtt_topic_calls(app, topic)) == source_change_publish_count + 1
    assert (
        component._entities["TemperatureOffice"].checks["freshness"].result
        == "pending_failure"
    )


def test_entity_monitor_merges_memberships_for_same_entity(mocked_hass_app_basic):
    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    app.get_state = MagicMock(return_value=_snapshot("off", now))
    config = _config("binary_sensor.office_window")
    config["component_entities"].append(
        {
            "key": "ExternalOpeningOffice",
            "entity_id": "binary_sensor.office_window",
            "owner": "ExternalHazardComponent",
            "purpose": "Opening input",
            "source": "component",
            "fault_owner": "component",
            "fault_name": "ExternalOpeningMonitoringUnavailable",
            "failure_debounce_seconds": 10,
            "recovery_debounce_seconds": 10,
            "checks": config["component_entities"][0]["checks"],
        }
    )

    component.get_symptoms_data({"EntityMonitorComponent": component}, config)

    assert len(component._entities) == 1
    dependency = component._entities["TemperatureOffice"].dependency
    assert dependency.owners == (
        "TemperatureComponent",
        "ExternalHazardComponent",
    )
    assert dependency.consumer_keys == (
        "TemperatureOffice",
        "ExternalOpeningOffice",
    )
    assert dependency.fault_name == "CommonInputUnavailable"
    assert set(component.get_fault_definitions()) == {"CommonInputUnavailable"}


def test_multiple_component_inputs_aggregate_into_one_diagnostic_fault(
    mocked_hass_app_basic,
):
    """Inputs in different rooms share one fault but retain distinct contributors."""

    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    app.get_state = MagicMock(return_value=_snapshot("21.5", now))
    config = _config()
    second = dict(config["component_entities"][0])
    second.update(
        key="TemperatureKitchen",
        entity_id="sensor.kitchen_temperature",
        purpose="Temperature input for Kitchen",
    )
    config["component_entities"].append(second)

    symptoms, _ = component.get_symptoms_data(
        {"EntityMonitorComponent": component}, config
    )

    assert len(component._entities) == 2
    assert set(component.get_fault_definitions()) == {
        "TemperatureMonitoringUnavailable"
    }
    assert set(
        component.get_fault_definitions()["TemperatureMonitoringUnavailable"][
            "related_sms"
        ]
    ) == {
        "sm_entity_health_temperature_office",
        "sm_entity_health_temperature_kitchen",
    }
    assert len(symptoms) == 6


def test_missing_declared_component_fault_binding_is_rejected(
    mocked_hass_app_basic,
):
    app, _, component = _component(mocked_hass_app_basic)
    app.get_state = MagicMock(return_value=None)
    config = _config()
    config["component_entities"][0].pop("fault_name")

    with pytest.raises(ValueError, match="Missing component fault binding"):
        component.get_symptoms_data({"EntityMonitorComponent": component}, config)


def test_explicit_dependency_controls_stable_key_for_merged_entity(
    mocked_hass_app_basic,
):
    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    app.get_state = MagicMock(return_value=_snapshot("on", now))
    config = _config("binary_sensor.upper_bathroom_window")
    config["explicit_entities"] = [
        {
            "key": "ExternalOpeningUpperBathroomWindow",
            "entity_id": "binary_sensor.upper_bathroom_window",
            "owner": "installation",
            "purpose": "Upper bathroom window contact",
            "source": "explicit",
            "fault_owner": "entity_monitor",
            "failure_debounce_seconds": 10,
            "recovery_debounce_seconds": 10,
            "checks": {},
        }
    ]

    component.get_symptoms_data({"EntityMonitorComponent": component}, config)

    assert set(component._entities) == {"ExternalOpeningUpperBathroomWindow"}
    assert set(component.get_fault_definitions()) == {
        "TemperatureMonitoringUnavailable"
    }


def test_freshness_fault_context_formats_age_as_duration(mocked_hass_app_basic):
    app, _, component = _component(mocked_hass_app_basic)
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    app.get_state = MagicMock(return_value=_snapshot("21.5", now))
    component.get_symptoms_data({"EntityMonitorComponent": component}, _config())
    runtime = component._entities["TemperatureOffice"]
    state = runtime.checks["freshness"]
    state.reason = "freshness_expired"
    state.observed_value = 7222.761

    context = component._symptom_context(runtime, "freshness", state)

    assert context["freshness_age"] == "2 h 0 min 23 s"
    assert "observed_value" not in context
