"""Security safety components and schemas."""

from .door_window_security_component import DoorWindowSecurityComponent
from .schema import (
    DoorWindowDefaults,
    DoorWindowSecurityComponentConfig,
    DoorConfig,
    WindowConfig,
    validate_door_window_security_config,
)

__all__ = [
    "DoorWindowSecurityComponent",
    "DoorWindowDefaults",
    "DoorWindowSecurityComponentConfig",
    "DoorConfig",
    "WindowConfig",
    "validate_door_window_security_config",
]
