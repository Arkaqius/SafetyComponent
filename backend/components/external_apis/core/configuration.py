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
    name: str, suffix: list[str | int], code: str, message: str
) -> ProviderConfigurationError:
    return ProviderConfigurationError(
        ["user_config", "providers", name, *suffix], code, message
    )


def resolve_provider_bindings(
    provider_policies: Mapping[str, Any],
    selections: Mapping[str, Any],
    site: Mapping[str, Any],
    *,
    component_enabled: bool = True,
    generated: bool = False,
    weather_horizon: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate and resolve providers without network calls or source mutation."""

    plugins = get_registered_api_components()
    unknown = set(provider_policies) | set(selections)
    unknown -= plugins.keys()
    if unknown:
        name = sorted(unknown)[0]
        raise _error(name, [], "unknown_provider", "Unknown provider plugin")
    missing_policy = set(selections) - set(provider_policies)
    if missing_policy:
        raise _error(
            sorted(missing_policy)[0],
            [],
            "unknown_provider",
            "Provider has no packaged policy",
        )
    result: dict[str, dict[str, Any]] = {}
    for name, policy in provider_policies.items():
        plugin = plugins[name]
        selection = copy.deepcopy(dict(selections.get(name, {})))
        if not generated:
            extra = set(selection) - {"enabled", "parameters"}
            if extra:
                raise _error(
                    name, [sorted(extra)[0]], "unknown_field", "Unknown provider field"
                )
        origin = selection.get(
            "selection_origin",
            "inherited"
            if generated
            else ("explicit" if "enabled" in selection else "inherited"),
        )
        if origin not in {"explicit", "inherited"}:
            raise _error(name, [], "invalid_value", "Invalid selection provenance")
        requested = selection.get("enabled", policy.get("enabled", True))
        if not isinstance(requested, bool):
            raise _error(
                name, ["enabled"], "invalid_value", "enabled must be a boolean"
            )
        country = str(site.get("country_code", "")).strip().upper()
        applicable = not plugin.countries or country in plugin.countries
        if component_enabled and requested and not applicable and origin == "explicit":
            raise _error(
                name,
                ["enabled"],
                "incompatible_country",
                "Provider is incompatible with installation country",
            )
        active = bool(component_enabled and requested and applicable)
        raw = selection.get("parameters", {})
        if not isinstance(raw, dict):
            raise _error(
                name, ["parameters"], "invalid_value", "parameters must be a mapping"
            )
        raw = copy.deepcopy(raw)
        extras = set(raw) - plugin.parameter_model.model_fields.keys()
        if extras:
            raise _error(
                name,
                ["parameters", sorted(extras)[0]],
                "unknown_field",
                "Unknown provider parameter",
            )
        # Compatibility is declared by its provider; generic code owns no TERYT rule.
        for field, path in plugin.legacy_parameter_paths.items():
            legacy: Any = {"installation": {"site": dict(site)}}
            for part in path:
                if not isinstance(legacy, Mapping) or part not in legacy:
                    legacy = None
                    break
                legacy = legacy[part]
            if generated and legacy == []:
                legacy = None
            if legacy is not None:
                try:
                    normalized_legacy = plugin.parameter_model.model_validate(
                        {field: legacy}
                    ).model_dump(exclude_none=True)[field]
                    if field in raw:
                        normalized_new = plugin.parameter_model.model_validate(
                            {field: raw[field]}
                        ).model_dump(exclude_none=True)[field]
                        equal = (
                            set(normalized_new) == set(normalized_legacy)
                            if isinstance(normalized_new, list)
                            and isinstance(normalized_legacy, list)
                            else normalized_new == normalized_legacy
                        )
                        if not equal:
                            raise _error(
                                name,
                                ["parameters", field],
                                "alias_conflict",
                                "Legacy and provider parameter values conflict",
                            )
                    else:
                        raw[field] = legacy
                except ValidationError as exc:
                    raise ProviderConfigurationError(
                        ["user_config", *path], "invalid_value", str(exc)
                    ) from exc
        try:
            parameters = plugin.parameter_model.model_validate(raw).model_dump(
                exclude_none=True
            )
        except ValidationError as exc:
            issue = exc.errors()[0]
            raise _error(
                name, ["parameters", *issue["loc"]], "invalid_value", issue["msg"]
            ) from exc
        if active:
            for field in plugin.required_when_enabled:
                if parameters.get(field) in (None, "", []):
                    raise _error(
                        name,
                        ["parameters", field],
                        "required_when_enabled",
                        f"{field} is required when provider is enabled",
                    )
        transport = copy.deepcopy(dict(policy))
        if generated:
            transport.update(
                {
                    key: value
                    for key, value in selection.items()
                    if key not in {"parameters", "selection_origin"}
                }
            )
        transport["enabled"] = active
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
            raise _error(name, [], "invalid_transport", str(exc)) from exc
        result[name] = {
            **validated,
            "parameters": parameters,
            "selection_origin": origin,
        }
    return result


def export_provider_catalogue(packaged_defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Export bounded editable metadata independently of installation validity."""

    plugins = get_registered_api_components()
    if len(packaged_defaults) > 64:
        raise ValueError("Provider catalogue exceeds 64 entries")
    result: dict[str, Any] = {}
    for name, defaults in packaged_defaults.items():
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
            "enabled": defaults.get("enabled", True),
            "capability": plugin.capability.value,
            "hazards": sorted(h.value for h in plugin.hazards),
            "display_name": title,
            "description": description,
            "parameter_schema": schema,
            "required_when_enabled": sorted(plugin.required_when_enabled),
            "parameter_defaults": {
                key: value.get_default(call_default_factory=True)
                for key, value in plugin.parameter_model.model_fields.items()
                if not value.is_required()
                and value.get_default(call_default_factory=True) is not None
            },
            "legacy_parameter_paths": {
                key: list(value) for key, value in plugin.legacy_parameter_paths.items()
            },
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
