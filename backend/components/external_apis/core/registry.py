"""Registry for provider-specific external API components."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Type, TYPE_CHECKING

from pydantic import BaseModel

from .models import ProviderCapability

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


def clear_registered_api_components() -> None:
    """Clear the registry for isolated tests."""

    _API_COMPONENT_REGISTRY.clear()
