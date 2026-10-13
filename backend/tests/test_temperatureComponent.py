# tests/test_temperature_component.py
# mypy: ignore-errors

from typing import Iterator, List
from copy import deepcopy
from datetime import datetime
import pytest
from components.core.fault_state_policy import FaultEvaluationStatus
from components.core.types_common import FaultState, SMState
from .fixtures.hass_fixture import (
    mock_get_state,
    MockBehavior,
    update_mocked_get_state,
)  # Import utilities from conftest.py


DEBOUNCE_LIMIT = 1


@pytest.mark.parametrize(
    "name, kind, temperature, rate, threshold, modeled",
    [
        ("RiskyTemperatureOfficeForeCast", "low", "20.26", "-0.019", 18, 17.98),
        ("RiskyTemperatureHighOfficeForeCast", "high", "25.74", "0.019", 28, 28.02),
    ],
)
def test_forecast_evidence_explains_risk_with_available_inputs_and_retains_fault_on_loss(
    mocked_hass_app_with_temp_component,
    name, kind, temperature, rate, threshold, modeled,
):
    """Available numeric rate inputs can predict risk; later loss cannot heal it."""
    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    component = app.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms[name]
    mechanism.sm_args.update(cold_thr=18, hot_thr=28, forecast_timespan=2, debounce_limit=1)
    component.debounce_states[name] = type(component.debounce_states[name])(0, False)
    states = {"sensor.office_temperature": temperature, "sensor.office_temperature_rate": rate}
    app.get_state.side_effect = lambda entity_id, **kwargs: states.get(entity_id)
    sensor_id = f"sensor.office_temperature_{kind}_threshold"

    for _ in range(2):
        mechanism.callback(mechanism)
    evidence = component.mqtt_entities.entity_attributes[sensor_id]["forecast_evaluation"]
    assert evidence["status"] == "risk"
    assert evidence["symptom_id"] == name
    assert evidence["modeled_temperature_c"] == pytest.approx(modeled)
    assert evidence["temperature_c"] == float(temperature)
    assert evidence["rate_per_minute"] == float(rate)
    assert evidence["threshold_c"] == threshold
    assert evidence["forecast_timespan_hours"] == 2
    assert datetime.fromisoformat(evidence["evaluated_at"]).utcoffset().total_seconds() == 0
    assert app.fm.check_fault("RiskyTemperatureForecast") is FaultEvaluationStatus.FAIL

    states["sensor.office_temperature_rate"] = "unavailable"
    mechanism.callback(mechanism)
    evidence = component.mqtt_entities.entity_attributes[sensor_id]["forecast_evaluation"]
    assert evidence["status"] == "unevaluable"
    assert evidence["modeled_temperature_c"] is None
    assert evidence["rate_per_minute"] is None
    assert app.fm.check_symptom(name) is FaultState.SET
    assert app.fm.check_fault("RiskyTemperatureForecast") is FaultEvaluationStatus.UNEVALUABLE


def test_simulated_forecast_cannot_replace_last_live_assessment(
    mocked_hass_app_with_temp_component,
):
    """A synthetic safe predicate cannot overwrite live risk evidence or fault state."""
    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    component = app.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms["RiskyTemperatureOfficeForeCast"]
    mechanism.sm_args.update(cold_thr=18, forecast_timespan=2, debounce_limit=1)
    component.debounce_states[mechanism.name] = type(component.debounce_states[mechanism.name])(0, False)
    states = {"sensor.office_temperature": "20.26", "sensor.office_temperature_rate": "-0.019"}
    app.get_state.side_effect = lambda entity_id, **kwargs: states.get(entity_id)
    for _ in range(2):
        mechanism.callback(mechanism)
    sensor_id = "sensor.office_temperature_low_threshold"
    original = deepcopy(component.mqtt_entities.entity_attributes[sensor_id])
    mechanism.callback(mechanism, entities_changes={
        "sensor.office_temperature": "22", "sensor.office_temperature_rate": "0",
    })
    assert component.mqtt_entities.entity_attributes[sensor_id] == original
    assert app.fm.check_symptom(mechanism.name) is FaultState.SET


def test_forecast_publication_failure_cannot_block_hazard_qualification(
    mocked_hass_app_with_temp_component, monkeypatch,
):
    """Extra diagnostic output must not stop a valid safety predicate from qualifying."""
    app, *_ = mocked_hass_app_with_temp_component
    app.initialize()
    component = app.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms["RiskyTemperatureOfficeForeCast"]
    mechanism.sm_args.update(cold_thr=18, forecast_timespan=2, debounce_limit=1)
    component.debounce_states[mechanism.name] = type(component.debounce_states[mechanism.name])(0, False)
    states = {"sensor.office_temperature": "20.26", "sensor.office_temperature_rate": "-0.019"}
    app.get_state.side_effect = lambda entity_id, **kwargs: states.get(entity_id)

    def fail_publication(sensor_id):
        raise OSError("diagnostic transport failed")

    monkeypatch.setattr(component, "_publish_temperature_threshold", fail_publication)
    for _ in range(2):
        mechanism.callback(mechanism)
    assert app.fm.check_fault("RiskyTemperatureForecast") is FaultEvaluationStatus.FAIL


@pytest.mark.parametrize("name, rate, expected", [
    ("RiskyTemperatureOfficeForeCast", "0", FaultState.CLEARED),
    ("RiskyTemperatureHighOfficeForeCast", "0", FaultState.CLEARED),
    ("RiskyTemperatureOfficeForeCast", "-0.04", FaultState.SET),
    ("RiskyTemperatureHighOfficeForeCast", "0.04", FaultState.SET),
])
def test_forecast_requalifies_on_rate_change_without_temperature_change(
    mocked_hass_app_with_temp_component, name, rate, expected,
):
    """Rate availability alone must trigger a new forecast evaluation."""
    app, _, _, _, _ = mocked_hass_app_with_temp_component
    app.initialize()
    component = app.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms[name]
    mechanism.sm_args.update(cold_thr=18, hot_thr=26, debounce_limit=1)
    component.debounce_states[name] = type(component.debounce_states[name])(0, False)
    states = {"sensor.office_temperature": "22", "sensor.office_temperature_rate": "unknown"}
    app.get_state.side_effect = lambda entity_id, **kwargs: states.get(entity_id)
    mechanism.callback(mechanism)
    assert app.fm.check_fault("RiskyTemperatureForecast") == FaultEvaluationStatus.UNEVALUABLE
    listeners = [
        call.args[0] for call in app.listen_state.call_args_list
        if len(call.args) > 1 and call.args[1] == "sensor.office_temperature_rate"
        and getattr(call.args[0], "__self__", None) is mechanism
    ]
    assert len(listeners) == 1
    states["sensor.office_temperature_rate"] = rate
    listeners[0]("sensor.office_temperature_rate", "state", "unknown", rate)
    assert app.fm.check_symptom(name) == expected
    states["sensor.office_temperature_rate"] = "unavailable"
    listeners[0]("sensor.office_temperature_rate", "state", rate, "unavailable")
    assert app.fm.check_fault("RiskyTemperatureForecast") == FaultEvaluationStatus.UNEVALUABLE
    assert app.fm.check_symptom(name) == expected


@pytest.mark.parametrize(
    "temperature, expected_symptom_state, expected_fault_state",
    [
        (
            ["35", "36", "37", "8", "9"],
            FaultState.CLEARED,
            FaultEvaluationStatus.PASS,
        ),
        (
            ["5", "6", "7", "8", "9"],
            FaultState.SET,
            FaultEvaluationStatus.FAIL,
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


@pytest.mark.parametrize(
    "temperature, expected_symptom_state, expected_fault_state",
    [
        (
            ["20", "21", "22", "23", "24"],
            FaultState.CLEARED,
            FaultEvaluationStatus.PASS,
        ),
        (
            ["30", "31", "32", "33", "34"],
            FaultState.SET,
            FaultEvaluationStatus.FAIL,
        ),
    ],
)
def test_temp_comp_smtc3(
    mocked_hass_app_with_temp_component,
    temperature,
    expected_symptom_state,
    expected_fault_state,
):
    """
    Test Case: Verify overtemperature symptom and fault states based on temperature input.

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
        app_instance.sm_modules["TemperatureComponent"].sm_tc_3(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOffice")
        == expected_symptom_state
    )
    assert app_instance.fm.check_fault("RiskyTemperature") == expected_fault_state


def test_temp_comp_overtemp_and_undertemp_multi_room_fault_clear(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Shared fault stays SET until all high/low symptoms clear across rooms.
    """
    app_instance, _, __, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.initialize()

    # Set Office overtemperature and Kitchen undertemperature
    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.office_temperature", iter(["30"])),
        MockBehavior("sensor.kitchen_temperature", iter(["5"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_3(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOffice"
            ]
        )
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureKitchen"
            ]
        )

    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.FAIL

    # Clear Office overtemperature, Kitchen still low
    test_mock_behaviours = [
        MockBehavior("sensor.office_temperature", iter(["20"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_3(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOffice"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOffice")
        == FaultState.CLEARED
    )
    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.FAIL

    # Clear Kitchen undertemperature
    test_mock_behaviours = [
        MockBehavior("sensor.kitchen_temperature", iter(["20"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_1(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureKitchen"
            ]
        )

    assert app_instance.fm.check_fault("RiskyTemperature") is FaultEvaluationStatus.PASS


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
        - Input: Initial temperature is 20.0°C, rate is -0.02°C/min, and forecast timespan is 2 hours.
        - Expected Result: Symptom "RiskyTemperatureOfficeForeCast" should be set to True.
    """
    app_instance, __, _, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["20.0"]
    rate_of_change = "-0.02"

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


def test_temperature_forecast_uses_rate_per_minute_and_rejects_implausible_jump(
    mocked_hass_app_with_temp_component,
):
    app_instance, *_ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    component = app_instance.sm_modules["TemperatureComponent"]

    assert component.forecast_temperature(20.0, 0.02, 2.0, 15.0) == 22.4
    assert component.forecast_temperature(20.0, 0.35, 2.0, 15.0) is None


def test_implausible_measurement_cannot_set_or_clear_temperature_fault(
    mocked_hass_app_with_temp_component,
):
    app_instance, *_ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    component = app_instance.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms["RiskyTemperatureHighOffice"]
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [MockBehavior("sensor.office_temperature", iter(["30"] * 10))],
    )

    for _ in range(DEBOUNCE_LIMIT + 2):
        component.sm_tc_3(mechanism)
    assert app_instance.fm.check_symptom("RiskyTemperatureHighOffice") is FaultState.SET

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [MockBehavior("sensor.office_temperature", iter(["3618"] * 10))],
    )
    for _ in range(DEBOUNCE_LIMIT + 2):
        component.sm_tc_3(mechanism)
    assert app_instance.fm.check_symptom("RiskyTemperatureHighOffice") is FaultState.SET
    assert (
        app_instance.fm.get_fault_evaluation("RiskyTemperature").status
        is FaultEvaluationStatus.UNEVALUABLE
    )


def test_invalid_forecast_cannot_clear_active_temperature_fault(
    mocked_hass_app_with_temp_component,
):
    app_instance, *_ = mocked_hass_app_with_temp_component
    app_instance.initialize()
    component = app_instance.sm_modules["TemperatureComponent"]
    mechanism = component.safety_mechanisms["RiskyTemperatureHighOfficeForeCast"]
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [
            MockBehavior("sensor.office_temperature", iter(["27"] * 10)),
            MockBehavior("sensor.office_temperature_rate", iter(["0.02"] * 10)),
        ],
    )
    for _ in range(DEBOUNCE_LIMIT + 2):
        component.sm_tc_4(mechanism)
    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOfficeForeCast")
        is FaultState.SET
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id,
        [
            MockBehavior("sensor.office_temperature", iter(["27"] * 10)),
            MockBehavior("sensor.office_temperature_rate", iter(["unavailable"] * 10)),
        ],
    )
    for _ in range(DEBOUNCE_LIMIT + 2):
        component.sm_tc_4(mechanism)
    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOfficeForeCast")
        is FaultState.SET
    )

    assert (
        app_instance.fm.get_fault_evaluation("RiskyTemperatureForecast").status
        is FaultEvaluationStatus.UNEVALUABLE
    )


def test_forecasted_overtemp_symptom_set_when_temp_rate_indicates_rise(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Forecasted Overtemperature Symptom Set When Temperature Rate Indicates a Rise

    Scenario:
        - Input: Initial temperature is 30.0\u0abbC, rate is 1.0\u0abbC/min, and forecast timespan is 2 hours.
        - Expected Result: Symptom "RiskyTemperatureHighOfficeForeCast" should be set to True.
    """
    app_instance, __, _, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    temperature_sequence = ["27.0"]
    rate_of_change = "0.02"

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
    for _ in range(DEBOUNCE_LIMIT + 2):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_4(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOfficeForeCast"
            ]
        )

    # Assert the symptom state
    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOfficeForeCast")
        is FaultState.SET
    )


def test_forecasted_overtemp_multi_room_fault_clear(
    mocked_hass_app_with_temp_component,
):
    """
    Test Case: Forecasted overtemperature stays SET until all rooms clear.
    """
    app_instance, __, _, ___, mock_behaviors_default = (
        mocked_hass_app_with_temp_component
    )
    app_instance.initialize()

    test_mock_behaviours = [
        MockBehavior("sensor.office_temperature", iter(["27"])),
        MockBehavior("sensor.office_temperature_rate", iter(["0.02"])),
        MockBehavior("sensor.kitchen_temperature", iter(["27"])),
        MockBehavior("sensor.kitchen_temperature_rate", iter(["0.02"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_4(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOfficeForeCast"
            ]
        )
        app_instance.sm_modules["TemperatureComponent"].sm_tc_4(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighKitchenForeCast"
            ]
        )

    assert app_instance.fm.check_fault("RiskyTemperatureForecast") is FaultEvaluationStatus.FAIL

    test_mock_behaviours = [
        MockBehavior("sensor.office_temperature", iter(["25"])),
        MockBehavior("sensor.office_temperature_rate", iter(["0"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_4(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighOfficeForeCast"
            ]
        )

    assert (
        app_instance.fm.check_symptom("RiskyTemperatureHighOfficeForeCast")
        == FaultState.CLEARED
    )
    assert (
        app_instance.fm.check_fault("RiskyTemperatureForecast") is FaultEvaluationStatus.FAIL
    )

    test_mock_behaviours = [
        MockBehavior("sensor.kitchen_temperature", iter(["25"])),
        MockBehavior("sensor.kitchen_temperature_rate", iter(["0"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    for _ in range(5):
        app_instance.sm_modules["TemperatureComponent"].sm_tc_4(
            app_instance.sm_modules["TemperatureComponent"].safety_mechanisms[
                "RiskyTemperatureHighKitchenForeCast"
            ]
        )

    assert (
        app_instance.fm.check_fault("RiskyTemperatureForecast")
        is FaultEvaluationStatus.PASS
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
    rate_of_change = "0.0"  # stable and within forecast plausibility limits

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
    assert notification["local"]["light_entity"] == "light.warning_light"
