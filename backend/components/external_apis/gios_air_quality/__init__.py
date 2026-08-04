"""GIOŚ air-quality provider."""

from .component import GiosAirQualityApiComponent
from .schema import COMPONENT_NAME, GiosAirQualityConfig

__all__ = ["COMPONENT_NAME", "GiosAirQualityApiComponent", "GiosAirQualityConfig"]
