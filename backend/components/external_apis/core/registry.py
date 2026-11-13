"""Registry for provider-specific external API components."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, Type, TYPE_CHECKING

from pydantic import BaseModel

from .models import HazardType, ProviderCapability

if TYPE_CHECKING:
    from .api_component import ExternalApiComponent


_API_COMPONENT_REGISTRY: Dict[str, Type["ExternalApiComponent"]] = {}


def register_api_component(
    cls: Type["ExternalApiComponent"],
) -> Type["ExternalApiComponent"]:
    """Register one provider adapter under its stable component name."""

    name = getattr(cls, "component_name", None)
    if not name:
        raise ValueError("ExternalApiComponent.component_name must be set")
    model = getattr(cls, "config_model", None)
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise ValueError(f"API component '{name}' must declare a configuration model")
    if not isinstance(getattr(cls, "capability", None), ProviderCapability):
        raise ValueError(f"API component '{name}' must declare a provider capability")
    if name in _API_COMPONENT_REGISTRY:
        raise ValueError(f"API component '{name}' is already registered")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        raise ValueError("Provider ID must be a stable alphanumeric key")
    identity = provider_identity(name)
    if any(
        any(
            old == new
            for old, new in zip(provider_identity(existing), identity, strict=True)
        )
        for existing in _API_COMPONENT_REGISTRY
    ):
        raise ValueError(f"Provider diagnostic identity collision: {name}")
    parameters = getattr(cls, "parameter_model", None)
    if not isinstance(parameters, type) or not issubclass(parameters, BaseModel):
        raise ValueError(f"API component '{name}' must declare parameter_model")
    hazards: frozenset[HazardType] = getattr(cls, "hazards", frozenset())
    if not hazards or any(not isinstance(hazard, HazardType) for hazard in hazards):
        raise ValueError(f"API component '{name}' must declare supported hazards")
    allowed = (
        {HazardType.OUTDOOR_AIR_POLLUTION}
        if cls.capability == ProviderCapability.AIR_QUALITY
        else set(HazardType) - {HazardType.OUTDOOR_AIR_POLLUTION}
    )
    if not set(hazards).issubset(allowed):
        raise ValueError(f"API component '{name}' has incompatible hazard coverage")
    if any(not re.fullmatch(r"[A-Z]{2}", country) for country in cls.countries):
        raise ValueError(f"API component '{name}' has invalid country coverage")
    if not cls.required_when_enabled.issubset(parameters.model_fields):
        raise ValueError(f"API component '{name}' declares unknown required parameters")
    for field, path in cls.legacy_parameter_paths.items():
        if (
            field not in parameters.model_fields
            or not path
            or path[0] != "installation"
            or len(path) > 16
            or any(not isinstance(part, str) or len(part) > 128 for part in path)
        ):
            raise ValueError(
                f"API component '{name}' has invalid legacy parameter paths"
            )
    _API_COMPONENT_REGISTRY[name] = cls
    return cls


def get_registered_api_components() -> Dict[str, Type["ExternalApiComponent"]]:
    """Return a copy of the API component registry."""

    return dict(_API_COMPONENT_REGISTRY)


def validate_provider_keys(names: Iterable[str]) -> None:
    """Reject configurations referencing a plugin outside the registry."""
    unknown = sorted(set(names) - _API_COMPONENT_REGISTRY.keys())
    if unknown:
        raise ValueError(f"Unknown provider plugins: {', '.join(unknown)}")


def describe_provider_keys(schema: dict[str, Any]) -> None:
    """Keep the exported configuration schema aligned with registered IDs."""
    schema["propertyNames"] = {"enum": sorted(_API_COMPONENT_REGISTRY)}
    schema["additionalProperties"] = False
    schema["properties"] = {
        name: {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "parameters": parameter_schema(plugin),
            },
        }
        for name, plugin in sorted(_API_COMPONENT_REGISTRY.items())
    }


def provider_identity(name: str) -> tuple[str, str]:
    """Return existing contributor and MQTT identities for collision checks."""

    return (
        "ProviderHealth" + name.removesuffix("ApiComponent"),
        re.sub(r"(?<!^)(?=[A-Z])", "_", name.replace("ApiComponent", "")).lower(),
    )


def parameter_schema(plugin: Type["ExternalApiComponent"]) -> dict[str, Any]:
    """Return a closed parameter schema with provider-local definitions."""

    return closed_model_schema(plugin.parameter_model)


def closed_model_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Inline bounded local references for a self-contained closed model schema."""

    schema = copy.deepcopy(model.model_json_schema())
    schema["additionalProperties"] = False
    definitions = schema.pop("$defs", {})
    if len(definitions) > 128:
        raise ValueError("Provider schema exceeds 128 definitions")
    if definitions:
        # Parameter schemas are self-contained when embedded in the catalogue.
        def expand(value: Any, seen: frozenset[str] = frozenset()) -> Any:
            if isinstance(value, list):
                return [expand(item, seen) for item in value]
            if not isinstance(value, dict):
                return value
            if "$ref" in value:
                reference = value["$ref"]
                key = reference.removeprefix("#/$defs/")
                if (
                    not reference.startswith("#/$defs/")
                    or key in seen
                    or key not in definitions
                    or len(seen) >= 16
                ):
                    raise ValueError("Unsupported provider schema reference")
                return expand(
                    {
                        **definitions[key],
                        **{k: v for k, v in value.items() if k != "$ref"},
                    },
                    seen | {key},
                )
            return {key: expand(item, seen) for key, item in value.items()}

        schema = expand(schema)
    return schema


def describe_runtime_provider_keys(schema: dict[str, Any]) -> None:
    """Export each registered provider's packaged transport schema."""

    schema["propertyNames"] = {"enum": sorted(_API_COMPONENT_REGISTRY)}
    schema["additionalProperties"] = False
    schema["properties"] = {
        name: closed_model_schema(plugin.config_model)
        for name, plugin in sorted(_API_COMPONENT_REGISTRY.items())
    }


def clear_registered_api_components() -> None:
    """Clear the registry for isolated tests."""

    _API_COMPONENT_REGISTRY.clear()
