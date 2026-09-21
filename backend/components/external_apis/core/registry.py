"""Registry for provider-specific external API components."""

from __future__ import annotations

from typing import Dict, Type, TYPE_CHECKING

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
    if name in _API_COMPONENT_REGISTRY:
        raise ValueError(f"API component '{name}' is already registered")
    _API_COMPONENT_REGISTRY[name] = cls
    return cls


def get_registered_api_components() -> Dict[str, Type["ExternalApiComponent"]]:
    """Return a copy of the API component registry."""

    return dict(_API_COMPONENT_REGISTRY)


def clear_registered_api_components() -> None:
    """Clear the registry for isolated tests."""

    _API_COMPONENT_REGISTRY.clear()
