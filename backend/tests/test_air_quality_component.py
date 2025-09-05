# tests/test_air_quality_component.py
# mypy: ignore-errors

from unittest.mock import MagicMock

from shared.air_quality_component import AirQualityComponent
from shared.common_entities import CommonEntities


def _create_component(aqi_value: str):
    hass = MagicMock()
    hass.get_state.return_value = aqi_value
    common = CommonEntities(hass, {"outside_temp": "sensor.outside"})
    component = AirQualityComponent(hass, common)
    return component, hass


def test_get_symptoms_data_creates_entries():
    component, _ = _create_component("50")
    sm_modules = {"AirQualityComponent": component}
    cfg = [{"Office": {"CAL_AQI_THRESHOLD": 100, "aqi_sensor": "sensor.office_aqi"}}]
    symptoms, recoveries = component.get_symptoms_data(sm_modules, cfg)
    assert "PoorAirQualityOffice" in symptoms
    assert "PoorAirQualityOffice" in recoveries


def test_sm_aq_1_triggers_on_high_aqi():
    component, hass = _create_component("150")
    component.init_safety_mechanism(
        "sm_aq_1",
        "PoorAirQualityOffice",
        {
            "CAL_AQI_THRESHOLD": 100,
            "aqi_sensor": "sensor.office_aqi",
            "location": "Office",
        },
    )
    sm = component.safety_mechanisms["PoorAirQualityOffice"]
    result = component.sm_aq_1(sm)
    assert result is True


def test_sm_aq_1_not_trigger_on_low_aqi():
    component, hass = _create_component("50")
    component.init_safety_mechanism(
        "sm_aq_1",
        "PoorAirQualityOffice",
        {
            "CAL_AQI_THRESHOLD": 100,
            "aqi_sensor": "sensor.office_aqi",
            "location": "Office",
        },
    )
    sm = component.safety_mechanisms["PoorAirQualityOffice"]
    result = component.sm_aq_1(sm)
    assert result is False
