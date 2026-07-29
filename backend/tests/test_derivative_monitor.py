from unittest.mock import Mock, call

import pytest

from components.core.derivative_monitor import DerivativeMonitor


@pytest.fixture
def setup_derivative_monitor():
    """Set up a fresh derivative monitor with an MQTT publisher."""
    mock_hass = Mock()
    mock_hass.run_every = Mock()
    mqtt_entities = Mock()
    DerivativeMonitor._instance = None
    derivative_monitor = DerivativeMonitor(mock_hass, mqtt_entities)

    derivative_monitor.entities.clear()
    derivative_monitor.derivative_data.clear()
    state_values = {}

    def mock_get_state(entity_id, **kwargs):
        return state_values.get(entity_id)

    def set_mock_state(entity_id, value):
        state_values[entity_id] = value

    mock_hass.get_state.side_effect = mock_get_state
    return mock_hass, mqtt_entities, derivative_monitor, set_mock_state


def test_register_entity(setup_derivative_monitor):
    """Verify derivative sensors are registered through MQTT discovery."""
    mock_hass, mqtt_entities, derivative_monitor, _ = setup_derivative_monitor
    entity_id = "sensor.temperature"
    sample_time = 10

    derivative_monitor.register_entity(entity_id, sample_time, -5.0, 5.0)

    config = derivative_monitor.entities[entity_id]
    assert config["sample_time"] == sample_time
    assert config["low_saturation"] == -5.0
    assert config["high_saturation"] == 5.0
    mqtt_entities.register_sensor.assert_has_calls(
        [
            call(
                f"{entity_id}_rate",
                f"{entity_id} Rate",
                state=None,
                attributes={
                    "friendly_name": f"{entity_id} Rate",
                    "state_class": "measurement",
                    "unit_of_measurement": "°C/min",
                    "attribution": "Data provided by SafetyFunction",
                    "icon": "mdi:chart-timeline-variant",
                },
                icon="mdi:chart-timeline-variant",
                unit_of_measurement="°C/min",
                state_class="measurement",
                entity_category="diagnostic",
            ),
            call(
                f"{entity_id}_rateOfRate",
                f"{entity_id} Rate Of Rate",
                state=None,
                attributes={
                    "friendly_name": f"{entity_id} Rate Of Rate",
                    "state_class": "measurement",
                    "unit_of_measurement": "°C/min²",
                    "attribution": "Data provided by SafetyFunction",
                    "icon": "mdi:chart-timeline-variant",
                },
                icon="mdi:chart-timeline-variant",
                unit_of_measurement="°C/min²",
                state_class="measurement",
                entity_category="diagnostic",
            ),
        ]
    )
    mock_hass.run_every.assert_called_with(
        derivative_monitor._calculate_diff,
        "now",
        sample_time,
        entity_id=entity_id,
        sample_time=sample_time,
    )


def test_calculate_diff_updates_derivatives(setup_derivative_monitor):
    """Test derivative calculation and MQTT state publication."""
    _, mqtt_entities, derivative_monitor, set_mock_state = setup_derivative_monitor
    entity_id = "sensor.temperature"
    sample_time = 60
    derivative_monitor.register_entity(entity_id, sample_time, -10.0, 10.0)

    set_mock_state(entity_id, 10.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_first_derivative(entity_id) is None
    assert derivative_monitor.get_second_derivative(entity_id) is None

    set_mock_state(entity_id, 13.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_first_derivative(entity_id) == 1.5

    set_mock_state(entity_id, 17.0)
    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=sample_time)
    assert derivative_monitor.get_second_derivative(entity_id) == 1.25
    mqtt_entities.publish_sensor_state.assert_any_call(
        f"{entity_id}_rate",
        derivative_monitor.get_first_derivative(entity_id),
    )
    mqtt_entities.publish_sensor_state.assert_any_call(
        f"{entity_id}_rateOfRate",
        derivative_monitor.get_second_derivative(entity_id),
    )


def test_calculate_diff_handles_missing_value(setup_derivative_monitor):
    """Ensure missing values skip calculation."""
    mock_hass, _, derivative_monitor, _ = setup_derivative_monitor
    entity_id = "sensor.temperature"
    derivative_monitor.register_entity(entity_id, 10, -5.0, 5.0)

    derivative_monitor._calculate_diff(entity_id=entity_id, sample_time=10)
    mock_hass.log.assert_any_call(
        f"No value available for {entity_id}. Skipping calculation.",
        level="DEBUG",
    )


def test_unregistered_entity_error(setup_derivative_monitor):
    """Ensure an error is logged for unregistered entities."""
    mock_hass, _, derivative_monitor, _ = setup_derivative_monitor
    derivative_monitor._calculate_diff(entity_id="sensor.unregistered")
    mock_hass.log.assert_called_with(
        "Entity sensor.unregistered not registered for derivatives.",
        level="ERROR",
    )


def test_get_entity_value_invalid(setup_derivative_monitor):
    mock_hass, _, derivative_monitor, _ = setup_derivative_monitor
    mock_hass.get_state.side_effect = None
    mock_hass.get_state.return_value = "bad"
    assert derivative_monitor._get_entity_value("sensor.temperature") is None
