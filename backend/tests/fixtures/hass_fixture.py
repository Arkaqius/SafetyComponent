import pytest
from unittest.mock import MagicMock, patch
from shared.types_common import FaultState
from SafetyFunctions import SafetyFunctions
from shared.temperature_component import TemperatureComponent
from typing import Any, Generator, List
from itertools import cycle


@pytest.fixture
def mocked_hass() -> Generator[Any, Any, None]:
    """Fixture for providing a mocked Hass instance."""
    with patch("appdaemon.plugins.hass.hassapi.Hass") as MockHass:
        mock_hass = MockHass()
        mock_hass.logger = MagicMock()
        mock_hass.get_state = MagicMock(return_value="on")
        mock_hass.set_state = MagicMock()
        mock_hass.call_service = MagicMock()
        yield mock_hass


@pytest.fixture
def mocked_hass_app_basic(mocked_hass, app_config_valid):
    """Fixture that initializes SafetyFunctions with mocked Hass and provides state management."""
    with patch.object(
        SafetyFunctions, "log", new_callable=MagicMock
    ) as mock_log_method:
        app_instance = SafetyFunctions(
            mocked_hass,
            "dummy_namespace",
            mocked_hass.logger,
            app_config_valid,
            "mock_config",
            "dummy_app_config",
            "dummy_global_vars",
        )

        mock_behaviors = default_mock_behaviors()
        app_instance.get_state = MagicMock(
            side_effect=lambda entity_id, **kwargs: mock_get_state(
                entity_id, mock_behaviors
            )
        )
        yield app_instance, mocked_hass, mock_log_method


@pytest.fixture
def mocked_hass_app_with_temp_component(mocked_hass, app_config_valid):
    """Fixture that initializes SafetyFunctions with mocked Hass and TemperatureComponent."""
    with patch(
        "shared.temperature_component.TemperatureComponent"
    ) as MockTemperatureComponent, patch.object(
        SafetyFunctions, "log", new_callable=MagicMock
    ) as mock_log_method:

        app_instance = SafetyFunctions(
            mocked_hass,
            "dummy_namespace",
            mocked_hass.logger,
            app_config_valid,
            "mock_config",
            "dummy_app_config",
            "dummy_global_vars",
        )

        mock_behaviors = default_mock_behaviors()
        app_instance.get_state  = MagicMock(
            side_effect=lambda entity_id, **kwargs: mock_get_state(
                entity_id, mock_behaviors
            )
        )
        
        app_instance.set_state = mocked_hass.set_state
        app_instance.call_service = mocked_hass.call_service
        
        yield app_instance, mocked_hass, mock_log_method, MockTemperatureComponent, mock_behaviors


def default_mock_behaviors():
    """Default mock behaviors for sensors."""
    return [
        MockBehavior("sensor.office_temperature", iter(["5", "6", "7", "8", "9"])),
        MockBehavior("sensor.office_temperature_rate", iter(["0", "0", "0", "0", "0"])),
        MockBehavior("sensor.office_humidity", iter(["45", "50"])),
        MockBehavior("sensor.fault_RiskyTemperature", iter([None, None, None])),
        MockBehavior(
            "sensor.office_window_contact_contact", iter(["off", "off", "off"])
        ),
        MockBehavior("sensor.dom_temperature", iter(["1", "1", "1"])),
    ]


class MockBehavior:
    """Class to simulate sensor behavior for testing."""

    def __init__(self, entity_id, generator):
        self.entity_id = entity_id
        self.generator = cycle(generator)

    def get_value(self, called_entity_id):
        if called_entity_id == self.entity_id:
            return next(self.generator, None)
        return None


def mock_get_state(entity_id, mock_behaviors):
    """Simulate get_state based on mock behaviors."""
    for behavior in mock_behaviors:
        value = behavior.get_value(entity_id)
        if value is not None:
            return value
    return None

def update_mocked_get_state(default: List[MockBehavior], test_specyfic: List[MockBehavior]) -> List[MockBehavior]:
    # Create a set of entity_ids already in the default list for quick lookup
    default_entity_ids = {mock.entity_id for mock in default}
    
    # Iterate over the default list to replace existing mocks with those from test_specyfic
    for idx, default_mock in enumerate(default):
        matching_mock = next((test_mock for test_mock in test_specyfic if test_mock.entity_id == default_mock.entity_id), None)
        if matching_mock:
            default[idx] = matching_mock
    
    # Add mocks from test_specyfic that are not present in the default list
    for test_mock in test_specyfic:
        if test_mock.entity_id not in default_entity_ids:
            default.append(test_mock)
    
    return default
