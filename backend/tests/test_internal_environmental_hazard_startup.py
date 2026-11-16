"""End-to-end startup wiring for the configured internal hazard monitor."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from build_app_config import compile_config
from SafetyFunctions import SafetyFunctions
from components.core.fault_state_policy import FaultEvaluationStatus
from components.core.degradation import RestrictionEffect
from components.core.types_common import FaultState
from .fixtures.hass_fixture import drain_responses, install_response_fakes


def _retention_configuration(tmp_path):
    backend = Path(__file__).parents[1]
    raw = compile_config(user_path=backend / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0})["SafetyFunctions"]
    raw["app_config"]["validation"]["validate_entity_existence"] = False
    raw["user_config"]["components_enabled"] = {"EntityMonitorComponent": True, "InternalEnvironmentalHazardMonitorComponent": True}
    raw["app_config"]["fault_evidence"]["state_file"] = str(tmp_path / "fault_evidence.json")
    for namespace in ("notification", "recovery"):
        raw["user_config"][namespace]["persistence"]["state_file"] = str(tmp_path / f"{namespace}.json")
    policy = raw["app_config"]["calibration"]["functional_safety"]
    for key in ("battery_fault_catalog_file", "periodic_test_state_file", "detector_test_state_file"):
        policy[key] = str(tmp_path / f"{key}.json")
    indoor = raw["user_config"]["safety_components"]["InternalEnvironmentalHazardMonitorComponent"]
    indoor["persistence"]["state_file"] = str(tmp_path / "indoor.json")
    indoor["detectors"] = {"Fixture": dict(area_id="example_utility", entity_id="binary_sensor.fixture",
        friendly_name="Fictional gas detector", hazard="flammable_gas", gas_identity="flammable_gas_unspecified",
        profile="home_assistant_binary_alarm")}
    return raw


def _fixture_service(service, **payload):
    if payload.get("callback") is not None:
        payload["callback"]({"success": True, "result": None})
    return "fictional-scheduling-return"


@pytest.mark.parametrize("mode", ["removed", "rebound", "profile_changed", "disabled", "empty", "combined_owners"])
def test_original_indoor_incident_and_gas_latch_precede_first_output_after_removal(tmp_path, mode):
    from datetime import datetime, timezone
    from components.core.snapshot_writer import SnapshotWriter
    from components.core.sqlite_state_store import SqliteStateDatabase
    from components.safetycomponents.internal_environmental_hazard.observation import DetectorBinding
    from components.safetycomponents.internal_environmental_hazard.schema import validate_internal_environmental_hazard_config
    from components.safetycomponents.internal_environmental_hazard.state_store import IndoorStateOwner, commissioned_checkpoint, current_launch_id
    from .safety_lifecycle_support import InlineStorageExecutor
    from .fixtures.hass_fixture import mqtt_json_payloads, mqtt_topic_for

    raw = _retention_configuration(tmp_path)
    source = raw["user_config"]["safety_components"]["InternalEnvironmentalHazardMonitorComponent"]
    normalized = validate_internal_environmental_hazard_config(source)
    contract = DetectorBinding.from_config("Fixture", normalized["detectors"]["Fixture"], normalized["profiles"]["home_assistant_binary_alarm"])
    store = SqliteStateDatabase(tmp_path / "safety_state.sqlite3").store("internal_environment_state", source["persistence"]["state_file"])
    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    store.save(commissioned_checkpoint("reviewed-fictional-installation", at))
    owner = IndoorStateOwner(store, writer=SnapshotWriter(InlineStorageExecutor()), launch_receipt=current_launch_id())
    owner.establish_session()
    record = owner.set_alarm(contract, {"detector": "Original equipment"}, at=at)
    owner.drain()
    assert owner.stop()
    owner.drain()
    if mode in {"removed", "empty", "combined_owners"}:
        source["detectors"] = {}
    elif mode == "disabled":
        raw["user_config"]["components_enabled"]["InternalEnvironmentalHazardMonitorComponent"] = False
    elif mode == "rebound":
        source["detectors"]["Fixture"]["entity_id"] = "binary_sensor.replacement"
    else:
        source["profiles"]["home_assistant_binary_alarm"]["version"] = "2"
    if mode == "combined_owners":
        from .test_heating_monitor import build_component
        from components.safetycomponents.external_hazard.assertion_store import AssertionRecord, RealAssertionStore
        heater, _, _, clock = build_component(tmp_path / "heating", {
            "sensor.health": {"state": "bad", "attributes": {}},
            "sensor.flow": {"state": "30", "attributes": {}},
        })
        heater._tick()
        clock[0] += 5
        heater._tick()
        assert heater._latches["Heating_supervision_loss_Main"].active
        heat_config = heater._config.model_dump()
        raw["user_config"]["safety_components"]["HeatingSystemMonitorComponent"] = heat_config
        raw["user_config"]["components_enabled"]["HeatingSystemMonitorComponent"] = True
        database = SqliteStateDatabase(tmp_path / "safety_state.sqlite3")
        database.store("heating_monitor_state", heat_config["state_file"]).save(heater._store.load())
        external = RealAssertionStore(database)
        external.assert_real(AssertionRecord(symptom_id="ExternalWeatherExposureWindOriginalOpening",
            fault_id="ExternalWeatherExposure", opening="OriginalOpening", hazard="wind",
            source="ImgwWarningsApiComponent", asserted_at=at.isoformat(), context={}))
    app = SafetyFunctions(args=raw)
    app.get_state = lambda *_args, **_kwargs: "off"
    app.render_template = lambda *_args, **_kwargs: "Fictional utility"
    app.call_service = Mock(side_effect=_fixture_service)
    install_response_fakes(app, app)
    app.initialize()
    drain_responses(app)
    restored = app.indoor_state_owner.records[record.record_id]
    assert restored.incident_id == record.incident_id and restored.alarm_active
    assert app.indoor_state_owner.gas_inhibited
    assert app.fm.check_fault("InternalFlammableGasDetected") is FaultEvaluationStatus.UNEVALUABLE
    assert app.fm.retained_assertions("InternalFlammableGasDetected")[0]["entity_id"] == "binary_sensor.fixture"
    payloads = mqtt_json_payloads(app, mqtt_topic_for("sensor.fault_InternalFlammableGasDetected", "attributes"))
    assert payloads and payloads[0]["active"] is True
    summary = mqtt_json_payloads(app, mqtt_topic_for("sensor.internal_environment_summary", "attributes"))
    assert summary[0]["gas_switching_inhibited"] is True
    assert summary[0]["retained_records_total"] == 1
    assert not any(call.args and call.args[0].startswith(("light/", "switch/", "fan/", "valve/")) for call in app.call_service.call_args_list)
    if mode == "combined_owners":
        assert app.sm_modules["HeatingSystemMonitorComponent"]._latches["Heating_supervision_loss_Main"].active
        assert app.fm.retained_assertions("ExternalWeatherExposure")[0]["opening"] == "OriginalOpening"
        assert app.fm.retained_assertions("InternalFlammableGasDetected")[0]["incident_id"] == record.incident_id


@pytest.mark.parametrize("history", ["missing", "corrupt"])
def test_missing_or_corrupt_checkpoint_does_not_prove_absence_of_gas_history(tmp_path, history):
    from components.core.sqlite_state_store import SqliteStateDatabase
    raw = _retention_configuration(tmp_path)
    raw["user_config"]["components_enabled"]["InternalEnvironmentalHazardMonitorComponent"] = False
    if history == "corrupt":
        path = raw["user_config"]["safety_components"]["InternalEnvironmentalHazardMonitorComponent"]["persistence"]["state_file"]
        SqliteStateDatabase(tmp_path / "safety_state.sqlite3").store("internal_environment_state", path).save({"version": 2, "invalid": True})
    app = SafetyFunctions(args=raw)
    app.get_state = lambda *_args, **_kwargs: "off"
    app.render_template = lambda *_args, **_kwargs: "Fictional utility"
    app.call_service = Mock(side_effect=_fixture_service)
    app._indoor_initial_checkpoint = None
    install_response_fakes(app, app)
    app.initialize()
    drain_responses(app)
    assert app.indoor_state_owner.history_unknown and app.indoor_state_owner.gas_inhibited
    assert app.fm.check_fault("InternalFlammableGasDetected") is FaultEvaluationStatus.UNEVALUABLE
    assert not any(call.args and call.args[0].startswith(("light/", "switch/")) for call in app.call_service.call_args_list)


@pytest.mark.parametrize("checkpoint_loss", [False, True])
def test_healed_gas_alarm_keeps_latch_and_lost_checkpoint_rejects_virgin_receipt(tmp_path, checkpoint_loss):
    from datetime import datetime, timedelta, timezone
    from copy import deepcopy
    from .test_internal_environmental_hazard_component import _snapshot
    raw = _retention_configuration(tmp_path)
    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    source_state = [_snapshot("on", at)]
    def create(configuration):
        app = SafetyFunctions(args=configuration)
        app.get_state = lambda entity_id, **kwargs: source_state[0] if entity_id == "binary_sensor.fixture" else "off"
        app.render_template = lambda *_args, **_kwargs: "Fictional utility"
        app.call_service = Mock(side_effect=_fixture_service)
        install_response_fakes(app, app)
        app.initialize()
        drain_responses(app)
        return app
    app = create(deepcopy(raw))
    monitor = app.sm_modules["InternalEnvironmentalHazardMonitorComponent"]
    monitor._monotonic = lambda: 0.0
    monitor._source_event("state_changed", dict(entity_id="binary_sensor.fixture", old_state=_snapshot("off", at - timedelta(seconds=1)),
        new_state=source_state[0], metadata=dict(origin="LOCAL", time_fired=at.isoformat(), context=dict(id="alarm"))))
    old = source_state[0]
    source_state[0] = _snapshot("off", at + timedelta(seconds=1))
    monitor._monotonic = lambda: 1.0
    monitor._source_event("state_changed", dict(entity_id="binary_sensor.fixture", old_state=old, new_state=source_state[0],
        metadata=dict(origin="LOCAL", time_fired=source_state[0]["last_updated"], context=dict(id="clear"))))
    runtime = monitor._detectors["Fixture"]
    candidate = runtime.authority.candidate
    assert candidate is not None
    monitor._monotonic = lambda: 31.0
    monitor._alarm_clear_elapsed(detector_key="Fixture", candidate_token=candidate.token)
    assert runtime.alarm_active
    drain_responses(app)
    assert not runtime.alarm_active
    assert app.fault_evidence.get("InternalFlammableGasDetected")["active"] is False
    assert app.indoor_state_owner.gas_inhibited
    original = app.indoor_state_owner.records[runtime.record_id]
    assert original.clear_proof is not None
    app.terminate()
    assert app.indoor_state_owner.store.load()["clean"] is True
    if checkpoint_loss:
        app.indoor_state_owner.store.save({})  # Explicit fictional namespace loss.
    raw["user_config"]["components_enabled"]["InternalEnvironmentalHazardMonitorComponent"] = False
    restarted = create(raw)
    assert restarted.indoor_state_owner.gas_inhibited
    assert restarted.indoor_state_owner.history_unknown is checkpoint_loss
    if checkpoint_loss:
        assert not restarted.indoor_state_owner.records
        assert restarted.fm.check_fault("InternalFlammableGasDetected") is FaultEvaluationStatus.UNEVALUABLE
    else:
        assert restarted.indoor_state_owner.records[original.record_id].incident_id == original.incident_id
        assert not restarted.indoor_state_owner.records[original.record_id].alarm_active


@pytest.mark.parametrize("restart", ["reconnect", "stop_start", "disable_enable"])
def test_restart_at_second_29_cannot_reuse_clear_or_old_ingress(restart):
    from datetime import datetime, timedelta, timezone
    from .test_internal_environmental_hazard_component import (
        CO_ENTITY, GAS_ENTITY, _build_component, _live, _snapshot,
    )
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    states = {GAS_ENTITY: _snapshot("on", now), CO_ENTITY: _snapshot("off", now)}
    component, hass_app, events = _build_component(states, now=now)
    runtime = component._detectors["BathroomFlammableGas"]
    component._evaluate_mechanism(component.safety_mechanisms["InternalEnv_flammable_gas_BathroomFlammableGas"])
    old = states[GAS_ENTITY]
    states[GAS_ENTITY] = _snapshot("off", now + timedelta(seconds=1))
    _live(component, GAS_ENTITY, old, states[GAS_ENTITY])
    candidate = runtime.authority.candidate
    assert candidate is not None
    component._monotonic = lambda: 29.0
    if restart == "reconnect":
        component._source_session_changed("plugin_stopped", {"name": "fixture-hass"})
        component._source_session_changed("plugin_started", {"name": "fixture-hass"})
    elif restart == "stop_start":
        component.stop()
        component.start()
    else:
        from components.core.types_common import SMState
        name = "InternalEnv_flammable_gas_BathroomFlammableGas"
        component.enable_safety_mechanism(name, SMState.DISABLED)
        component.enable_safety_mechanism(name, SMState.ENABLED)
    component._monotonic = lambda: 30.0
    component._evaluate_mechanism(component.safety_mechanisms["InternalEnv_flammable_gas_BathroomFlammableGas"])
    component._alarm_clear_elapsed(detector_key=runtime.key, candidate_token=candidate.token)
    assert runtime.alarm_active and runtime.authority.candidate is None
    assert not any(item["state"] == FaultState.CLEARED and item["symptom_id"].startswith("InternalEnv_flammable_gas") for item in events)
    assert not any(call.args and call.args[0].startswith(("switch/", "light/")) for call in hass_app.call_service.call_args_list)


@pytest.mark.parametrize("unwritable_database", [False, True])
def test_gas_alarm_reaches_l1_fault_without_co_consensus(tmp_path, monkeypatch, unwritable_database) -> None:
    from components.core.functional_safety_diagnostics import JsonFunctionalSafetyDiagnosticsStore

    monkeypatch.setattr(
        "SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore",
        lambda: JsonFunctionalSafetyDiagnosticsStore(tmp_path / "functional_safety.json"),
    )
    backend_dir = Path(__file__).parents[1]
    raw = compile_config(
        user_path=backend_dir / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0},
    )["SafetyFunctions"]
    raw["app_config"]["calibration"]["functional_safety"][
        "battery_fault_catalog_file"
    ] = str(tmp_path / "battery_fault_catalog.json")
    for key in ("periodic_test_state_file", "detector_test_state_file"):
        raw["app_config"]["calibration"]["functional_safety"][key] = str(tmp_path / f"{key}.json")
    raw["app_config"]["validation"]["validate_entity_existence"] = False
    raw["app_config"]["calibration"]["entity_monitor"]["startup_grace_seconds"] = 600
    raw["user_config"]["components_enabled"] = {
        "InternalEnvironmentalHazardMonitorComponent": True,
        "EntityMonitorComponent": True,
    }
    raw["user_config"]["notification"]["persistence"]["state_file"] = str(
        tmp_path / "notification.json"
    )
    raw["user_config"]["recovery"]["persistence"]["state_file"] = str(
        tmp_path / "recovery.json"
    )
    raw["app_config"]["fault_evidence"]["state_file"] = str(
        tmp_path / "fault_evidence.json"
    )
    internal = raw["user_config"]["safety_components"][
        "InternalEnvironmentalHazardMonitorComponent"
    ]
    internal["detectors"] = {
        "ExampleUtilityFlammableGas": {
            "area_id": "example_utility",
            "entity_id": "binary_sensor.example_utility_gas_alarm",
            "friendly_name": "Example gas detector",
            "hazard": "flammable_gas",
            "profile": "home_assistant_binary_alarm",
            "gas_identity": "flammable_gas_unspecified",
        },
        "ExampleUtilityCarbonMonoxide": {
            "area_id": "example_utility",
            "entity_id": "binary_sensor.example_utility_co_alarm",
            "friendly_name": "Example carbon monoxide detector",
            "hazard": "carbon_monoxide",
            "profile": "home_assistant_binary_alarm",
        },
    }
    internal["persistence"]["state_file"] = str(tmp_path / "internal.json")
    if unwritable_database:
        (tmp_path / "safety_state.sqlite3").mkdir()
    app = SafetyFunctions(args=raw)
    service_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_state(entity_id: str, **_: Any) -> Any:
        if entity_id == "binary_sensor.example_utility_gas_alarm":
            return "on"
        if entity_id == "binary_sensor.example_utility_co_alarm":
            return "off"
        return None

    app.get_state = fake_state
    app.render_template = lambda *_args, **_kwargs: "Łazienka"
    app.call_service = lambda service, **kwargs: service_calls.append(
        (service, kwargs)
    )

    install_response_fakes(app, app, capture_only=True)
    app.initialize()
    drain_responses(app)

    assert app.degradation.binding_errors == {}

    monitor = app.sm_modules["InternalEnvironmentalHazardMonitorComponent"]
    assert app.startup_grace.snapshot()["phase"] == "settling"
    health_symptom = next(
        symptom_id for symptom_id, (_, kind) in monitor._symptom_bindings.items()
        if kind == "health"
    )
    assert app.symptoms[health_symptom].parameters["detection_budget_seconds"] == 60
    app.event_bus.publish("symptom", symptom_id=health_symptom, state=FaultState.SET)
    assert app.fm.check_fault("InternalEnvironmentalDetectorUnavailable") is FaultEvaluationStatus.FAIL
    app.event_bus.publish("symptom", symptom_id=health_symptom, state=FaultState.CLEARED)
    assert app.state_database.path == tmp_path / "safety_state.sqlite3"
    for store in (
        monitor._state_store, app.notify_man.state_store, app.reco_man.state_store,
        app.fault_evidence.store, app.periodic_test_monitor.state_store,
        app.detector_test_monitor.state_store,
    ):
        assert store.database is app.state_database
    if unwritable_database:
        assert app.fm.check_symptom("AppHealthPersistenceBatteryFaultCatalog") == FaultState.SET
        assert app.fm.check_fault("SafetyAppHealth") is FaultEvaluationStatus.FAIL
    else:
        assert next(item for item in monitor._state_store.load()["records"] if item["detector_key"] == "ExampleUtilityFlammableGas")["gas_switching_inhibited"] is True
    failed_store = Mock()
    failed_store.save.side_effect = OSError("detector state unavailable")
    monitor._state_store = failed_store
    monitor._persist_state()
    drain_responses(app)
    cause = "AppHealthPersistenceInternalEnvironmentState"
    assert app.fm.check_symptom(cause) == FaultState.SET
    assert cause in app.degradation.causes_for(
        "InternalEnv_flammable_gas_ExampleUtilityFlammableGas",
        RestrictionEffect.DURABILITY,
    )
    assert all(
        item["symptom"].startswith("Internal")
        for item in app.degradation.snapshot()["affected"]
        if item["cause"] == cause
    )
    failed_store.save.side_effect = None
    monitor._persist_state()
    drain_responses(app)
    assert app.fm.check_symptom(cause) == (
        FaultState.SET if unwritable_database else FaultState.CLEARED
    )

    assert app.fm.check_fault("InternalFlammableGasDetected") is FaultEvaluationStatus.FAIL
    assert app.fm.check_fault("InternalCarbonMonoxideDetected") is not FaultEvaluationStatus.FAIL
    if unwritable_database:
        assert app.fm.check_fault("InternalSmokeDetected") is FaultEvaluationStatus.UNEVALUABLE
        assert app.indoor_state_owner.history_unknown
    else:
        assert "InternalSmokeDetected" not in app.faults
        assert "sensor.fault_internalsmokedetected" not in app.mqtt_entities.discovered_entities
    assert app.faults["InternalFlammableGasDetected"].level == 1
    assert any(
        service == "notify/mobile_app_example_phone"
        for service, _kwargs in service_calls
    )
    assert "InternalEnvironmentExampleUtilityFlammableGas" in app.sm_modules[
        "EntityMonitorComponent"
    ]._entities
    assert not any(
        symptom.startswith(
            "EntityHealthFailureInternalEnvironmentExampleUtilityFlammableGas"
        )
        for symptom in app.symptoms
    )
    assert not any(
        service.startswith(("light/", "switch/", "fan/", "valve/"))
        for service, _kwargs in service_calls
    )
