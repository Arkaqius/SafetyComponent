"""External Hazard Monitoring safety component."""

from .external_hazard_component import ExternalHazardComponent
from .schema import (
    COMPONENT_NAME,
    ExternalHazardComponentConfig,
    ExternalHazardPolicy,
    SiteConfig,
    validate_external_hazard_config,
)

__all__ = [
    "COMPONENT_NAME",
    "ExternalHazardComponent",
    "ExternalHazardComponentConfig",
    "ExternalHazardPolicy",
    "SiteConfig",
    "validate_external_hazard_config",
]
