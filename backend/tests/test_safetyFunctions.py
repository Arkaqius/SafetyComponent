from copy import deepcopy
from unittest.mock import Mock

from components.core.types_common import FaultState

from .fixtures.hass_fixture import (
    mqtt_json_payloads,
    mqtt_payloads,
    mqtt_topic_for,
)

def test_safety_functions_initialization(mocked_hass_app_with_temp_component) -> None:

    app_instance, mocked_hass, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.initialize()

    # Assert the 'symptoms' dictionary content
    symptom = app_instance.symptoms["RiskyTemperatureOffice"]
    assert symptom.name == "RiskyTemperatureOffice"
    assert symptom.sm_name == "sm_tc_1"
    assert symptom.parameters["CAL_LOW_TEMP_THRESHOLD"] == 18.0

    # Assert the 'faults' dictionary content
    fault = app_instance.fault_dict["RiskyTemperature"]
    assert fault["name"] == "Unsafe temperature"
    assert fault["level"] == 2
    assert fault["related_sms"][0] == "sm_tc_1"

    # Assert the 'notification_cfg' dictionary content
    notification = app_instance.notification_cfg
    assert notification["local"]["light_entity"] == "light.warning_light"

    # Ensure that the correct common entity was used
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"

    # Verify that safety mechanisms are initialized and enabled via MQTT state.
    health_topic = mqtt_topic_for("sensor.safety_app_health")
    health_payloads = mqtt_payloads(mocked_hass, health_topic)
    assert "init" in health_payloads
    assert "running" in health_payloads
    assert mqtt_payloads(mocked_hass, "safety_component/status") == [
        "offline",
        "online",
    ]
    assert {
        "sensor.safetysystem_state",
        "sensor.fault_riskytemperature",
        "sensor.fault_riskytemperatureforecast",
        "sensor.recovery_manipulatewindowoffice",
        "sensor.office_temperature_low_threshold",
        "sensor.office_temperature_high_threshold",
    }.issubset(app_instance.mqtt_entities.discovered_entities)
    assert mqtt_payloads(
        mocked_hass,
        mqtt_topic_for("sensor.office_temperature_low_threshold"),
    )[-1] == "18.0"
    threshold_attributes = mqtt_json_payloads(
        mocked_hass,
        mqtt_topic_for("sensor.office_temperature_low_threshold", "attributes"),
    )[-1]
    assert threshold_attributes == {
        "area_id": "office",
        "area_name": "Office",
        "attribution": "Managed by SafetyFunction",
        "source_entity": "sensor.office_temperature",
        "threshold_type": "low",
    }


def test_entity_monitor_is_wired_into_application_startup(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.args = deepcopy(app_instance.args)
    app_instance.args["app_config"].setdefault("calibration", {})[
        "entity_monitor"
    ] = {
        "startup_grace_seconds": 0,
        "default_failure_debounce_seconds": 15,
        "default_recovery_debounce_seconds": 60,
        "evaluation_interval_seconds": 5,
        "unhealthy_summary_limit": 32,
    }
    app_instance.args["user_config"]["components_enabled"][
        "EntityMonitorComponent"
    ] = True
    app_instance.args["user_config"]["safety_components"][
        "EntityMonitorComponent"
    ] = {"explicit_entities": {}}

    app_instance.initialize()

    assert "EntityMonitorComponent" in app_instance.sm_modules
    assert "sensor.entity_monitor_summary" in app_instance.mqtt_entities.discovered_entities
    assert "EntityHealthTemperatureOffice" in app_instance.faults
    assert (
        "EntityHealthFailureTemperatureOfficeAvailability" in app_instance.symptoms
    )


def test_entity_monitor_rejects_component_timing_outside_detection_budget(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.args = deepcopy(app_instance.args)
    app_instance.args["app_config"].setdefault("calibration", {})[
        "entity_monitor"
    ] = {"default_failure_debounce_seconds": 31}
    app_instance.args["user_config"]["components_enabled"][
        "EntityMonitorComponent"
    ] = True
    app_instance.args["user_config"]["safety_components"][
        "EntityMonitorComponent"
    ] = {"explicit_entities": {}}

    app_instance.initialize()

    assert mqtt_payloads(
        mocked_hass, mqtt_topic_for("sensor.safety_app_health")
    )[-1] == "invalid_cfg"
    assert "EntityMonitorComponent" not in app_instance.sm_modules


def test_mqtt_heartbeat_accepts_appdaemon_dictionary_unpacking_callback(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    app_instance.mqtt_entities.publish_heartbeat = Mock()

    app_instance._mqtt_heartbeat()
    app_instance._mqtt_heartbeat(timer="heartbeat")

    assert app_instance.mqtt_entities.publish_heartbeat.call_count == 2

    # Verify TemperatureComponent configurations are set up correctly
    assert "TemperatureComponent" in app_instance.sm_modules

    # Verify that TemperatureComponent received the correct configuration
    temp_comp_cfg = app_instance.safety_components_cfg["TemperatureComponent"]

    office_cfg = next(cfg["Office"] for cfg in temp_comp_cfg if "Office" in cfg)
    assert office_cfg["temperature_sensor"] == "sensor.office_temperature"
    assert office_cfg["window_sensor"] == "sensor.office_window_contact_contact"

    kitchen_cfg = next(cfg["Kitchen"] for cfg in temp_comp_cfg if "Kitchen" in cfg)
    assert kitchen_cfg["temperature_sensor"] == "sensor.kitchen_temperature"
    assert kitchen_cfg["window_sensor"] == "sensor.kitchen_window_contact_contact"

    # Verify the NotificationManager is initialized with the correct entity
    assert (
        app_instance.notify_man.notification_config["local"]["light_entity"]
        == "light.warning_light"
    )

    # Verify that common entities are properly initialized in CommonEntities
    assert "outside_temp" in app_instance.common_entities_cfg
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"


def test_fault_and_symptom_registration(mocked_hass_app_with_temp_component):
    """Ensure all configured faults and symptoms are correctly registered in FaultManager."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Assert that all symptoms are registered
    for symptom_name in app_instance.symptoms:
        assert app_instance.fm.check_symptom(symptom_name) == FaultState.NOT_TESTED

    # Assert that all faults are registered
    for fault_name in app_instance.faults:
        fault = app_instance.faults[fault_name]
        assert fault.name is not None
        assert fault.level >= 0


def test_trigger_symptom_sets_fault(mocked_hass_app_with_temp_component):
    """Test triggering a symptom results in fault state being set."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Manually trigger a symptom
    app_instance.fm.set_symptom("RiskyTemperatureOffice", None)

    # Check if the corresponding fault is set to 'SET'
    assert app_instance.fm.check_fault("RiskyTemperature") == FaultState.SET


def test_recovery_process_execution(mocked_hass_app_with_temp_component):
    """Test that recovery actions are executed when faults are triggered."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Mock the recovery action to track if it's called
    app_instance.reco_man.recovery = Mock()

    # Manually trigger a symptom
    app_instance.fm.set_symptom("RiskyTemperatureOffice", None)

    # Extract the call arguments
    recovery_call_args = app_instance.reco_man.recovery.call_args

    # Verify only the first argument of the call, which should be the symptom object
    assert recovery_call_args[0][0] == app_instance.symptoms["RiskyTemperatureOffice"]


def test_app_initialization_health_state(mocked_hass_app_with_temp_component):
    """Test health state transitions during app initialization."""
    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component

    app_instance.initialize()

    # Verify that health state transitions from 'init' to 'running'.
    health_topic = mqtt_topic_for("sensor.safety_app_health")
    health_payloads = mqtt_payloads(mocked_hass, health_topic)
    assert "init" in health_payloads
    assert "running" in health_payloads


def test_terminate_publishes_offline(mocked_hass_app_with_temp_component):
    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    app_instance.terminate()

    health_topic = mqtt_topic_for("sensor.safety_app_health")
    system_topic = mqtt_topic_for("sensor.safetysystem_state")
    assert mqtt_payloads(mocked_hass, health_topic)[-1] == "stopped"
    assert mqtt_payloads(mocked_hass, system_topic)[-1] == "stopped"
    assert mqtt_payloads(mocked_hass, "safety_component/status")[-1] == "offline"


def test_invalid_user_config_type_stops_cleanly(
    mocked_hass_app_with_temp_component,
):
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.args = {"app_config": {}, "user_config": None}

    app_instance.initialize()

    app_instance.log.assert_called_with(
        "Invalid MQTT configuration: user_config must be a mapping",
        level="ERROR",
    )
    assert app_instance._stopped == app_instance.name

def test_common_entities_lookup(mocked_hass_app_with_temp_component):
    """Test that common entities are properly initialized and accessible."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Access the common entity and ensure it matches the configured value
    assert app_instance.common_entities_cfg["outside_temp"] == "sensor.dom_temperature"


def test_initialize_no_faults_or_safety_components(mocked_hass_app_with_temp_component):
    """
    Test Case: No faults or safety components defined in configuration.

    Scenario:
        - The configuration does not include any faults or safety components.
        - Expected Result: The validator reports the error while MQTT health remains observable.
    """
    app_instance, mocked_hass, _, _, _ = mocked_hass_app_with_temp_component

    # Modify the configuration to remove 'faults' and 'safety_components'
    app_instance.args['app_config']['faults'] = {}  # No faults defined
    app_instance.args['user_config']['safety_components'] = {}  # No safety components defined

    app_instance.initialize()

    app_instance.log.assert_called_with(
        "Invalid app configuration: app_config.faults must define at least one fault",
        level="ERROR",
    )

    health_topic = mqtt_topic_for("sensor.safety_app_health")
    assert mqtt_payloads(mocked_hass, health_topic)[-1] == "invalid_cfg"
    assert mqtt_payloads(mocked_hass, "safety_component/status")[-1] == "online"
    assert not hasattr(app_instance, "_stopped")
