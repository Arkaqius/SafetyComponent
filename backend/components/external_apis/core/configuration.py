"""Pure provider configuration resolution shared by compilation and startup."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from .models import ProviderCapability
from .registry import get_registered_api_components, parameter_schema


class ProviderConfigurationError(ValueError):
    """Carry bounded source-path errors without parsing exception strings."""

    def __init__(self, path: list[str | int], code: str, message: str) -> None:
        super().__init__(f"{'.'.join(str(part) for part in path)}: {message}")
        self.field_errors = [
            {"path": path[:16], "code": code, "message": message[:512]}
        ]


def _error(
    section: str, suffix: list[str | int], code: str, message: str
) -> ProviderConfigurationError:
    return ProviderConfigurationError(["user_config", section, *suffix], code, message)


def resolve_provider_bindings(
    provider_policies: Mapping[str, Any],
    external_sources: Mapping[str, Any],
    provider_parameters: Mapping[str, Any],
    site: Mapping[str, Any],
    *,
    component_enabled: bool = True,
    weather_horizon: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve explicit source choices and canonical parameters without I/O."""
    plugins = get_registered_api_components()
    capabilities = {item.value for item in ProviderCapability}
    if set(external_sources) != capabilities:
        raise _error(
            "external_sources",
            [],
            "invalid_categories",
            "Each category must explicitly select a provider or null",
        )
    if "teryt_codes" in site:
        raise _error(
            "installation",
            ["site", "teryt_codes"],
            "unknown_field",
            "teryt_codes belongs to provider_parameters",
        )
    unknown = (set(provider_policies) | set(provider_parameters)) - plugins.keys()
    if unknown:
        raise _error(
            "provider_parameters",
            [sorted(unknown)[0]],
            "unknown_provider",
            "Unknown provider plugin",
        )
    selected: set[str] = set()
    country = str(site.get("country_code", "")).strip().upper()
    for capability, name in external_sources.items():
        if name is None:
            continue
        if (
            not isinstance(name, str)
            or name not in plugins
            or name not in provider_policies
        ):
            raise _error(
                "external_sources",
                [capability],
                "unknown_provider",
                "Unknown provider or missing packaged policy",
            )
        plugin = plugins[name]
        if plugin.capability.value != capability:
            raise _error(
                "external_sources",
                [capability],
                "invalid_capability",
                "Provider capability does not match category",
            )
        if site and plugin.countries and country not in plugin.countries:
            raise _error(
                "external_sources",
                [capability],
                "incompatible_country",
                "Provider is incompatible with installation country",
            )
        selected.add(name)
    if component_enabled and selected and not country:
        raise _error(
            "installation",
            ["site"],
            "required_site",
            "An active source requires installation country and site",
        )
    normalized: dict[str, dict[str, Any]] = {}
    for name in set(provider_parameters) | set(provider_policies):
        plugin = plugins[name]
        raw = provider_parameters.get(name, {})
        if not isinstance(raw, Mapping):
            raise _error(
                "provider_parameters",
                [name],
                "invalid_value",
                "Provider parameters must be a mapping",
            )
        extras = set(raw) - plugin.parameter_model.model_fields.keys()
        if extras:
            raise _error(
                "provider_parameters",
                [name, sorted(extras)[0]],
                "unknown_field",
                "Unknown provider parameter",
            )
        try:
            parameters = plugin.parameter_model.model_validate(dict(raw)).model_dump(
                exclude_none=True
            )
        except ValidationError as exc:
            issue = exc.errors()[0]
            raise _error(
                "provider_parameters",
                [name, *issue["loc"]],
                "invalid_value",
                issue["msg"],
            ) from exc
        if component_enabled and name in selected:
            for field in plugin.required_when_selected:
                if parameters.get(field) in (None, "", []):
                    raise _error(
                        "provider_parameters",
                        [name, field],
                        "required_when_selected",
                        f"{field} is required when provider is selected",
                    )
        normalized[name] = parameters
    result: dict[str, dict[str, Any]] = {}
    for name, policy in provider_policies.items():
        plugin = plugins[name]
        transport = copy.deepcopy(dict(policy))
        if (
            plugin.capability == ProviderCapability.WEATHER_MODEL
            and weather_horizon is not None
        ):
            transport["forecast_horizon_hours"] = weather_horizon
        try:
            validated = plugin.config_model.model_validate(
                transport, context={"strict_validation": True}
            ).model_dump()
        except (ValidationError, ValueError) as exc:
            raise _error(
                "external_sources",
                [plugin.capability.value],
                "invalid_transport",
                str(exc),
            ) from exc
        result[name] = {
            **validated,
            "enabled": bool(component_enabled and name in selected),
            "parameters": normalized[name],
        }
    return result


def export_provider_catalogue(packaged_defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Export bounded editable metadata independently of installation validity."""

    plugins = get_registered_api_components()
    if len(packaged_defaults) > 64:
        raise ValueError("Provider catalogue exceeds 64 entries")
    result: dict[str, Any] = {}
    for name in packaged_defaults:
        if name not in plugins:
            raise ValueError(f"Unknown provider plugin: {name}")
        plugin = plugins[name]
        schema = parameter_schema(plugin)
        _validate_schema_budget(schema)
        title = plugin.display_name or name
        description = plugin.description
        if len(title) > 256 or len(description) > 2048:
            raise ValueError("Provider display metadata exceeds text budget")
        result[name] = {
            "countries": sorted(plugin.countries),
            "capability": plugin.capability.value,
            "hazards": sorted(h.value for h in plugin.hazards),
            "display_name": title,
            "description": description,
            "parameter_schema": schema,
            "required_when_selected": sorted(plugin.required_when_selected),
            "parameter_defaults": {
                key: value.get_default(call_default_factory=True)
                for key, value in plugin.parameter_model.model_fields.items()
                if not value.is_required()
                and value.get_default(call_default_factory=True) is not None
            },
            "data_kind": plugin.data_kind,
            "transport_kind": plugin.transport_kind,
        }
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 1_048_576:
        raise ValueError("Provider catalogue exceeds 1 MiB")
    return result


def _validate_schema_budget(schema: dict[str, Any]) -> None:
    """Reject schema metadata exceeding the shared editor interpretation limits."""

    if len(json.dumps(schema, ensure_ascii=False).encode("utf-8")) > 65_536:
        raise ValueError("Provider schema exceeds 64 KiB")

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("Provider schema exceeds depth 8")
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "properties" and len(item) > 64:
                    raise ValueError("Provider schema exceeds 64 properties")
                if key == "$defs" and len(item) > 128:
                    raise ValueError("Provider schema exceeds 128 definitions")
                if key == "enum" and len(item) > 1024:
                    raise ValueError("Provider schema exceeds 1024 enum choices")
                if key == "enum" and any(
                    isinstance(choice, str) and len(choice) > 256 for choice in item
                ):
                    raise ValueError("Provider enum label exceeds 256 characters")
                if (
                    key in {"title", "pattern"}
                    and isinstance(item, str)
                    and len(item) > 256
                ):
                    raise ValueError("Provider schema text exceeds 256 characters")
                if key == "description" and isinstance(item, str) and len(item) > 2048:
                    raise ValueError("Provider help exceeds 2048 characters")
                visit(item, depth + 1)

    visit(schema)
