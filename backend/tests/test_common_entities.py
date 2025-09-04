from unittest.mock import Mock
import pytest
from shared.common_entities import CommonEntities

def test_common_entities_initialization():
    """
    Test Case: Initialization of CommonEntities.

    Scenario:
        - The configuration is provided with an outside temperature sensor.
        - Expected Result: The CommonEntities instance should have the correct sensor name.
    """
    # Mock the Home Assistant instance
    mocked_hass_app = Mock()

    # Configuration with an outside temperature sensor
    config = {"outside_temp": "sensor.outside_temperature"}

    # Instantiate CommonEntities with the mocked hass_app and configuration
    common_entities = CommonEntities(mocked_hass_app, config)

    # Verify that the outside_temp_sensor is set correctly
    assert common_entities.outside_temp_sensor == "sensor.outside_temperature"

def test_get_outside_temperature():
    """
    Test Case: Get outside temperature from Home Assistant.

    Scenario:
        - A valid temperature sensor is provided, and hass_app returns a value.
        - Expected Result: The temperature value from hass_app should be returned.
    """
    # Mock the Home Assistant instance
    mocked_hass_app = Mock()

    # Configure hass_app to return a temperature value when get_state is called
    mocked_hass_app.get_state.return_value = "25.5"

    # Configuration with an outside temperature sensor
    config = {"outside_temp": "sensor.outside_temperature"}

    # Instantiate CommonEntities with the mocked hass_app and configuration
    common_entities = CommonEntities(mocked_hass_app, config)

    # Call get_outisde_temperature() and verify the returned value
    temperature = common_entities.get_outisde_temperature()
    assert temperature == "25.5"
    mocked_hass_app.get_state.assert_called_with("sensor.outside_temperature")

def test_get_outside_temperature_no_hass_app():
    """
    Test Case: Get outside temperature when hass_app is None.

    Scenario:
        - hass_app is None, so there is no connection to Home Assistant.
        - Expected Result: The log function should be called to indicate an error, and None should be returned.
    """
    # Mock the Home Assistant instance
    mocked_hass_app = Mock()
    mocked_hass_app.log = Mock()

    # Configuration with an outside temperature sensor
    config = {"outside_temp": "sensor.outside_temperature"}

    # Instantiate CommonEntities with the mocked hass_app and configuration
    common_entities = CommonEntities(mocked_hass_app, config)

    # Set hass_app to None to simulate the absence of Home Assistant connection
    common_entities.hass_app = None

    # Call get_outisde_temperature() and verify the returned value is None
    temperature = common_entities.get_outisde_temperature()
    assert temperature is None