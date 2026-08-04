"""Shared external API infrastructure."""

from .api_component import ExternalApiComponent
from .api_runtime import ExternalApiRuntime
from .http_json_client import HttpJsonClient, HttpJsonError
from .models import (
    ApiResult,
    ExternalObservation,
    HazardType,
    Measurement,
    ProviderHealth,
    ProviderHealthState,
)
from .registry import get_registered_api_components, register_api_component

__all__ = [
    "ApiResult",
    "ExternalApiComponent",
    "ExternalApiRuntime",
    "ExternalObservation",
    "HazardType",
    "HttpJsonClient",
    "HttpJsonError",
    "Measurement",
    "ProviderHealth",
    "ProviderHealthState",
    "get_registered_api_components",
    "register_api_component",
]
