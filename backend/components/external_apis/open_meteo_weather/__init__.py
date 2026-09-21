"""Open-Meteo weather provider."""

from .component import OpenMeteoWeatherApiComponent
from .schema import COMPONENT_NAME, OpenMeteoWeatherConfig

__all__ = ["COMPONENT_NAME", "OpenMeteoWeatherApiComponent", "OpenMeteoWeatherConfig"]
