"""Behavior tests for Entity Health Monitoring."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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
                "fault_owner": "entity_monitor",
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


def test_entity_monitor_creates_per_check_symptoms_and_per_entity_fault(
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
    fault = component.get_fault_definitions()["EntityHealthTemperatureOffice"]
    assert fault["level"] == 3
    assert fault["related_sms"] == ["sm_entity_health_temperature_office"]
    runtime = component._entities["TemperatureOffice"]
    attributes = component._diagnostic_attributes(runtime)
    assert attributes["source_entity_id"] == "sensor.office_temperature"


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
            "fault_owner": "entity_monitor",
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
