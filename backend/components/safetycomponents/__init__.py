
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
from .security.schema import (
    DoorWindowDefaults,
    DoorWindowSecurityComponentConfig,
    DoorConfig,
    WindowConfig,
    validate_door_window_security_config,
)
from .security.door_window_security_component import DoorWindowSecurityComponent

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
    "DoorWindowSecurityComponent",
    "DoorWindowSecurityComponentConfig",
    "DoorWindowDefaults",
    "DoorConfig",
    "WindowConfig",
    "safety_mechanism_decorator",
    "validate_door_window_security_config",
    "validate_temperature_config",
]
