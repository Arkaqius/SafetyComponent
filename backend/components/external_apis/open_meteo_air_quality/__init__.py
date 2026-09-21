"""Open-Meteo air-quality provider."""

from .component import OpenMeteoAirQualityApiComponent
from .schema import COMPONENT_NAME, OpenMeteoAirQualityConfig

__all__ = ["COMPONENT_NAME", "OpenMeteoAirQualityApiComponent", "OpenMeteoAirQualityConfig"]
