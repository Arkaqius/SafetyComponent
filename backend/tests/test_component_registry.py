from components.safetycomponents.core.safety_component import (
    get_registered_components,
)
from components.safetycomponents.temperature.temperature_component import (
    TemperatureComponent,
)
from components.safetycomponents.internal_environmental_hazard.internal_environmental_hazard_monitor_component import (
    InternalEnvironmentalHazardMonitorComponent,
)


def test_temperature_component_is_registered():
    registry = get_registered_components()
    assert registry.get("TemperatureComponent") is TemperatureComponent


def test_internal_environmental_hazard_component_is_registered():
    registry = get_registered_components()
    assert (
        registry.get("InternalEnvironmentalHazardMonitorComponent")
        is InternalEnvironmentalHazardMonitorComponent
    )
