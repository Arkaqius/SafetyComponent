from copy import deepcopy
from unittest.mock import Mock

import pytest

from components.core.types_common import FaultState, SMState
from components.core.fault_state_policy import FaultEvaluationStatus
from components.faults_manager.cfg_parser import validate_fault_routes
from components.recovery_manager.recovery_manager import ComponentRecoveryError
from components.notification_manager.models import (
    DeliveryBatchResult, DeliveryDisposition, TargetDeliveryResult,
)
from components.core.startup_grace import StartupGrace

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
    validate_fault_routes(app_instance.symptoms, app_instance.faults)
    assert app_instance.degradation.binding_errors == {}
    assert "sensor.safety_coverage_state" in app_instance.mqtt_entities.discovered_entities

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
    assert app_instance.common_entities_cfg["outside_temp"] == (
        "sensor.example_outdoor_temperature"
    )

    # Verify that safety mechanisms are initialized and enabled via MQTT state.
    health_topic = mqtt_topic_for("sensor.safety_app_health")
    health_payloads = mqtt_payloads(mocked_hass, health_topic)
    assert "init" in health_payloads
    assert "running" in health_payloads
    assert "sensor.safety_evaluation_progress" in app_instance.mqtt_entities.discovered_entities
    progress_payload = mqtt_json_payloads(
        mocked_hass,
        mqtt_topic_for("sensor.safety_evaluation_progress", "attributes"),
    )[-1]
    assert progress_payload["components"]["TemperatureComponent"]["status"] == "observed"
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
    forecast_evaluation = threshold_attributes.pop("forecast_evaluation")
    assert forecast_evaluation["symptom_id"] == "RiskyTemperatureOfficeForeCast"
    assert forecast_evaluation["status"] == "risk"
    assert forecast_evaluation["modeled_temperature_c"] == 7.0
    assert forecast_evaluation["threshold_c"] == 18.0
    assert forecast_evaluation["evaluated_at"] is not None
    assert threshold_attributes == {
        "area_id": "office",
        "area_name": "Office",
        "attribution": "Managed by SafetyFunction",
        "source_entity": "sensor.office_temperature",
        "threshold_type": "low",
    }


def test_invalid_fault_route_keeps_application_out_of_running_state(
    mocked_hass_app_with_temp_component,
) -> None:
    """A missing live route fails configuration without starting monitors."""

    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.args = deepcopy(app_instance.args)
    app_instance.args["app_config"]["faults"]["RiskyTemperature"][
        "related_sms"
    ] = ["sm_typo"]

    app_instance.initialize()

    assert mqtt_payloads(
        mocked_hass, mqtt_topic_for("sensor.safety_app_health")
    )[-1] == "invalid_cfg"
    assert not hasattr(app_instance, "notify_man")


def test_old_shared_door_fault_discovery_is_removed(
    mocked_hass_app_with_temp_component,
) -> None:
    """The obsolete shared identity is retired without a clear transition."""

    app_instance, mocked_hass, *_ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    for topic in (
        "homeassistant/sensor/safety_component_fault_safetydooropentimeout/config",
        "homeassistant/sensor/fault_safetydooropentimeout/config",
        "safety_component/state/fault_safetydooropentimeout",
        "safety_component/attributes/fault_safetydooropentimeout",
    ):
        assert mqtt_payloads(mocked_hass, topic)[-1] == ""
    assert "sensor.fault_safetydooropentimeout" not in (
        app_instance.mqtt_entities.discovered_entities
    )


def test_fault_registration_preserves_hazard_and_diagnostic_metadata(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, mocked_hass, _, _, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    for fault_name, category in (("RiskyTemperature", "H"), ("SafetyAppHealth", "D")):
        attributes = mqtt_json_payloads(
            mocked_hass,
            mqtt_topic_for(f"sensor.fault_{fault_name.lower()}", "attributes"),
        )[-1]
        assert attributes["category"] == category
        assert isinstance(attributes["contributors"], list)
        assert isinstance(attributes["active_contributors"], list)
        assert attributes["level"] == f"level_{app_instance.faults[fault_name].level}"


def test_fault_metadata_and_unified_frame_survive_activation_and_clear(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, mocked_hass, _, _, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    topic = mqtt_topic_for("sensor.fault_riskytemperature", "attributes")

    app_instance.fm.set_symptom("RiskyTemperatureOffice", {"location": "Office"})
    active = mqtt_json_payloads(mocked_hass, topic)[-1]
    assert active["category"] == "H"
    assert active["level"] == "level_2"
    assert "RiskyTemperatureOffice" in active["contributors"]
    assert "RiskyTemperatureForecastOffice" not in active["contributors"]
    assert active["active_contributors"] == ["RiskyTemperatureOffice"]
    assert active["active"] is True
    assert active["freeze_frame"]["version"] == 2
    assert "extended_data" not in active

    app_instance.fm.clear_symptom("RiskyTemperatureOffice", {"location": "Office"})
    cleared = mqtt_json_payloads(mocked_hass, topic)[-1]
    assert cleared["category"] == "H"
    assert cleared["level"] == "level_2"
    assert cleared["contributors"] == active["contributors"]
    assert cleared["active_contributors"] == []
    assert cleared["active"] is False
    assert cleared["freeze_frame"]["captured_at"] == active["freeze_frame"]["captured_at"]
    assert cleared["freeze_frame"]["last_valid_pass_at"] is not None
    assert "extended_data" not in cleared


def test_reinitialize_keeps_raw_appdaemon_configuration(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, mocked_hass, __, ___, _ = mocked_hass_app_with_temp_component

    app_instance.initialize()

    raw_temperature_config = app_instance.args["user_config"][
        "safety_components"
    ]["TemperatureComponent"]
    assert isinstance(raw_temperature_config, dict)

    app_instance.initialize()

    assert mqtt_payloads(
        mocked_hass, mqtt_topic_for("sensor.safety_app_health")
    )[-1] == "running"


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
    assert "InputMonitoringUnavailable" in app_instance.faults
    assert "EntityHealthTemperatureOffice" not in app_instance.faults
    assert (
        "EntityHealthFailureTemperatureOfficeAvailability" in app_instance.symptoms
    )


def test_shared_startup_grace_keeps_h_and_app_health_live_while_d_is_unknown(
    mocked_hass_app_with_temp_component, monkeypatch,
) -> None:
    """Real application routing postpones diagnostics, including their recovery effects."""
    app, mocked_hass, *_ = mocked_hass_app_with_temp_component
    app.args = deepcopy(app.args)
    app.args["app_config"]["calibration"] = {"entity_monitor": {"startup_grace_seconds": 600}}
    app.args["user_config"]["components_enabled"]["EntityMonitorComponent"] = True
    app.args["user_config"]["safety_components"]["EntityMonitorComponent"] = {
        "explicit_entities": {"StartupExtra": {"entity_id": "sensor.startup_extra", "description": "Startup diagnostic"}}
    }
    now = [0.0]
    monkeypatch.setattr("SafetyFunctions.StartupGrace", lambda bus, ids, seconds: StartupGrace(bus, ids, seconds, clock=lambda: now[0]))
    app.initialize()
    diagnostic = "EntityHealthFailureStartupExtraAvailability"
    app.event_bus.publish("symptom", symptom_id=diagnostic, state=FaultState.SET)
    assert app.fm.check_fault("EntityHealthStartupExtra") is FaultEvaluationStatus.UNEVALUABLE
    budgeted = "EntityHealthFailureTemperatureOfficeAvailability"
    app.event_bus.publish("symptom", symptom_id=budgeted, state=FaultState.SET)
    assert app.fm.check_fault("InputMonitoringUnavailable") is FaultEvaluationStatus.FAIL
    app.event_bus.publish("symptom", symptom_id="RiskyTemperatureOffice", state=FaultState.SET)
    assert app.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.FAIL
    app.self_diagnostics.record_app_cause("publication", True)
    assert app.fm.check_fault("SafetyAppHealth") is FaultEvaluationStatus.FAIL
    app.event_bus.publish("symptom", symptom_id=diagnostic, state=FaultState.CLEARED)
    now[0] = 600
    app._finish_startup_grace()
    assert app.fm.check_symptom(diagnostic) is FaultState.CLEARED
    assert app.fm.check_fault("EntityHealthStartupExtra") is not FaultEvaluationStatus.FAIL
    progress = mqtt_json_payloads(mocked_hass, mqtt_topic_for("sensor.safety_evaluation_progress", "attributes"))[-1]
    assert progress["startup"]["phase"] == "complete"


def test_disabling_during_startup_discards_pending_diagnostic_activation(
    mocked_hass_app_with_temp_component, monkeypatch,
) -> None:
    app, _, *_ = mocked_hass_app_with_temp_component
    app.args = deepcopy(app.args)
    app.args["app_config"]["calibration"] = {"entity_monitor": {"startup_grace_seconds": 600}}
    app.args["user_config"]["components_enabled"]["EntityMonitorComponent"] = True
    app.args["user_config"]["safety_components"]["EntityMonitorComponent"] = {
        "explicit_entities": {"StartupExtra": {"entity_id": "sensor.startup_extra", "description": "Startup diagnostic"}}
    }
    now = [0.0]
    monkeypatch.setattr("SafetyFunctions.StartupGrace", lambda bus, ids, seconds: StartupGrace(bus, ids, seconds, clock=lambda: now[0]))
    app.initialize()
    diagnostic = "EntityHealthFailureStartupExtraAvailability"
    app.event_bus.publish("symptom", symptom_id=diagnostic, state=FaultState.SET)
    app.fm.enable_sm(diagnostic, SMState.DISABLED)
    now[0] = 600
    app._finish_startup_grace()
    assert app.fm.check_symptom(diagnostic) is FaultState.NOT_TESTED
    assert app.fm.check_fault("EntityHealthStartupExtra") is not FaultEvaluationStatus.FAIL


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
    app_instance.mqtt_entities.publish_heartbeat_batch = Mock()

    app_instance._mqtt_heartbeat()
    app_instance._mqtt_heartbeat(timer="heartbeat")

    assert app_instance.mqtt_entities.publish_heartbeat_batch.call_count == 2

    # Verify TemperatureComponent configurations are set up correctly
    assert "TemperatureComponent" in app_instance.sm_modules

    # Verify that TemperatureComponent received the correct configuration
    temp_comp_cfg = app_instance.safety_components_cfg["TemperatureComponent"]

    office_cfg = next(cfg["Office"] for cfg in temp_comp_cfg if "Office" in cfg)
    assert office_cfg["temperature_sensor"] == "sensor.office_temperature"
    assert office_cfg["window_sensor"] == "binary_sensor.example_office_window"

    kitchen_cfg = next(cfg["Kitchen"] for cfg in temp_comp_cfg if "Kitchen" in cfg)
    assert kitchen_cfg["temperature_sensor"] == "sensor.kitchen_temperature"
    assert kitchen_cfg["window_sensor"] == "binary_sensor.example_kitchen_window"

    # Verify the NotificationManager is initialized with the correct entity
    assert (
        app_instance.notify_man.notification_config["local"]["light_entity"]
        == "light.warning_light"
    )

    # Verify that common entities are properly initialized in CommonEntities
    assert "outside_temp" in app_instance.common_entities_cfg
    assert app_instance.common_entities_cfg["outside_temp"] == (
        "sensor.example_outdoor_temperature"
    )


def test_fault_and_symptom_registration(mocked_hass_app_with_temp_component):
    """Ensure all configured faults and symptoms are correctly registered in FaultManager."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Assert that all symptoms are registered
    for symptom_name in app_instance.symptoms:
        expected = (
            FaultState.CLEARED
            if symptom_name in {
                "AppHealthStartup", "AppHealthPublication", "AppHealthDelivery",
                "AppHealthPersistenceNotificationState",
                "AppHealthPersistenceRecoveryState",
                "AppHealthPersistenceFaultEvidenceState",
                "AppHealthPersistenceSafetyRoutines",
            }
            or symptom_name.startswith(("AppHealthEvaluation_", "AppHealthRecovery_"))
            else FaultState.NOT_TESTED
        )
        assert app_instance.fm.check_symptom(symptom_name) == expected

    # Assert that all faults are registered
    for fault_name in app_instance.faults:
        fault = app_instance.faults[fault_name]
        assert fault.name is not None
        assert fault.level >= 0


def test_app_health_storage_failure_routes_once_without_recursive_notification(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    store = Mock()
    store.save.side_effect = OSError("storage unavailable")
    app_instance.notify_man.state_store = store

    app_instance.notify_man._persist_state()

    assert app_instance.fm.check_symptom("AppHealthPersistenceNotificationState") == FaultState.SET
    assert app_instance.faults["SafetyAppHealth"].evaluation.active is True


def test_recovery_store_failure_is_reported_without_aborting_detection_or_clearing_from_other_store(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    store = Mock()
    store.save.side_effect = OSError("recovery store unavailable")
    app_instance.reco_man.state_store = store

    assert app_instance.reco_man._persist_state() is False
    assert app_instance.reco_man._storage_available is False
    app_instance.notify_man._persist_state()
    assert app_instance.fm.check_symptom("AppHealthPersistenceRecoveryState") == FaultState.SET

    store.save.side_effect = None
    assert app_instance.reco_man._persist_state() is True
    assert app_instance.fm.check_symptom("AppHealthPersistenceRecoveryState") == FaultState.CLEARED


def test_recovery_timing_uses_compiled_system_policy(mocked_hass_app_with_temp_component):
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.args["user_config"].setdefault("recovery", {})["timing"] = {
        "consent_timeout_seconds": 30, "effect_timeout_seconds": 240,
        "manual_task_timeout_seconds": None,
    }
    app_instance.initialize()
    assert app_instance.reco_man.timing.consent_timeout_seconds == 30
    assert app_instance.reco_man.timing.effect_timeout_seconds == 240


def test_mqtt_outage_keeps_internal_cause_for_external_supervisor(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    original_call_service = app_instance.call_service

    def broken_mqtt(service: str, **kwargs: object) -> object:
        if service == "mqtt/publish":
            raise OSError("broker unavailable")
        return original_call_service(service, **kwargs)

    app_instance.call_service = broken_mqtt
    app_instance._mqtt_heartbeat()
    assert app_instance.fm.check_symptom("AppHealthPublication") == FaultState.SET

    app_instance.call_service = original_call_service
    app_instance._mqtt_heartbeat()
    assert app_instance.fm.check_symptom("AppHealthPublication") == FaultState.CLEARED


def test_component_recovery_policy_error_is_not_shared_dispatch_failure(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    symptom_id = "RiskyTemperatureOffice"
    app_instance.recovery_actions[symptom_id].rec_fun = Mock(
        side_effect=RuntimeError("component policy error")
    )
    symptom = app_instance.symptoms[symptom_id]
    symptom.state = FaultState.SET

    with pytest.raises(ComponentRecoveryError):
        app_instance.reco_man.handle_fault_event(
            symptom=symptom,
            fault_tag="test-fault-tag",
            fault_state=FaultState.SET,
            fault_name="RiskyTemperature",
        )
    assert app_instance.fm.check_symptom(
        f"AppHealthRecovery_{symptom_id}"
    ) == FaultState.CLEARED


def test_failed_mobile_submission_sets_app_health_without_notification_loop(
    mocked_hass_app_with_temp_component,
) -> None:
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    service = app_instance.notify_man.mobile_provider.services[0]
    failed = DeliveryBatchResult((
        TargetDeliveryResult(service, DeliveryDisposition.FAILED, "transport down"),
    ))
    sender = Mock(return_value=failed)
    app_instance.notify_man.mobile_provider.send = sender

    app_instance.notify_man.notify(
        "Test hazard", 2, FaultState.SET, {}, "test-hazard-tag"
    )

    assert app_instance.fm.check_symptom("AppHealthDelivery") == FaultState.SET
    assert sender.call_count == 2


def test_trigger_symptom_sets_fault(mocked_hass_app_with_temp_component):
    """Test triggering a symptom results in fault state being set."""
    app_instance, _, __, ___, _ = mocked_hass_app_with_temp_component
    app_instance.initialize()

    # Manually trigger a symptom
    app_instance.fm.set_symptom("RiskyTemperatureOffice", None)

    # Check if the corresponding fault is set to 'SET'
    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.FAIL


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
    assert app_instance.common_entities_cfg["outside_temp"] == (
        "sensor.example_outdoor_temperature"
    )


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
