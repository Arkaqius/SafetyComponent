from components.safetycomponents.core.safety_component import (
    get_registered_components,
)
from components.safetycomponents.temperature.temperature_component import (
    TemperatureComponent,
)


def test_temperature_component_is_registered():
    registry = get_registered_components()
    assert registry.get("TemperatureComponent") is TemperatureComponent
