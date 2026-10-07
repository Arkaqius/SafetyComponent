"""Ensure generated rate dependencies honor their sampling cadence."""

import pytest

from components.safetycomponents.temperature.temperature_component import (
    TemperatureComponent,
)
from SafetyFunctions import SafetyFunctions


@pytest.mark.parametrize("sample_minutes", [15, 30])
def test_rate_failure_budget_exceeds_first_sample_interval(sample_minutes: int) -> None:
    dependencies = TemperatureComponent.get_entity_dependencies([
        {"Office": {
            "temperature_sensor": "sensor.office_temperature",
            "SM_TC_MIN_VALID_TEMPERATURE_C": -40,
            "SM_TC_MAX_VALID_TEMPERATURE_C": 80,
            "SM_TC_2_DERIVATIVE_SAMPLE_MINUTES": sample_minutes,
        }}
    ])
    rate = next(item for item in dependencies if item["key"] == "TemperatureForecastOffice")
    assert rate["failure_debounce_seconds"] == sample_minutes * 60 + 60
    assert rate["detection_budget_seconds"] == sample_minutes * 60 + 150
    assert rate["detection_budget_seconds"] - rate["failure_debounce_seconds"] == 90

    calibrated = SafetyFunctions._calibrate_component_dependency(
        rate, {}, default_failure_debounce=15, default_recovery_debounce=15
    )
    assert calibrated["failure_debounce_seconds"] == sample_minutes * 60 + 60
    assert calibrated["detection_budget_seconds"] == sample_minutes * 60 + 150


def test_rate_failure_debounce_can_be_explicitly_overridden() -> None:
    dependency = {
        "key": "TemperatureForecastOffice",
        "failure_debounce_seconds": 960,
        "detection_budget_seconds": 960,
    }
    calibrated = SafetyFunctions._calibrate_component_dependency(
        dependency,
        {"TemperatureForecastOffice": {"failure_debounce_seconds": 30}},
        default_failure_debounce=15,
        default_recovery_debounce=15,
    )
    assert calibrated["failure_debounce_seconds"] == 30
