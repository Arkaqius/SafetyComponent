"""Tests for MQTT discovery and state publishing."""

import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from components.core.mqtt_entity_manager import MqttEntityManager


def _mqtt_calls(hass_app, topic):
    return [
        call
        for call in hass_app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs["topic"] == topic
    ]


def test_register_sensor_publishes_discovery_state_and_attributes():
    hass_app = Mock()
    mqtt_entities = MqttEntityManager(hass_app)

    mqtt_entities.register_sensor(
        "sensor.safety_app_health",
        "Safety App Health",
        state="running",
        attributes={"mode": "test"},
        icon="mdi:heart-pulse",
    )

    discovery_call = _mqtt_calls(
        hass_app,
        "homeassistant/sensor/safety_component_safety_app_health/config",
    )[-1]
    discovery_payload = json.loads(discovery_call.kwargs["payload"])

    assert discovery_call.kwargs["retain"] is True
    assert discovery_payload["state_topic"] == "safety_component/state/safety_app_health"
    assert (
        discovery_payload["json_attributes_topic"]
        == "safety_component/attributes/safety_app_health"
    )
    assert discovery_payload["unique_id"] == "safety_component_safety_app_health"
    assert discovery_payload["default_entity_id"] == "sensor.safety_app_health"
    assert discovery_payload["expire_after"] == 180
    assert discovery_payload["origin"]["name"] == "SafetyComponent"

    state_call = _mqtt_calls(
        hass_app, "safety_component/state/safety_app_health"
    )[-1]
    assert state_call.kwargs["payload"] == "running"
    assert state_call.kwargs["retain"] is False
    attributes_payload = json.loads(
        _mqtt_calls(hass_app, "safety_component/attributes/safety_app_health")[
            -1
        ].kwargs["payload"]
    )
    assert attributes_payload == {"mode": "test", "state_label": "Running"}


def test_localization_keeps_state_code_and_localizes_display_metadata():
    hass_app = Mock()
    mqtt_entities = MqttEntityManager(
        hass_app,
        localization={
            "language": "pl",
            "entity_names": {
                "sensor.safety_app_health": "Kondycja systemu",
            },
        },
    )

    mqtt_entities.register_sensor(
        "sensor.safety_app_health",
        "Safety App Health",
        state="running",
    )

    discovery_payload = json.loads(
        _mqtt_calls(
            hass_app,
            "homeassistant/sensor/safety_component_safety_app_health/config",
        )[-1].kwargs["payload"]
    )
    attributes_payload = json.loads(
        _mqtt_calls(
            hass_app,
            "safety_component/attributes/safety_app_health",
        )[-1].kwargs["payload"]
    )
    state_payload = _mqtt_calls(
        hass_app,
        "safety_component/state/safety_app_health",
    )[-1].kwargs["payload"]

    assert discovery_payload["name"] == "Kondycja systemu"
    assert state_payload == "running"
    assert attributes_payload["state_label"] == "Działa"

    mqtt_entities.publish_sensor_state(
        "sensor.safety_app_health",
        "stopped",
    )

    updated_attributes_payload = json.loads(
        _mqtt_calls(
            hass_app,
            "safety_component/attributes/safety_app_health",
        )[-1].kwargs["payload"]
    )
    assert updated_attributes_payload["state_label"] == "Zatrzymana"


def test_availability_cleanup_and_remove_sensor():
    hass_app = Mock()
    mqtt_entities = MqttEntityManager(
        hass_app,
        {
            "legacy_discovery_entity_ids": ["sensor.safety_app_health"]
        },
    )

    mqtt_entities.cleanup_legacy_discovery_topics()
    mqtt_entities.publish_availability(True)
    mqtt_entities.register_sensor("sensor.test", "Test", state="ok")
    mqtt_entities.remove_sensor("sensor.test", remove_legacy_topic=True)

    availability_call = _mqtt_calls(hass_app, "safety_component/status")[-1]
    assert availability_call.kwargs["payload"] == "online"
    assert availability_call.kwargs["retain"] is True

    legacy_health_call = _mqtt_calls(
        hass_app, "homeassistant/sensor/safety_app_health/config"
    )[0]
    assert legacy_health_call.kwargs["payload"] == ""
    assert legacy_health_call.kwargs["retain"] is True

    for topic in (
        "homeassistant/sensor/safety_component_test/config",
        "homeassistant/sensor/test/config",
        "safety_component/state/test",
        "safety_component/attributes/test",
    ):
        cleanup_call = _mqtt_calls(hass_app, topic)[-1]
        assert cleanup_call.kwargs["payload"] == ""
        assert cleanup_call.kwargs["retain"] is True


def test_entity_ids_are_canonical_and_none_is_an_explicit_unknown_state():
    hass_app = Mock()
    mqtt_entities = MqttEntityManager(hass_app)

    canonical_id = mqtt_entities.register_sensor(
        "sensor.Fault_RiskyTemperature",
        "Risky temperature",
        state=None,
    )

    assert canonical_id == "sensor.fault_riskytemperature"
    assert (
        _mqtt_calls(
            hass_app,
            "safety_component/state/fault_riskytemperature",
        )[-1].kwargs["payload"]
        == "None"
    )
    discovery_call = _mqtt_calls(
        hass_app,
        "homeassistant/sensor/"
        "safety_component_fault_riskytemperature/config",
    )[-1]
    discovery_payload = json.loads(discovery_call.kwargs["payload"])
    assert (
        discovery_payload["default_entity_id"]
        == "sensor.fault_riskytemperature"
    )


@pytest.mark.parametrize(
    "mqtt_config",
    [
        {"qos": 3},
        {"retain_discovery": False},
        {"base_topic": "unsafe/#"},
        {"retain_state": "false"},
        {"device_identifier": "Unsafe Identifier"},
        {"heartbeat_seconds": 0, "expire_after": 60},
        {"heartbeat_seconds": 60, "expire_after": 60},
        {"legacy_discovery_entity_ids": ["light.not_a_sensor"]},
    ],
)
def test_invalid_mqtt_settings_are_rejected(mqtt_config):
    with pytest.raises((ValidationError, ValueError)):
        MqttEntityManager(Mock(), mqtt_config)


def test_heartbeat_republishes_cached_states_without_retaining_them():
    hass_app = Mock()
    mqtt_entities = MqttEntityManager(hass_app)
    mqtt_entities.register_sensor(
        "sensor.health",
        "Health",
        state="running",
        attributes={"configuration": {"version": 1}},
    )

    hass_app.call_service.reset_mock()
    mqtt_entities.publish_heartbeat()

    state_call = _mqtt_calls(hass_app, "safety_component/state/health")[-1]
    assert state_call.kwargs["payload"] == "running"
    assert state_call.kwargs["retain"] is False
    attributes_call = _mqtt_calls(
        hass_app, "safety_component/attributes/health"
    )[-1]
    assert json.loads(attributes_call.kwargs["payload"]) == {
        "configuration": {"version": 1}
    }
    assert attributes_call.kwargs["retain"] is False


def test_failed_mqtt_publish_response_is_rejected():
    hass_app = Mock(
        call_service=Mock(
            return_value={"success": False, "error": "broker unavailable"}
        )
    )
    mqtt_entities = MqttEntityManager(hass_app)

    with pytest.raises(RuntimeError, match="MQTT publish failed"):
        mqtt_entities.publish_availability()
