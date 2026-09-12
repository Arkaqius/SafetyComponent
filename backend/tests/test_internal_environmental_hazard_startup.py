"""End-to-end startup wiring for the configured internal hazard monitor."""

from pathlib import Path
from typing import Any

import yaml

from SafetyFunctions import SafetyFunctions
from components.core.types_common import FaultState


def test_gas_alarm_reaches_l1_fault_without_co_consensus(tmp_path) -> None:
    raw = yaml.safe_load(
        (Path(__file__).parents[1] / "app_cfg.yaml").read_text(encoding="utf-8")
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
    internal["persistence"]["state_file"] = str(tmp_path / "internal.json")
    app = SafetyFunctions(args=raw)
    service_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_state(entity_id: str, **_: Any) -> Any:
        if entity_id == "binary_sensor.bathroom_gasleak_detector_gas":
            return "on"
        if entity_id == "binary_sensor.bathroom_carbonoxide_detector_carbon_monoxide":
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
    assert app.faults["InternalFlammableGasDetected"].level == 1
    assert any(service == "notify/all_phones" for service, _kwargs in service_calls)
    assert "InternalEnvironmentBathroomFlammableGas" in app.sm_modules[
        "EntityMonitorComponent"
    ]._entities
    assert not any(
        symptom.startswith(
            "EntityHealthFailureInternalEnvironmentBathroomFlammableGas"
        )
        for symptom in app.symptoms
    )
    assert not any(
        service.startswith(("light/", "switch/", "fan/", "valve/"))
        for service, _kwargs in service_calls
    )
