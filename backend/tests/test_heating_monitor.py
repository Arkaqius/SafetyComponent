"""Contracts for product-independent heating input mapping and durable faults."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from components.core.event_bus import EventBus
from components.core.localization import Localizer
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.sqlite_state_store import SqliteStateDatabase
from components.core.types_common import FaultState, SMState
from components.safetycomponents.heating.engine import observed_phase, supervise_inputs
from components.safetycomponents.heating.heating_system_monitor_component import (
    HeatingSystemMonitorComponent,
)
from components.safetycomponents.heating.inputs import (
    HeatingInputReader,
    HeatingObservation,
    timestamp,
)
from components.safetycomponents.heating.schema import (
    HeatingConfig,
    HeatingInput,
    HeatingProfile,
)


def binding(entity="sensor.any_source", **overrides):
    return HeatingInput(
        entity_id=entity,
        evidence_kind="measurement",
        independence_group="device",
        **overrides,
    )


@pytest.mark.parametrize(
    "entity,attribute,raw,mapping",
    [
        ("sensor.vendor_a", None, "operating", {"operating": True, "stopped": False}),
        ("sensor.direct_device", "burning", "yes", {"yes": True, "no": False}),
    ],
)
def test_unrelated_sources_normalize_to_same_boolean(entity, attribute, raw, mapping):
    record = {
        "state": raw if attribute is None else "online",
        "attributes": {attribute: raw, "sample_at": 100},
    }
    reader = HeatingInputReader(lambda _: record)
    result = reader.read(
        "boiler_active",
        binding(
            entity,
            attribute=attribute,
            value_map=mapping,
            freshness="source_timestamp",
            observed_at_attribute="sample_at",
        ),
        101,
    )
    assert result.value is True and result.qualified and result.observed_at == 100


@pytest.mark.parametrize("unit,raw", [("°C", "20"), ("°F", "68"), ("K", "293.15")])
def test_units_normalize_before_scale_offset(unit, raw):
    reader = HeatingInputReader(lambda _: {"state": raw, "attributes": {}})
    result = reader.read("flow_temperature", binding(unit=unit, scale=2, offset=1), 100)
    assert result.value == pytest.approx(41)
    assert result.quality == "availability_only"


@pytest.mark.parametrize(
    "state,quality",
    [
        ("nan", "invalid_value"),
        ("inf", "invalid_value"),
        ("unavailable", "unavailable"),
        ("unknown", "unavailable"),
        ("word", "invalid_value"),
    ],
)
def test_bad_measurement_never_becomes_clear_evidence(state, quality):
    result = HeatingInputReader(lambda _: {"state": state, "attributes": {}}).read(
        "flow_temperature", binding(unit="°C"), 100
    )
    assert result.value is None and result.quality == quality and not result.qualified


def test_freshness_uses_original_time_not_ha_publication_or_poll_time():
    record = {
        "state": "30",
        "last_updated": "2099-01-01T00:00:00Z",
        "attributes": {"at": 100},
    }
    reader = HeatingInputReader(lambda _: record)
    source = binding(
        unit="°C",
        freshness="source_timestamp",
        observed_at_attribute="at",
        max_age_seconds=10,
    )
    assert reader.read("flow_temperature", source, 110).qualified
    assert reader.read("flow_temperature", source, 111).quality == "stale"
    record["attributes"]["at"] = 120
    assert reader.read("flow_temperature", source, 111).quality == "future"
    record["attributes"]["at"] = 99
    assert reader.read("flow_temperature", source, 105).quality == "replayed"
    record["attributes"]["at"] = 100
    record["state"] = "31"
    assert reader.read("flow_temperature", source, 105).quality == "replayed"


def test_unix_text_timestamp_and_separate_timestamp_entity():
    states = {
        "sensor.any_source": {"state": "20", "attributes": {}},
        "sensor.sample_at": {"state": "100", "attributes": {}},
    }
    result = HeatingInputReader(states.get).read(
        "flow_temperature",
        binding(
            unit="°C",
            freshness="source_timestamp",
            observed_at_entity_id="sensor.sample_at",
        ),
        101,
    )
    assert result.qualified
    assert timestamp("2026-01-01T01:00:00") is None
    assert timestamp(True) is None


def test_no_implicit_truth_or_unmapped_states():
    reader = HeatingInputReader(lambda _: {"state": "on", "attributes": {}})
    assert reader.read("boiler_active", binding(), 100).quality == "invalid_value"
    assert (
        reader.read("boiler_state", binding(value_map={"off": "idle"}), 100).quality
        == "unmapped"
    )


def test_invalid_attribute_container_is_not_replaced_with_entity_state():
    result = HeatingInputReader(lambda _: {"state": "20", "attributes": []}).read(
        "flow_temperature", binding(attribute="temperature", unit="°C"), 100
    )
    assert result.value is None and result.quality == "invalid_value"


def test_power_units_and_impossible_timestamps():
    result = HeatingInputReader(lambda _: {"state": "2.5", "attributes": {}}).read(
        "power_w", binding(unit="kW"), 100
    )
    assert result.value == 2500
    assert timestamp(1e300) is None
    assert timestamp(float("inf")) is None


def observation(value, *, at=100, group="device", kind="measurement", quality="valid"):
    return HeatingObservation(value, quality, at, "sensor.test", group, kind)


def test_supervision_exposes_quality_without_claiming_thermal_coverage():
    assert supervise_inputs({"flow_temperature": observation(20.0)}).violation is False
    assert (
        supervise_inputs(
            {"flow_temperature": observation(None, quality="stale")}
        ).violation
        is True
    )
    assert supervise_inputs({}).violation is None


def test_unknown_phase_and_dhw_priority_remain_separate_from_health():
    assert observed_phase({"boiler_active": observation(True)}) == "unknown"
    assert (
        observed_phase(
            {"boiler_active": observation(True), "dhw_active": observation(True)}
        )
        == "dhw"
    )


def test_code_history_is_not_a_supported_input_role():
    with pytest.raises(ValueError):
        HeatingConfig.model_validate(
            {
                "systems": {
                    "Main": {
                        "friendly_name": "Main",
                        "inputs": {"last_error": binding().model_dump()},
                    }
                }
            }
        )


@pytest.mark.parametrize("rule", [f"R{index:02}" for index in range(7, 13)])
def test_unqualified_safety_paths_cannot_be_activated_by_configuration(rule):
    with pytest.raises(ValueError, match="Only R01"):
        HeatingProfile(enabled_rules=["R01", rule], provenance="test")


def build_component(tmp_path, states, *, initial=100, configuration=None):
    app = MagicMock()
    app.localizer = Localizer({"language": "pl"})
    app.state_database = SqliteStateDatabase(tmp_path / "state.sqlite3")
    app.get_state.side_effect = lambda entity, **_: states.get(entity)
    bus = EventBus()
    events = []
    bus.subscribe("symptom", lambda **payload: events.append(payload))
    monitor = HeatingSystemMonitorComponent(
        app, MagicMock(), bus, MqttEntityManager(app)
    )
    clock = [initial]
    monitor._now = lambda: datetime.fromtimestamp(clock[0], timezone.utc)
    monitor._monotonic = lambda: clock[0]
    config = {
        "state_file": str(tmp_path / "legacy.json"),
        "systems": {
            "Main": {
                "friendly_name": "Kotłownia",
                "inputs": {
                    "source_health": {
                        "entity_id": "sensor.health",
                        "value_map": {"ok": True, "bad": False},
                        "evidence_kind": "contact",
                        "independence_group": "source",
                    },
                    "flow_temperature": binding("sensor.flow", unit="°C").model_dump(),
                },
            }
        },
    }
    config = configuration or config
    symptoms, _ = monitor.get_symptoms_data({monitor.component_name: monitor}, config)
    for symptom in symptoms.values():
        assert monitor.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        monitor.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    return monitor, app, events, clock


def test_two_causes_need_positive_recovery_and_restart_preserves_activation(tmp_path):
    states = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "unavailable", "attributes": {}},
    }
    monitor, app, events, clock = build_component(tmp_path, states)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    assert events[-1]["state"] == FaultState.SET
    incident = events[-1]["additional_info"]["incident_id"]
    states["sensor.health"]["state"] = "ok"
    for _ in range(20):
        clock[0] += 5
        monitor._tick()
    assert monitor._latches["Heating_supervision_loss_Main"].active
    restarted, app2, restored_events, restored_clock = build_component(
        tmp_path, states, initial=clock[0] + 100
    )
    restarted._tick()
    assert restored_events[0]["state"] == FaultState.SET
    assert restored_events[0]["additional_info"]["incident_id"] == incident
    states["sensor.flow"]["state"] = "30"
    for _ in range(12):
        restored_clock[0] += 5
        restarted._tick()
    assert restarted._latches["Heating_supervision_loss_Main"].active
    restored_clock[0] += 5
    restarted._tick()
    assert restored_events[-1]["state"] == FaultState.CLEARED
    for host in (app, app2):
        assert all(
            call.args[0] == "mqtt/publish" for call in host.call_service.call_args_list
        )
        host.turn_on.assert_not_called()
        host.turn_off.assert_not_called()


def test_invalid_persisted_qualification_fails_closed(tmp_path):
    states = {
        "sensor.health": {"state": "ok", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, app, _, _ = build_component(tmp_path, states)
    monitor._tick()
    store = app.state_database.store("heating_monitor_state", tmp_path / "legacy.json")
    snapshot = store.load()
    snapshot["latches"]["Heating_supervision_loss_Main"]["pending_failure_seconds"] = []
    store.save(snapshot)
    restarted, _, _, _ = build_component(tmp_path, states)
    assert restarted._restore_error
    restarted._tick()


def test_empty_registry_has_no_ghost_installations_or_timers(tmp_path):
    monitor, app, _, _ = build_component(tmp_path, {})
    empty = HeatingSystemMonitorComponent(
        app, MagicMock(), EventBus(), MqttEntityManager(app)
    )
    symptoms, recovery = empty.get_symptoms_data(
        {empty.component_name: empty}, {"systems": {}}
    )
    assert symptoms == recovery == {} and empty._timer is None


def test_restart_retains_failure_qualification_without_counting_downtime(tmp_path):
    states = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, _, clock = build_component(tmp_path, states)
    monitor._tick()
    clock[0] += 2
    monitor._tick()
    restarted, _, events, restored_clock = build_component(
        tmp_path, states, initial=1000
    )
    restarted._tick()
    assert not events
    restored_clock[0] += 3
    restarted._tick()
    assert events[-1]["state"] == FaultState.SET


def test_cancelled_pending_failure_republishes_qualified_clear(tmp_path):
    states = {
        "sensor.health": {"state": "ok", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, events, clock = build_component(tmp_path, states)
    monitor._tick()
    states["sensor.health"]["state"] = "bad"
    clock[0] += 1
    monitor._tick()
    states["sensor.health"]["state"] = "ok"
    clock[0] += 1
    monitor._tick()
    assert [item["state"] for item in events] == [
        FaultState.CLEARED,
        FaultState.CLEARED,
    ]


@pytest.mark.parametrize("missing", ["latch", "incident"])
def test_missing_durable_identity_is_not_silently_accepted(tmp_path, missing):
    states = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, _, clock = build_component(tmp_path, states)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    snapshot = monitor._store.load()
    snapshot["latches" if missing == "latch" else "incidents"] = {}
    monitor._store.save(snapshot)
    restarted, _, _, _ = build_component(tmp_path, states)
    assert restarted._restore_error


def test_renaming_installation_does_not_discard_active_evidence(tmp_path):
    states = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, app, _, clock = build_component(tmp_path, states)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    renamed = monitor._config.model_dump()
    renamed["systems"]["Main"]["friendly_name"] = "Nowa nazwa"
    restarted = HeatingSystemMonitorComponent(
        app, MagicMock(), EventBus(), MqttEntityManager(app)
    )
    restarted.get_symptoms_data({restarted.component_name: restarted}, renamed)
    assert restarted._restore_error is None
    assert restarted._latches["Heating_supervision_loss_Main"].active


def test_failed_clear_commit_preserves_active_condition(tmp_path):
    states = {
        "sensor.health": {"state": "bad", "attributes": {}},
        "sensor.flow": {"state": "30", "attributes": {}},
    }
    monitor, _, events, clock = build_component(tmp_path, states)
    monitor._tick()
    clock[0] += 5
    monitor._tick()
    states["sensor.health"]["state"] = "ok"
    monitor._store.save = MagicMock(side_effect=OSError("test storage failure"))
    for _ in range(14):
        clock[0] += 5
        monitor._tick()
    assert monitor._latches["Heating_supervision_loss_Main"].active
    assert all(item["state"] != FaultState.CLEARED for item in events)
    assert (
        monitor._store.load()["latches"]["Heating_supervision_loss_Main"]["active"]
        is True
    )


def test_heating_initializes_through_application_fault_and_coverage_wiring(
    tmp_path, monkeypatch
):
    from SafetyFunctions import SafetyFunctions
    from build_app_config import compile_config
    from components.core.functional_safety_diagnostics import (
        JsonFunctionalSafetyDiagnosticsStore,
    )

    monkeypatch.setattr("SafetyFunctions.SafetyHomeApiGateway.start", lambda self: None)
    monkeypatch.setattr(
        "SafetyFunctions.JsonFunctionalSafetyDiagnosticsStore",
        lambda: JsonFunctionalSafetyDiagnosticsStore(
            tmp_path / "functional_safety.json"
        ),
    )
    raw = compile_config(
        user_path=Path(__file__).parents[1] / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0},
    )["SafetyFunctions"]
    raw["app_config"]["validation"]["validate_entity_existence"] = False
    raw["user_config"]["components_enabled"] = {
        name: name == "HeatingSystemMonitorComponent"
        for name in (
            *raw["user_config"]["safety_components"],
            "HeatingSystemMonitorComponent",
        )
    }
    raw["user_config"]["safety_components"][
        "HeatingSystemMonitorComponent"
    ] = HeatingConfig(
        state_file=str(tmp_path / "heating.json"),
        systems={
            "Main": {
                "friendly_name": "Kotłownia",
                "inputs": {"flow_temperature": binding(unit="°C")},
            }
        },
    ).model_dump()
    raw["user_config"]["notification"]["persistence"]["state_file"] = str(
        tmp_path / "notifications.json"
    )
    raw["user_config"]["recovery"]["persistence"]["state_file"] = str(
        tmp_path / "recovery.json"
    )
    raw["app_config"]["fault_evidence"]["state_file"] = str(tmp_path / "evidence.json")
    calibration = raw["app_config"]["calibration"]["functional_safety"]
    for key in (
        "battery_fault_catalog_file",
        "periodic_test_state_file",
        "detector_test_state_file",
    ):
        calibration[key] = str(tmp_path / f"{key}.json")
    app = SafetyFunctions(args=raw)
    app.run_in = lambda callback, delay, **kwargs: (callback, delay, kwargs)
    app.get_state = lambda *args, **kwargs: {
        "state": "30",
        "attributes": {"unit_of_measurement": "°C"},
    }
    app.render_template = lambda *args, **kwargs: "Kotłownia"
    app.call_service = MagicMock()
    app.log = MagicMock()
    app.initialize()
    assert hasattr(app, "degradation"), app.log.call_args_list
    assert app.degradation.binding_errors == {}
    assert "HeatingSupervisionLoss" in app.fm.faults
    app.sm_modules["HeatingSystemMonitorComponent"]._tick()
    assert (
        app.sm_modules["HeatingSystemMonitorComponent"]._store.database
        is app.state_database
    )
    assert all(
        call.args[0] == "mqtt/publish" for call in app.call_service.call_args_list
    )
    app.terminate()
