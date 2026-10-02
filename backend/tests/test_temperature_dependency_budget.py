"""Ensure generated rate dependencies honor their sampling cadence."""

import pytest

from components.safetycomponents.temperature.temperature_component import (
    TemperatureComponent,
)


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
    assert rate["detection_budget_seconds"] == sample_minutes * 60 + 60
