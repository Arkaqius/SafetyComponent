
"""Temperature safety component and configuration schema."""

from .schema import (
    TemperatureComponentConfig,
    TemperatureDefaults,
    TemperatureRoom,
    validate_temperature_config,
)
from .temperature_component import TemperatureComponent

__all__ = [
    "TemperatureComponent",
    "TemperatureComponentConfig",
    "TemperatureDefaults",
    "TemperatureRoom",
    "validate_temperature_config",
]
