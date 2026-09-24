"""End-to-end startup wiring for the configured internal hazard monitor."""

from pathlib import Path
from typing import Any

from build_app_config import compile_config
from SafetyFunctions import SafetyFunctions
from components.core.types_common import FaultState


def test_gas_alarm_reaches_l1_fault_without_co_consensus(tmp_path) -> None:
    backend_dir = Path(__file__).parents[1]
    raw = compile_config(
        user_path=backend_dir / "config" / "user_config.example.yml",
        home_assistant_config={"latitude": 50.0, "longitude": 20.0},
    )["SafetyFunctions"]
    raw["app_config"]["validation"]["validate_entity_existence"] = False
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

    app.initialize()

    assert app.fm.check_fault("InternalFlammableGasDetected") == FaultState.SET
    assert app.fm.check_fault("InternalCarbonMonoxideDetected") != FaultState.SET
    assert "InternalSmokeDetected" not in app.faults
    assert "sensor.fault_internalsmokedetected" not in (
        app.mqtt_entities.discovered_entities
    )
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
