
"""Safety component base classes and concrete implementations."""

from .core.safety_component import (
    DebounceAction,
    DebounceResult,
    DebounceState,
    SafetyComponent,
    SafetyMechanismResult,
    clear_registered_components,
    get_registered_components,
    register_safety_component,
    safety_mechanism_decorator,
)
from .core.safety_mechanism import SafetyMechanism
from .temperature.schema import (
    TemperatureComponentConfig,
    TemperatureDefaults,
    TemperatureRoom,
    validate_temperature_config,
)
from .temperature.temperature_component import TemperatureComponent

__all__ = [
    "DebounceAction",
    "DebounceResult",
    "DebounceState",
    "SafetyComponent",
    "SafetyMechanism",
    "SafetyMechanismResult",
    "clear_registered_components",
    "get_registered_components",
    "register_safety_component",
    "TemperatureComponent",
    "TemperatureComponentConfig",
    "TemperatureDefaults",
    "TemperatureRoom",
    "safety_mechanism_decorator",
    "validate_temperature_config",
]
