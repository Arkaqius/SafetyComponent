# tests/test_temperature_component.py
# mypy: ignore-errors

from typing import Iterator, List
import pytest
from shared.types_common import FaultState, SMState
from unittest.mock import Mock
from .fixtures.hass_fixture import (
    mock_get_state,
    MockBehavior,
    update_mocked_get_state,
)  # Import utilities from conftest.py


DEBOUNCE_LIMIT = 1


@pytest.mark.parametrize(
    "temperature, expected_symptom_state, expected_fault_state",
    [
        (
            ["35", "36", "37", "8", "9"],
            FaultState.CLEARED,
            FaultState.CLEARED,
        ),
        (
            ["5", "6", "7", "8", "9"],
            FaultState.SET,
            FaultState.SET,
        ),
    ],
)
def test_temp_comp_smtc1(
    mocked_hass_app_with_temp_component,
    temperature,
    expected_symptom_state,
    expected_fault_state,
):
    """
    Test Case: Verify symptom and fault states based on temperature input.

    Scenario:
        - Input: Temperature sequences with varying levels.
        - Expected Result: Symptom and fault states should match expected values based on temperature.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.office_temperature", iter(temperature))
    ]
    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )
    app_instance.initialize()

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice")
        == expected_symptom_state
    )
    assert app_instance.fm.check_fault("RiskyTemperature") == expected_fault_state


def test_symptom_set_when_temp_NOT_below_threshold(mocked_hass_app_with_temp_component):
    """
    Test Case: Symptom Set When Temperature is Below Threshold

    Scenario:
        - Input: Temperature sequence ["16.0", "24", "23"]
        - Expected Result: Symptom "RiskyTemperatureOffice" should be set to True.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence: List[str] = ["16.0", "24", "23"]

    test_mock_behaviours: list[MockBehavior] = [
        MockBehavior("sensor.office_temperature", iter(temperature_sequence))
    ]

    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.initialize()

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice") is FaultState.NOT_TESTED
    )


@pytest.mark.parametrize(
    "debounce_value, expected_symptom_state",
    [
        (DEBOUNCE_LIMIT, FaultState.CLEARED),  # Case where debounce limit is met
        (
            DEBOUNCE_LIMIT - 1,
            FaultState.NOT_TESTED,
        ),  # Case where debounce limit is not met
    ],
)
def test_symptom_cleared_when_temp_above_threshold(
    mocked_hass_app_with_temp_component, debounce_value, expected_symptom_state
):
    """
    Test Case: Symptom Cleared When Temperature is Above Threshold

    Scenario:
        - Input: Temperature sequence ["20.0", "21.0", "22.0"]
        - Expected Result: Symptom "RiskyTemperatureOffice" should be cleared.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["20.0", "21.0", "22.0", "22.0"]

    test_mock_behaviours = [
        MockBehavior("sensor.office_temperature", iter(temperature_sequence))
    ]
    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        mock_behaviors_default,
    )

    app_instance.initialize()

    for _ in range(debounce_value):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice")
        is expected_symptom_state
    )


def test_symptom_cleared_when_temp_above_threshold_less_than_debounce(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Symptom Cleared When Temperature is Above Threshold

    Scenario:
        - Input: Temperature sequence ["20.0", "21.0", "22.0"]
        - Expected Result: Symptom "RiskyTemperatureOffice" should be cleared.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["20.0", "21.0", "22.0", "22.0"]

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.office_temperature", iter(temperature_sequence))
    ]
    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        mock_behaviors_default,
    )

    app_instance.initialize()

    for _ in range(DEBOUNCE_LIMIT - 1):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice") is FaultState.NOT_TESTED
    )


def test_forecasted_symptom_set_when_temp_rate_indicates_drop(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Forecasted Symptom Set When Temperature Rate Indicates a Drop

    Scenario:
        - Input: Initial temperature is 20.0°C, rate is -0.1°C/min, and forecast timespan is 2 hours.
        - Expected Result: Symptom "RiskyTemperatureOfficeForeCast" should be set to True.
    """
    app_instance, __, _, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["20.0"]
    rate_of_change = "-1"  # degrees per 15 minute

    # Initialize the application and register the monitored entity in DerivativeMonitor
    app_instance.initialize()
    app_instance.derivative_monitor.register_entity(
        "sensor.office_temperature",
        sample_time=60*15,  # Sampling every 1 minute
        low_saturation=-10.0,
        high_saturation=10.0,
    )

    # Mock the states for temperature and rate
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [
            MockBehavior("sensor.office_temperature", iter(temperature_sequence)),
            MockBehavior("sensor.office_temperature_rate", iter([rate_of_change])),
        ],
    )

    # Simulate multiple iterations to reach the debounce limit
    for _ in range(DEBOUNCE_LIMIT):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_2(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOfficeForeCast"
            ]
        )

    # Assert the symptom state
    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOfficeForeCast")
        is FaultState.SET
    )



@pytest.mark.parametrize(
    "debounce_value, expected_symptom_state",
    [
        (DEBOUNCE_LIMIT, FaultState.CLEARED),  # Case where debounce limit is met
        (
            DEBOUNCE_LIMIT - 1,
            FaultState.NOT_TESTED,
        ),  # Case where debounce limit is not met
    ],
)
def test_forecasted_symptom_cleared_when_temp_rate_indicates_stability(
    mocked_hass_app_with_temp_component, debounce_value, expected_symptom_state
):
    """
    Test Case: Forecasted Symptom Cleared When Temperature Rate Indicates Stability

    Scenario:
        - Input: Initial temperature is 20.0°C, rate is 0.1°C/min, and forecast timespan is 2 hours.
        - Parametrized with debounce_value and expected_symptom_state.
        - Expected Result: Symptom "RiskyTemperatureOfficeForeCast" should be cleared when debounce limit is met.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["20.0"]
    rate_of_change = "0.5"  # degrees per minute

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [
            MockBehavior("sensor.office_temperature", iter(temperature_sequence)),
            MockBehavior("sensor.office_temperature_rate", iter([rate_of_change])),
        ],
    )

    app_instance.initialize()

    for _ in range(debounce_value):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_2(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOfficeForeCast"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOfficeForeCast")
        == expected_symptom_state
    )


def test_safety_mechanism_disabled_does_not_trigger_symptom(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Safety Mechanism Disabled Does Not Trigger Symptom

    Scenario:
        - Input: Temperature is 15.0°C, and the mechanism is disabled.
        - Expected Result: Symptom state should remain unchanged.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["15.0"]

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.office_temperature", iter(temperature_sequence))
    ]
    mock_behaviors_default: List[MockBehavior] = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        mock_behaviors_default,
    )

    app_instance.initialize()

    # Disable the safety mechanism
    app_instance.fm.enable_sm("RiskyTemperatureOffice", SMState.DISABLED)

    for _ in range(DEBOUNCE_LIMIT):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureOffice"
            ]
        )

    # Check that no symptom was set since the mechanism was disabled
    assert (
        app_instance.fm.check_symptom("RiskyTemperatureOffice") is FaultState.NOT_TESTED
    )


def test_initialize_dicts_symptom(mocked_hass_app_with_temp_component):
    """
    Test Case: Initialization of Symptom Dictionaries

    Scenario:
        - Input: Initialization of the app instance.
        - Expected Result: Validate that the symptom, fault, and notification configurations are correctly populated.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.initialize()

    # Validate initialization
    symptom = app_instance.symptoms["RiskyTemperatureOffice"]
    assert symptom.name == "RiskyTemperatureOffice"
    assert symptom.sm_name == "sm_tc_1"
    assert symptom.parameters["CAL_LOW_TEMP_THRESHOLD"] == 18.0

    fault = app_instance.fault_dict["RiskyTemperature"]
    assert fault["name"] == "Unsafe temperature"
    assert fault["level"] == 2
    assert fault["related_sms"][0] == "sm_tc_1"

    notification = app_instance.notification_cfg
    assert notification["light_entity"] == "light.warning_light"