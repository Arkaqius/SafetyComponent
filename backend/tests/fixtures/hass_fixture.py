from itertools import cycle
import json
from typing import Any, Generator, List
from unittest.mock import MagicMock, patch

import pytest

from SafetyFunctions import SafetyFunctions
from components.core.mqtt_entity_manager import MqttEntityManager


@pytest.fixture
def mocked_hass() -> Generator[Any, Any, None]:
    """Fixture for providing a mocked Hass instance."""
    with patch("appdaemon.plugins.hass.hassapi.Hass") as MockHass:
        mock_hass = MockHass()
        mock_hass.logger = MagicMock()
        mock_hass.get_state = MagicMock(return_value="on")
        mock_hass.set_state = MagicMock()
        mock_hass.call_service = MagicMock()
        mock_hass.run_in = MagicMock()
        mock_hass.run_every = MagicMock()
        mock_hass.listen_state = MagicMock()
        mock_hass.render_template = MagicMock(
            side_effect=lambda template, **_kwargs: (
                "Office" if '"office"' in template else "Kitchen"
                if '"kitchen"' in template
                else None
            )
        )
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
        app_instance.set_state = mocked_hass.set_state
        app_instance.call_service = mocked_hass.call_service
        app_instance.run_in = mocked_hass.run_in
        app_instance.run_every = mocked_hass.run_every
        app_instance.listen_state = mocked_hass.listen_state
        yield app_instance, mocked_hass, mock_log_method


@pytest.fixture
def mocked_hass_app_with_temp_component(mocked_hass, app_config_valid):
    """Fixture that initializes SafetyFunctions with mocked Hass and TemperatureComponent."""
    with patch(
        "components.safetycomponents.temperature.temperature_component.TemperatureComponent"
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
        app_instance.get_state = MagicMock(
            side_effect=lambda entity_id, **kwargs: mock_get_state(
                entity_id, mock_behaviors
            )
        )

        app_instance.set_state = mocked_hass.set_state
        app_instance.call_service = mocked_hass.call_service
        app_instance.run_in = mocked_hass.run_in
        app_instance.run_every = mocked_hass.run_every
        app_instance.listen_state = mocked_hass.listen_state

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
        MockBehavior("sensor.kitchen_temperature", iter(["5", "6", "7", "8", "9"])),
        MockBehavior("sensor.kitchen_temperature_rate", iter(["0", "0", "0", "0", "0"])),
        MockBehavior(
            "sensor.kitchen_window_contact_contact", iter(["off", "off", "off"])
        ),
        MockBehavior("sensor.dom_temperature", iter(["1", "1", "1"])),
        MockBehavior("light.warning_light", iter(["on", "on", "on"])),
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


def mqtt_topic_for(entity_id: str, topic_kind: str = "state") -> str:
    """Return the default SafetyFunctions MQTT topic for an entity."""
    object_id = MqttEntityManager._slug(entity_id.split(".", 1)[-1])
    return f"safety_component/{topic_kind}/{object_id}"


def mqtt_publish_calls(hass_app: Any, topic: str | None = None) -> list[Any]:
    """Return mqtt.publish service calls, optionally filtered by topic."""
    calls = [
        call
        for call in hass_app.call_service.call_args_list
        if call.args and call.args[0] == "mqtt/publish"
    ]
    if topic is None:
        return calls
    return [call for call in calls if call.kwargs.get("topic") == topic]


def mqtt_payloads(hass_app: Any, topic: str) -> list[str]:
    """Return MQTT payloads published to a topic."""
    return [call.kwargs["payload"] for call in mqtt_publish_calls(hass_app, topic)]


def mqtt_json_payloads(hass_app: Any, topic: str) -> list[dict[str, Any]]:
    """Return JSON MQTT payloads published to a topic."""
    return [
        json.loads(payload)
        for payload in mqtt_payloads(hass_app, topic)
        if payload
    ]
