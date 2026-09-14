"""Validation tests for internal environmental detector configuration."""

from unittest.mock import MagicMock

import pytest

from components.safetycomponents.internal_environmental_hazard.schema import (
    validate_internal_environmental_hazard_config,
)


def _config() -> dict:
    return {
        "profiles": {
            "binary": {
                "version": "1.0",
                "provenance": "test contract",
                "alarm_states": ["ON"],
                "clear_states": ["OFF"],
                "test_states": ["test"],
                "unavailable_states": ["unknown", "unavailable"],
                "clear_duration_seconds": 30,
                "authoritative_clear": True,
            }
        },
        "detectors": {
            "BathroomGas": {
                "area_id": "bathroom",
                "entity_id": "binary_sensor.bathroom_gas",
                "friendly_name": "Bathroom gas detector",
                "hazard": "flammable_gas",
                "profile": "binary",
                "gas_identity": "LPG",
            }
        },
        "health_failure_debounce_seconds": 5,
        "health_recovery_debounce_seconds": 60,
        "persistence": {
            "enabled": False,
            "state_file": "unused.json",
            "maximum_detectors": 4,
        },
    }


def test_schema_normalizes_states_and_gas_identity() -> None:
    runtime = validate_internal_environmental_hazard_config(_config())

    assert runtime["profiles"]["binary"]["alarm_states"] == ["on"]
    assert runtime["detectors"]["BathroomGas"]["gas_identity"] == "lpg"


def test_schema_rejects_overlapping_state_meanings() -> None:
    config = _config()
    config["profiles"]["binary"]["clear_states"] = ["on"]

    with pytest.raises(ValueError, match="overlap"):
        validate_internal_environmental_hazard_config(config)


def test_schema_requires_gas_identity_only_for_flammable_gas() -> None:
    missing = _config()
    missing["detectors"]["BathroomGas"].pop("gas_identity")
    with pytest.raises(ValueError, match="gas_identity"):
        validate_internal_environmental_hazard_config(missing)

    wrong_channel = _config()
    wrong_channel["detectors"]["BathroomGas"]["hazard"] = "carbon_monoxide"
    with pytest.raises(ValueError, match="gas_identity"):
        validate_internal_environmental_hazard_config(wrong_channel)


@pytest.mark.parametrize("detector_key", ["Bathroom_Gas", "bathroom-gas", "żółty"])
def test_schema_rejects_non_alphanumeric_detector_keys(detector_key: str) -> None:
    config = _config()
    config["detectors"][detector_key] = config["detectors"].pop("BathroomGas")

    with pytest.raises(ValueError, match="ASCII letters and digits"):
        validate_internal_environmental_hazard_config(config)


def test_nonstrict_schema_logs_nested_extra_keys() -> None:
    config = _config()
    config["future_component"] = True
    config["profiles"]["binary"]["future_profile"] = True
    config["detectors"]["BathroomGas"]["future_detector"] = True
    log = MagicMock()

    validate_internal_environmental_hazard_config(
        config, strict_validation=False, log=log
    )

    assert log.call_count >= 3
