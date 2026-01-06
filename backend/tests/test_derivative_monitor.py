import pytest
from unittest.mock import Mock, call
from components.safetycomponents.core.derivative_monitor import DerivativeMonitor


@pytest.fixture
def setup_derivative_monitor():
    """Fixture to set up a mock Hass app and a fresh DerivativeMonitor instance."""
    mock_hass = Mock()
    mock_hass.run_every = Mock()
    DerivativeMonitor._instance = None
    derivative_monitor = DerivativeMonitor(mock_hass)

    # Ensure singleton state is clean for each test
    derivative_monitor.entities.clear()
    derivative_monitor.derivative_data.clear()

    # Use a mutable dictionary to hold state values (ensures proper scoping in closures)
    state_values = {}

    def mock_get_state(entity_id, **kwargs):
        return state_values.get(entity_id, None)

    def set_mock_state(entity_id, value):
        state_values[entity_id] = value

    # Attach state change simulation to mock_hass
    mock_hass.get_state.side_effect = mock_get_state
    mock_hass.set_state.side_effect = lambda entity_id, state, **kwargs: set_mock_state(
        entity_id, state
    )

    return mock_hass, derivative_monitor, set_mock_state


def test_register_entity(setup_derivative_monitor):
    """Verify entity registration and creation of derivative entities in Home Assistant."""
    mock_hass, derivative_monitor, _ = setup_derivative_monitor
    entity_id = "sensor.temperature"
    sample_time = 10
    low_saturation = -5.0
    high_saturation = 5.0

    derivative_monitor.register_entity(entity_id, sample_time, low_saturation, high_saturation)

    # Verify entity configuration is stored
    assert entity_id in derivative_monitor.entities
    config = derivative_monitor.entities[entity_id]
    assert config["sample_time"] == sample_time
    assert config["low_saturation"] == low_saturation
    assert config["high_saturation"] == high_saturation

    # Verify derivative entities are created in Home Assistant
    mock_hass.set_state.assert_has_calls(
        [
            call(
                f"{entity_id}_rate",
                state=None,
                attributes={'friendly_name': 'sensor.temperature Rate', 'state_class': 'measurement', 'unit_of_measurement': '°C/min', 'attribution': 'Data provided by SafetyFunction', 'device_class': 'temperature', 'icon': 'mdi:chart-timeline-variant'},
            ),
            call(
                f"{entity_id}_rateOfRate",
                state=None,
                attributes={'friendly_name': 'sensor.temperature Rate', 'state_class': 'measurement', 'unit_of_measurement': '°C/min', 'attribution': 'Data provided by SafetyFunction', 'device_class': 'temperature', 'icon': 'mdi:chart-timeline-variant'},
            ),
        ]
    )
    
    mock_hass.run_every.assert_called_with(
        derivative_monitor._calculate_diff, "now", sample_time, entity_id=entity_id, sample_time=sample_time
    )


def test_calculate_diff_updates_derivatives(setup_derivative_monitor):
    """Test the calculation of first and second derivatives."""
    mock_hass, derivative_monitor, set_mock_state = setup_derivative_monitor

    entity_id = "sensor.temperature"
    sample_time = 60
    low_saturation = -10.0
    high_saturation = 10.0

    derivative_monitor.register_entity(entity_id, sample_time, low_saturation, high_saturation)

    # Initial state change sets prev_value only
    set_mock_state(entity_id, 10.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_first_derivative(entity_id) is None
    assert derivative_monitor.get_second_derivative(entity_id) is None

    # Second change sets first derivative (filtered)
    set_mock_state(entity_id, 13.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_first_derivative(entity_id) == 1.5

    # Third change yields a non-zero second derivative
    set_mock_state(entity_id, 17.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_second_derivative(entity_id) == 1.25
    mock_hass.set_state.assert_called_with(f"{entity_id}_rate", state=derivative_monitor.get_first_derivative(entity_id))


def test_calculate_diff_handles_missing_value(setup_derivative_monitor):
    """Ensure missing values skip calculation."""
    mock_hass, derivative_monitor, _ = setup_derivative_monitor
    entity_id = "sensor.temperature"
    sample_time = 10
    derivative_monitor.register_entity(entity_id, sample_time, -5.0, 5.0)

    mock_hass.get_state.return_value = None
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    mock_hass.log.assert_any_call(
        f"No value available for {entity_id}. Skipping calculation.",
        level="DEBUG",
    )


def test_unregistered_entity_error(setup_derivative_monitor):
    """Ensure an error is logged for unregistered entities."""
    mock_hass, derivative_monitor, _ = setup_derivative_monitor
    entity_id = "sensor.unregistered"
    derivative_monitor._calculate_diff(entity_id=entity_id)
    mock_hass.log.assert_called_with(
        f"Entity {entity_id} not registered for derivatives.", level="ERROR"
    )


def test_get_entity_value_invalid(setup_derivative_monitor):
    mock_hass, derivative_monitor, _ = setup_derivative_monitor
    mock_hass.get_state.return_value = "bad"
    assert derivative_monitor._get_entity_value("sensor.temperature") is None
