"""Internal smoke, flammable-gas, and carbon-monoxide monitoring."""

from .internal_environmental_hazard_monitor_component import (
    InternalEnvironmentalHazardMonitorComponent,
)
from .schema import (
    BinaryDetectorProfile,
    InternalEnvironmentalHazardMonitorConfig,
    validate_internal_environmental_hazard_config,
)

__all__ = [
    "BinaryDetectorProfile",
    "InternalEnvironmentalHazardMonitorComponent",
    "InternalEnvironmentalHazardMonitorConfig",
    "validate_internal_environmental_hazard_config",
]
