"""Provider-specific external API components and their registry."""

from .core import (
    ApiResult,
    ExternalApiComponent,
    ExternalApiRuntime,
    ExternalObservation,
    HazardType,
    HttpJsonClient,
    Measurement,
    ProviderHealth,
    ProviderHealthState,
    get_registered_api_components,
    register_api_component,
)
from .gios_air_quality import GiosAirQualityApiComponent, GiosAirQualityConfig
from .imgw_warnings import ImgwWarningsApiComponent, ImgwWarningsConfig
from .open_meteo_air_quality import OpenMeteoAirQualityApiComponent, OpenMeteoAirQualityConfig
from .open_meteo_weather import OpenMeteoWeatherApiComponent, OpenMeteoWeatherConfig
from .paa_radiation import PaaRadiationApiComponent, PaaRadiationConfig

__all__ = [
    "ApiResult",
    "ExternalApiComponent",
    "ExternalApiRuntime",
    "ExternalObservation",
    "GiosAirQualityApiComponent",
    "GiosAirQualityConfig",
    "HazardType",
    "HttpJsonClient",
    "ImgwWarningsApiComponent",
    "ImgwWarningsConfig",
    "Measurement",
    "OpenMeteoAirQualityApiComponent",
    "OpenMeteoAirQualityConfig",
    "OpenMeteoWeatherApiComponent",
    "OpenMeteoWeatherConfig",
    "PaaRadiationApiComponent",
    "PaaRadiationConfig",
    "ProviderHealth",
    "ProviderHealthState",
    "get_registered_api_components",
    "register_api_component",
]
