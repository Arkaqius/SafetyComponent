"""Contract tests for independent internal binary hazard alarms."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock

import pytest

from components.core.event_bus import EventBus
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.sqlite_state_store import SqliteStateDatabase
from components.core.types_common import FaultState, SMState
from components.safetycomponents.internal_environmental_hazard.internal_environmental_hazard_monitor_component import (
    InternalEnvironmentalHazardMonitorComponent,
)
from components.safetycomponents.internal_environmental_hazard.state_store import (
    InMemoryInternalEnvironmentStateStore,
    IndoorStateOwner, commissioned_checkpoint, current_launch_id,
)
from components.core.snapshot_writer import SnapshotWriter
from safety_lifecycle_support import ControlledExecutor


GAS_ENTITY = "binary_sensor.bathroom_gasleak_detector"
CO_ENTITY = "binary_sensor.bathroom_carbonoxide_detector"
LEAK_ENTITY = "binary_sensor.utility_water_leak"


def _configuration(*, health_failure_seconds: int = 5, include_leak: bool = False) -> dict:
    config = {
        "profiles": {
            "binary": {
                "version": "1.0",
                "provenance": "test contract",
                "alarm_states": ["on"],
                "clear_states": ["off"],
                "test_states": ["test"],
                "unavailable_states": ["unknown", "unavailable"],
                "clear_duration_seconds": 30,
                "authoritative_clear": True,
                "clear_event_contract": "ha_state_changed_v1",
                "hush_states": ["hush"],
            }
        },
        "detectors": {
            "BathroomFlammableGas": {
                "area_id": "bathroom",
                "area_name": "Łazienka",
                "entity_id": GAS_ENTITY,
                "friendly_name": "Czujnik gazu w łazience",
                "hazard": "flammable_gas",
                "profile": "binary",
                "gas_identity": "flammable_gas_unspecified",
                "enabled": True,
            },
            "BathroomCarbonMonoxide": {
                "area_id": "bathroom",
                "area_name": "Łazienka",
                "entity_id": CO_ENTITY,
                "friendly_name": "Czujnik tlenku węgla w łazience",
                "hazard": "carbon_monoxide",
                "profile": "binary",
                "enabled": True,
            },
        },
        "health_failure_debounce_seconds": health_failure_seconds,
        "health_recovery_debounce_seconds": 60,
        "persistence": {
            "enabled": False,
            "state_file": "unused.json",
            "maximum_detectors": 8,
        },
    }
    if include_leak:
        config["detectors"]["UtilityLeak"] = {
            "area_id": "utility",
            "entity_id": LEAK_ENTITY,
            "friendly_name": "Utility leak",
            "hazard": "water_leak",
            "profile": "binary",
            "enabled": True,
        }
    return config


def _snapshot(state: str, at: datetime) -> dict:
    return {
        "state": state,
        "last_changed": at.isoformat(),
        "last_updated": at.isoformat(),
        "attributes": {},
    }


def _build_component(
    states: dict[str, dict],
    *,
    now: datetime,
    health_failure_seconds: int = 5,
    include_leak: bool = False,
    hazard_override: str | None = None,
) -> tuple[InternalEnvironmentalHazardMonitorComponent, MagicMock, list[dict]]:
    hass_app = MagicMock()
    executor = ControlledExecutor()
    hass_app.indoor_state_owner = IndoorStateOwner(InMemoryInternalEnvironmentStateStore(
        commissioned_checkpoint("reviewed-component-fixture", now)), writer=SnapshotWriter(executor), launch_receipt=current_launch_id())
    hass_app.indoor_state_owner.begin()
    executor.finish(0)
    hass_app.indoor_state_owner.drain()
    hass_app._indoor_test_executor = executor
    hass_app.localizer = None
    hass_app.get_state.side_effect = lambda entity_id, **_kwargs: states.get(entity_id)
    hass_app.run_in.side_effect = lambda callback, delay, **kwargs: (
        callback,
        delay,
        kwargs,
    )
    event_bus = EventBus()
    events: list[dict] = []
    event_bus.subscribe("symptom", lambda **payload: events.append(payload))
    component = InternalEnvironmentalHazardMonitorComponent(
        hass_app,
        MagicMock(),
        event_bus,
        MqttEntityManager(hass_app),
    )
    component._now = lambda: now  # type: ignore[method-assign]
    component._monotonic = lambda: 0.0
    config = _configuration(health_failure_seconds=health_failure_seconds, include_leak=include_leak)
    if hazard_override is not None:
        config["detectors"]["BathroomFlammableGas"]["hazard"] = hazard_override
        if hazard_override != "flammable_gas":
            config["detectors"]["BathroomFlammableGas"].pop("gas_identity")
    symptoms, recovery = component.get_symptoms_data(
        {component.component_name: component},
        config,
    )
    assert set(recovery) == set(symptoms)
    for symptom in symptoms.values():
        assert component.init_safety_mechanism(
            symptom.sm_name, symptom.name, symptom.parameters
        )
        assert component.enable_safety_mechanism(symptom.name, SMState.ENABLED)
    events.clear()
    hass_app.reset_mock()
    hass_app.get_state.side_effect = lambda entity_id, **_kwargs: states.get(entity_id)
    hass_app.run_in.side_effect = lambda callback, delay, **kwargs: (
        callback,
        delay,
        kwargs,
    )
    return component, hass_app, events


def _event(events: list[dict], symptom_id: str) -> dict:
    return next(event for event in reversed(events) if event["symptom_id"] == symptom_id)


def _live(component, entity, old, new, *, context="fixture-edge"):
    component._now = lambda: datetime.fromisoformat(new["last_updated"])
    component._source_event("state_changed", dict(entity_id=entity, old_state=old, new_state=new,
        metadata=dict(origin="LOCAL", time_fired=new["last_updated"], context=dict(id=context))))


def _expire(component, key):
    candidate = component._detectors[key].authority.candidate
    assert candidate is not None
    component._alarm_clear_elapsed(detector_key=key, candidate_token=candidate.token)
    executor = component.hass_app._indoor_test_executor
    # Finish only storage: no source/qualification timer or wall time advances.
    for _ in range(5):
        for index, (future, _, _) in enumerate(tuple(executor.jobs)):
            if not future.done():
                executor.finish(index)
        component._drain_state()


def test_device_contact_does_not_clear_a_latched_water_alarm_with_unknown_state() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {LEAK_ENTITY: _snapshot("on", now)}
    component, _, events = _build_component(states, now=now, include_leak=True)
    alarm = component.safety_mechanisms["InternalEnv_water_leak_UtilityLeak"]
    assert component.sm_iehm_water_leak(alarm)
    states[LEAK_ENTITY] = {**_snapshot("unknown", now), "last_contact_at": now.isoformat()}
    events.clear()
    assert component.sm_iehm_water_leak(alarm)
    assert component._detectors["UtilityLeak"].alarm_active
    assert not any(event["symptom_id"] == alarm.name and event["state"] == FaultState.CLEARED for event in events)


def test_flammable_gas_alarm_sets_independently_of_normal_co_detector() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, events = _build_component(states, now=now)

    gas = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    co = component.safety_mechanisms[
        "InternalEnv_carbon_monoxide_BathroomCarbonMonoxide"
    ]
    assert component.sm_iehm_flammable_gas(gas) is True
    assert component.sm_iehm_carbon_monoxide(co) is False

    gas_event = _event(
        events, "InternalEnv_flammable_gas_BathroomFlammableGas"
    )
    assert gas_event["state"] == FaultState.SET
    assert gas_event["additional_info"]["hazard"] == "flammable gas"
    assert gas_event["additional_info"]["gas_identity"] == (
        "flammable_gas_unspecified"
    )
    non_mqtt_calls = [
        call
        for call in hass_app.call_service.call_args_list
        if not call.args or call.args[0] != "mqtt/publish"
    ]
    assert non_mqtt_calls == []


def test_co_binary_alarm_does_not_require_numeric_measurement() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("on", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_carbon_monoxide_BathroomCarbonMonoxide"
    ]

    assert component.sm_iehm_carbon_monoxide(mechanism) is True
    event = _event(events, mechanism.name)
    assert event["state"] == FaultState.SET
    assert "observed_value" not in event["additional_info"]


def test_water_leak_alarm_latches_independently_without_actuation() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("off", now),
        LEAK_ENTITY: _snapshot("on", now),
    }
    component, hass_app, events = _build_component(states, now=now, include_leak=True)
    leak_name = "InternalEnv_water_leak_UtilityLeak"
    assert component.sm_iehm_water_leak(component.safety_mechanisms[leak_name]) is True
    assert _event(events, leak_name)["state"] == FaultState.SET
    assert _event(events, leak_name)["additional_info"]["hazard"] == "water leak"
    assert component.get_output_inhibitions() == ()
    assert [call for call in hass_app.call_service.call_args_list if not call.args or call.args[0] != "mqtt/publish"] == []


def test_water_leak_unavailable_does_not_clear_until_authoritative_off() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("off", now),
        LEAK_ENTITY: _snapshot("on", now),
    }
    component, _hass_app, events = _build_component(states, now=now, include_leak=True)
    leak_name = "InternalEnv_water_leak_UtilityLeak"
    mechanism = component.safety_mechanisms[leak_name]
    assert component.sm_iehm_water_leak(mechanism)

    states[LEAK_ENTITY] = _snapshot("unavailable", now)
    assert component.sm_iehm_water_leak(mechanism)
    assert _event(events, leak_name)["state"] == FaultState.SET

    clear_at = now + timedelta(seconds=1)
    states[LEAK_ENTITY] = _snapshot("off", clear_at)
    component._now = lambda: clear_at  # type: ignore[method-assign]
    assert component.sm_iehm_water_leak(mechanism)
    component._now = lambda: clear_at + timedelta(seconds=30)  # type: ignore[method-assign]
    component._alarm_clear_elapsed(detector_key="UtilityLeak")
    assert _event(events, leak_name)["state"] == FaultState.SET
    assert component._detectors["UtilityLeak"].authority.candidate is None
    alarm_at = clear_at + timedelta(seconds=31)
    prior = states[LEAK_ENTITY]
    states[LEAK_ENTITY] = _snapshot("on", alarm_at)
    _live(component, LEAK_ENTITY, prior, states[LEAK_ENTITY])
    prior = states[LEAK_ENTITY]
    states[LEAK_ENTITY] = _snapshot("off", alarm_at + timedelta(seconds=1))
    component._monotonic = lambda: 1.0
    _live(component, LEAK_ENTITY, prior, states[LEAK_ENTITY])
    component._monotonic = lambda: 31.0
    _expire(component, "UtilityLeak")
    assert _event(events, leak_name)["state"] == FaultState.CLEARED


def test_unavailable_or_test_state_never_clears_active_alarm() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)

    states[GAS_ENTITY] = _snapshot("unknown", now)
    component.sm_iehm_flammable_gas(mechanism)
    states[GAS_ENTITY] = _snapshot("test", now)
    component.sm_iehm_flammable_gas(mechanism)

    assert component._detectors["BathroomFlammableGas"].alarm_active is True
    assert [event["state"] for event in events if event["symptom_id"] == mechanism.name] == [
        FaultState.SET
    ]
    hass_app.cancel_timer.assert_not_called()


def test_state_event_latches_alarm_edge_without_rereading_newer_clear() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("off", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)

    component._entity_changed(
        GAS_ENTITY,
        "all",
        _snapshot("off", now),
        _snapshot("on", now),
    )

    event = _event(
        events, "InternalEnv_flammable_gas_BathroomFlammableGas"
    )
    assert event["state"] == FaultState.SET
    assert component._detectors["BathroomFlammableGas"].alarm_active is True


def test_authoritative_clear_requires_full_profile_interval() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)

    clear_at = now + timedelta(seconds=1)
    states[GAS_ENTITY] = _snapshot("off", clear_at)
    component._now = lambda: clear_at  # type: ignore[method-assign]
    component.sm_iehm_flammable_gas(mechanism)
    assert component._detectors["BathroomFlammableGas"].alarm_active is True
    component._monotonic = lambda: 1.0
    _live(component, GAS_ENTITY, _snapshot("on", now), states[GAS_ENTITY])
    component._monotonic = lambda: 30.999
    _expire(component, "BathroomFlammableGas")
    assert component._detectors["BathroomFlammableGas"].alarm_active is True

    component._now = lambda: clear_at + timedelta(seconds=30)  # type: ignore[method-assign]
    component._monotonic = lambda: 31.0
    _expire(component, "BathroomFlammableGas")

    assert component._detectors["BathroomFlammableGas"].alarm_active is False
    assert _event(events, mechanism.name)["state"] == FaultState.CLEARED
    assert component._detectors["BathroomFlammableGas"].gas_switching_inhibited is True


@pytest.mark.parametrize("hazard", ["smoke", "flammable_gas", "carbon_monoxide", "water_leak"])
def test_old_off_cannot_erase_fresh_alarm_and_live_clear_requires_thirty_seconds(hazard):
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    states = {GAS_ENTITY: _snapshot("on", now), CO_ENTITY: _snapshot("off", now)}
    component, _, events = _build_component(states, now=now, hazard_override=hazard)
    runtime = component._detectors["BathroomFlammableGas"]
    mechanism = component.safety_mechanisms[f"InternalEnv_{hazard}_BathroomFlammableGas"]
    component._evaluate_mechanism(mechanism)
    states[GAS_ENTITY] = _snapshot("off", now - timedelta(days=1))
    component._evaluate_mechanism(mechanism)
    assert runtime.alarm_active and runtime.authority.candidate is None
    _live(component, GAS_ENTITY, states[GAS_ENTITY], states[GAS_ENTITY])
    assert runtime.authority.candidate is None
    # A fresh positive reestablishes the exact source watermark after ambiguity.
    states[GAS_ENTITY] = _snapshot("on", now + timedelta(seconds=1))
    component._evaluate_mechanism(mechanism)
    prior = states[GAS_ENTITY]
    states[GAS_ENTITY] = _snapshot("off", now + timedelta(seconds=2))
    component._monotonic = lambda: 2.0
    _live(component, GAS_ENTITY, prior, states[GAS_ENTITY])
    component._monotonic = lambda: 31.999
    _expire(component, runtime.key)
    assert runtime.alarm_active
    component._monotonic = lambda: 32.0
    _expire(component, runtime.key)
    assert not runtime.alarm_active
    assert _event(events, mechanism.name)["state"] == FaultState.CLEARED


@pytest.mark.parametrize("hazard", ["smoke", "flammable_gas", "carbon_monoxide", "water_leak"])
@pytest.mark.parametrize("interruption", ["unknown", "unavailable", "test", "hush", "on", "reconnect", "stop"])
def test_clear_interruption_retains_alarm_and_rejects_obsolete_timer(hazard, interruption):
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    states = {GAS_ENTITY: _snapshot("on", now), CO_ENTITY: _snapshot("off", now)}
    component, hass_app, events = _build_component(states, now=now, hazard_override=hazard)
    runtime = component._detectors["BathroomFlammableGas"]
    name = f"InternalEnv_{hazard}_BathroomFlammableGas"
    component._evaluate_mechanism(component.safety_mechanisms[name])
    prior = states[GAS_ENTITY]
    states[GAS_ENTITY] = _snapshot("off", now + timedelta(seconds=1))
    component._monotonic = lambda: 1.0
    _live(component, GAS_ENTITY, prior, states[GAS_ENTITY])
    callback, _, kwargs = hass_app.run_in.call_args.args[0], hass_app.run_in.call_args.args[1], hass_app.run_in.call_args.kwargs
    token = runtime.authority.candidate.token
    if interruption == "reconnect":
        component._source_session_changed("plugin_stopped", {})
        component._source_session_changed("plugin_started", {})
    elif interruption == "stop":
        component.stop()
        component.start()
    else:
        prior = states[GAS_ENTITY]
        states[GAS_ENTITY] = _snapshot(interruption, now + timedelta(seconds=2))
        _live(component, GAS_ENTITY, prior, states[GAS_ENTITY])
    component._monotonic = lambda: 40.0
    callback(**kwargs)
    component._alarm_clear_elapsed(detector_key=runtime.key, candidate_token=token)
    assert runtime.alarm_active
    assert not any(item["state"] == FaultState.CLEARED and item["symptom_id"] == name for item in events)


def test_reentrant_disable_during_clear_read_denies_heal():
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    states = {GAS_ENTITY: _snapshot("on", now), CO_ENTITY: _snapshot("off", now)}
    component, hass_app, _ = _build_component(states, now=now)
    runtime = component._detectors["BathroomFlammableGas"]
    mechanism = component.safety_mechanisms["InternalEnv_flammable_gas_BathroomFlammableGas"]
    component._evaluate_mechanism(mechanism)
    prior = states[GAS_ENTITY]
    states[GAS_ENTITY] = _snapshot("off", now + timedelta(seconds=1))
    _live(component, GAS_ENTITY, prior, states[GAS_ENTITY])
    component._monotonic = lambda: 30.0
    def disabling_read(*args, **kwargs):
        mechanism.isEnabled = False
        return states[GAS_ENTITY]
    hass_app.get_state.side_effect = disabling_read
    _expire(component, runtime.key)
    assert runtime.alarm_active


def test_alarm_state_is_healthy_detector_operation() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    health = component.safety_mechanisms[
        "InternalEnv_detector_health_BathroomFlammableGas"
    ]

    assert component.sm_iehm_detector_health(health) is False
    assert _event(events, health.name)["state"] == FaultState.CLEARED


def test_unavailable_detector_raises_separate_health_symptom() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("unknown", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(
        states, now=now, health_failure_seconds=0
    )
    health = component.safety_mechanisms[
        "InternalEnv_detector_health_BathroomFlammableGas"
    ]

    assert component.sm_iehm_detector_health(health) is True
    assert _event(events, health.name)["state"] == FaultState.SET
    assert component.symptom_states[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ] == FaultState.NOT_TESTED


@pytest.mark.parametrize("durable", [False, True])
def test_persisted_alarm_is_reasserted_when_current_state_is_unknown(tmp_path, durable) -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("unknown", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, _hass_app, events = _build_component(states, now=now)
    store = InMemoryInternalEnvironmentStateStore(
        {
            "version": 1,
            "detectors": {
                "BathroomFlammableGas": {
                    "alarm_active": True,
                    "health_active": False,
                    "gas_switching_inhibited": True,
                    "last_authoritative_clear_at": None,
                }
            },
        }
    )
    if durable:
        legacy = tmp_path / "internal.json"
        legacy.write_text(json.dumps(store.load()), encoding="utf-8")
        sqlite_store = SqliteStateDatabase(tmp_path / "state.sqlite3").store("internal_environment_state", legacy)
        component._state_store = sqlite_store
    else:
        component._state_store = store
    component._restore_state()
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]

    # Legacy v1 never stored original hazard/entity/profile/incident. The key
    # alone must not assign this danger to current replacement equipment.
    component.sm_iehm_flammable_gas(mechanism)
    assert any(item.kind == "legacy_unattributed" and item.alarm_active for item in component._owner.records.values())
    assert component.get_output_inhibitions() == ("active_or_unresolved_flammable_gas",)
    assert component._summary_state() == "active_hazard"


def test_group_b_dependencies_are_diagnostic_only_and_keep_stable_fault_owner() -> None:
    dependencies = (
        InternalEnvironmentalHazardMonitorComponent.get_entity_dependencies(
            _configuration()
        )
    )

    assert {item["entity_id"] for item in dependencies} == {GAS_ENTITY, CO_ENTITY}
    assert {item["fault_owner"] for item in dependencies} == {"none"}
    assert {item["detection_budget_seconds"] for item in dependencies} == {60}


def test_unconfigured_hazard_fault_is_inactive() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    component, _hass_app, _events = _build_component(
        {GAS_ENTITY: _snapshot("off", now), CO_ENTITY: _snapshot("off", now)},
        now=now,
    )

    assert component.get_inactive_fault_names() == {"InternalSmokeDetected", "WaterLeakDetected"}


def test_diagnostic_payload_keeps_alarm_and_health_separate() -> None:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    states = {
        GAS_ENTITY: _snapshot("on", now),
        CO_ENTITY: _snapshot("off", now),
    }
    component, hass_app, _events = _build_component(states, now=now)
    mechanism = component.safety_mechanisms[
        "InternalEnv_flammable_gas_BathroomFlammableGas"
    ]
    component.sm_iehm_flammable_gas(mechanism)
    payloads = [
        json.loads(call.kwargs["payload"])
        for call in hass_app.call_service.call_args_list
        if call.args
        and call.args[0] == "mqtt/publish"
        and call.kwargs.get("topic")
        == "safety_component/attributes/internal_environment_bathroom_flammable_gas"
    ]

    assert payloads[-1]["alarm_active"] is True
    assert payloads[-1]["health_fault_active"] is False
    assert payloads[-1]["gas_switching_inhibited"] is True
