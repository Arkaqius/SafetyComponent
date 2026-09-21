"""Safety Doors component exports."""

from .safety_doors_component import SafetyDoorsComponent
from .schema import (
    SafetyDoorConfig,
    SafetyDoorDefaults,
    SafetyDoorsComponentConfig,
    validate_safety_doors_config,
)

__all__ = [
    "SafetyDoorConfig",
    "SafetyDoorDefaults",
    "SafetyDoorsComponent",
    "SafetyDoorsComponentConfig",
    "validate_safety_doors_config",
]
