"""Utility for validating and normalizing the SafetyFunctions app configuration."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict

from pydantic import ValidationError

from components.app_config_validator.schema import AppCfg
from components.core.pydantic_utils import log_extra_keys
from components.faults_manager.schema import validate_faults_config
from components.notification_manager.schema import validate_notification_config
from components.external_apis.gios_air_quality.schema import (
    COMPONENT_NAME as GIOS_COMPONENT_NAME,
    GiosAirQualityConfig,
)
from components.external_apis.imgw_warnings.schema import (
    COMPONENT_NAME as IMGW_COMPONENT_NAME,
    ImgwWarningsConfig,
)
from components.external_apis.open_meteo_air_quality.schema import (
    COMPONENT_NAME as OPEN_METEO_AQ_COMPONENT_NAME,
    OpenMeteoAirQualityConfig,
)
from components.external_apis.open_meteo_weather.schema import (
    COMPONENT_NAME as OPEN_METEO_WEATHER_COMPONENT_NAME,
    OpenMeteoWeatherConfig,
)
from components.external_apis.paa_radiation.schema import (
    COMPONENT_NAME as PAA_COMPONENT_NAME,
    PaaRadiationConfig,
)
from components.safetycomponents.external_hazard.schema import (
    COMPONENT_NAME as EXTERNAL_HAZARD_COMPONENT_NAME,
    validate_external_hazard_config,
)
from components.safetycomponents.safety_doors.schema import (
    COMPONENT_NAME as SAFETY_DOORS_COMPONENT_NAME,
    validate_safety_doors_config,
)
from components.safetycomponents.temperature.schema import (
    COMPONENT_NAME as TEMPERATURE_COMPONENT_NAME,
    validate_temperature_config,
)


class AppCfgValidationError(Exception):
    """Raised when the provided app configuration does not satisfy the schema."""

SUPPORTED_CONFIG_VERSION = 1
ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
REQUIRED_EXTERNAL_API_COMPONENTS = (
    OPEN_METEO_WEATHER_COMPONENT_NAME,
    IMGW_COMPONENT_NAME,
    GIOS_COMPONENT_NAME,
    OPEN_METEO_AQ_COMPONENT_NAME,
    PAA_COMPONENT_NAME,
)


def _log_warning(log: Callable[..., None] | None, message: str) -> None:
    if not log:
        return
    try:
        log(message, level="WARNING")
    except TypeError:
        log(message)


def _collect_entity_ids(runtime_cfg: Dict[str, Any]) -> list[tuple[str, str]]:
    user_cfg = runtime_cfg.get("user_config", {})
    entity_ids: list[tuple[str, str]] = []

    common_entities = user_cfg.get("common_entities", {}) or {}
    for key, value in common_entities.items():
        if isinstance(value, str):
            entity_ids.append((f"user_config.common_entities.{key}", value))

    notification_cfg = user_cfg.get("notification", {}) or {}
    for key, value in notification_cfg.items():
        if key.endswith("_entity") and isinstance(value, str):
            entity_ids.append((f"user_config.notification.{key}", value))

    components_cfg = user_cfg.get("safety_components", {}) or {}
    temperature_cfg = components_cfg.get(TEMPERATURE_COMPONENT_NAME)
    if isinstance(temperature_cfg, list):
        for room in temperature_cfg:
            if not isinstance(room, dict):
                continue
            for room_name, room_cfg in room.items():
                if not isinstance(room_cfg, dict):
                    continue
                for key in (
                    "temperature_sensor",
                    "window_sensor",
                    "actuator",
                ):
                    value = room_cfg.get(key)
                    if isinstance(value, str):
                        entity_ids.append(
                            (
                                "user_config.safety_components."
                                f"{TEMPERATURE_COMPONENT_NAME}."
                                f"{room_name}.{key}",
                                value,
                            )
                        )

    safety_doors_cfg = components_cfg.get(SAFETY_DOORS_COMPONENT_NAME)
    if isinstance(safety_doors_cfg, list):
        for door in safety_doors_cfg:
            if not isinstance(door, dict):
                continue
            for door_name, door_cfg in door.items():
                if not isinstance(door_cfg, dict):
                    continue
                entity_id = door_cfg.get("entity_id")
                if isinstance(entity_id, str):
                    entity_ids.append(
                        (
                            "user_config.safety_components."
                            f"{SAFETY_DOORS_COMPONENT_NAME}."
                            f"{door_name}.entity_id",
                            entity_id,
                        )
                    )
                condition = door_cfg.get("condition")
                if isinstance(condition, dict):
                    condition_entity_id = condition.get("entity_id")
                    if isinstance(condition_entity_id, str):
                        entity_ids.append(
                            (
                                "user_config.safety_components."
                                f"{SAFETY_DOORS_COMPONENT_NAME}."
                                f"{door_name}.condition.entity_id",
                                condition_entity_id,
                            )
                        )

    external_hazard_cfg = components_cfg.get(EXTERNAL_HAZARD_COMPONENT_NAME)
    if isinstance(external_hazard_cfg, dict):
        openings = external_hazard_cfg.get("openings", {})
        if isinstance(openings, dict):
            for opening_name, opening_cfg in openings.items():
                if not isinstance(opening_cfg, dict):
                    continue
                entity_id = opening_cfg.get("entity_id")
                if isinstance(entity_id, str):
                    entity_ids.append(
                        (
                            "user_config.safety_components."
                            f"{EXTERNAL_HAZARD_COMPONENT_NAME}."
                            f"openings.{opening_name}.entity_id",
                            entity_id,
                        )
                    )

    return entity_ids


def _validate_entity_id_syntax(entity_ids: list[tuple[str, str]]) -> list[str]:
    invalid = []
    for path, entity_id in entity_ids:
        if not ENTITY_ID_PATTERN.match(entity_id):
            invalid.append(f"{path}={entity_id}")
    return invalid


def _validate_entity_existence(
    hass: Any, entity_ids: list[tuple[str, str]]
) -> list[str]:
    missing = []
    for path, entity_id in entity_ids:
        try:
            state = hass.get_state(entity_id)
        except Exception as exc:
            missing.append(f"{path}={entity_id} ({exc})")
            continue
        if state is None:
            missing.append(f"{path}={entity_id}")
    return missing


def _resolve_area_name(hass: Any, area_id: str, config_path: str) -> str:
    """Resolve and validate a Home Assistant area reference."""
    render_template = getattr(hass, "render_template", None)
    if not callable(render_template):
        raise AppCfgValidationError(
            "Home Assistant area resolution is unavailable; "
            f"cannot validate {config_path}={area_id}"
        )

    template = f"{{{{ area_name({json.dumps(area_id)}) }}}}"
    try:
        resolved = render_template(template)
    except Exception as exc:
        raise AppCfgValidationError(
            f"Unable to resolve {config_path}={area_id}: {exc}"
        ) from exc

    if resolved is None or str(resolved).strip().lower() in {
        "",
        "none",
        "unknown",
        "unavailable",
    }:
        raise AppCfgValidationError(
            f"Unknown Home Assistant area: {config_path}={area_id}"
        )
    return str(resolved).strip()


def _resolve_area_names(runtime_cfg: Dict[str, Any], hass: Any) -> None:
    """Attach current Home Assistant area names to location-aware components."""
    components = runtime_cfg["user_config"]["safety_components"]
    for component_name in (
        TEMPERATURE_COMPONENT_NAME,
        SAFETY_DOORS_COMPONENT_NAME,
    ):
        component_cfg = components.get(component_name)
        if not isinstance(component_cfg, list):
            continue
        for entry in component_cfg:
            if not isinstance(entry, dict):
                continue
            for item_name, item_cfg in entry.items():
                if not isinstance(item_cfg, dict):
                    continue
                area_id = item_cfg.get("area_id")
                if not isinstance(area_id, str):
                    continue
                config_path = (
                    "user_config.safety_components."
                    f"{component_name}.{item_name}.area_id"
                )
                item_cfg["area_name"] = _resolve_area_name(
                    hass,
                    area_id,
                    config_path,
                )

    external_cfg = components.get(EXTERNAL_HAZARD_COMPONENT_NAME)
    if isinstance(external_cfg, dict):
        openings = external_cfg.get("openings", {})
        if isinstance(openings, dict):
            for opening_name, opening_cfg in openings.items():
                if not isinstance(opening_cfg, dict):
                    continue
                area_id = opening_cfg.get("area_id")
                if not isinstance(area_id, str):
                    continue
                config_path = (
                    "user_config.safety_components."
                    f"{EXTERNAL_HAZARD_COMPONENT_NAME}."
                    f"openings.{opening_name}.area_id"
                )
                opening_cfg["area_name"] = _resolve_area_name(
                    hass, area_id, config_path
                )


def _validate_api_components(
    cfg: AppCfg,
    *,
    strict_validation: bool,
) -> Dict[str, Any]:
    """Merge provider policy and installation binding, then validate each adapter."""

    policy = cfg.app_config.external_hazard_policy
    if policy is None:
        return {}
    raw_api_components = cfg.user_config.api_components
    validators = {
        OPEN_METEO_WEATHER_COMPONENT_NAME: OpenMeteoWeatherConfig,
        IMGW_COMPONENT_NAME: ImgwWarningsConfig,
        GIOS_COMPONENT_NAME: GiosAirQualityConfig,
        OPEN_METEO_AQ_COMPONENT_NAME: OpenMeteoAirQualityConfig,
        PAA_COMPONENT_NAME: PaaRadiationConfig,
    }
    normalized: Dict[str, Any] = {}
    for name, schema in validators.items():
        user_binding = raw_api_components.get(name)
        if not isinstance(user_binding, dict):
            raise ValueError(f"Missing user_config.api_components.{name}")
        provider_policy = policy.providers.get(name)
        if not isinstance(provider_policy, dict):
            raise ValueError(f"Missing app_config.external_hazard_policy.providers.{name}")
        merged = {**provider_policy, **user_binding}
        if name == OPEN_METEO_WEATHER_COMPONENT_NAME:
            merged["forecast_horizon_hours"] = policy.weather.forecast_horizon_hours
        validated = schema.model_validate(
            merged, context={"strict_validation": strict_validation}
        )
        normalized[name] = validated.model_dump()
    unknown_policy = sorted(set(policy.providers) - set(validators))
    if strict_validation and unknown_policy:
        raise ValueError(
            "Unknown external hazard provider policies: "
            + ", ".join(unknown_policy)
        )
    unknown = sorted(set(raw_api_components) - set(validators))
    if strict_validation and unknown:
        raise ValueError(f"Unknown API components: {', '.join(unknown)}")
    return normalized


def _to_runtime(
    cfg: AppCfg,
    *,
    strict_validation: bool,
    log: Callable[..., None] | None,
) -> Dict[str, Any]:
    runtime = cfg.model_dump(by_alias=True)
    runtime_user_cfg = runtime.get("user_config", {})

    enabled_components = cfg.user_config.enabled_components()
    external_enabled = EXTERNAL_HAZARD_COMPONENT_NAME in enabled_components
    if external_enabled:
        if cfg.app_config.external_hazard_policy is None:
            raise ValueError("ExternalHazardComponent requires external_hazard_policy")
        if cfg.user_config.site is None:
            raise ValueError("ExternalHazardComponent requires user_config.site")
        runtime_user_cfg["site"] = cfg.user_config.site.model_dump()
        runtime_user_cfg["api_components"] = _validate_api_components(
            cfg, strict_validation=strict_validation
        )
    else:
        runtime_user_cfg["api_components"] = {}
    runtime_components: Dict[str, Any] = {}
    for name, component_cfg in enabled_components.items():
        if name == TEMPERATURE_COMPONENT_NAME:
            runtime_components[name] = validate_temperature_config(
                component_cfg,
                strict_validation=strict_validation,
                log=log,
                calibration=cfg.app_config.calibration.temperature.model_dump(),
            )
        elif name == SAFETY_DOORS_COMPONENT_NAME:
            runtime_components[name] = validate_safety_doors_config(
                component_cfg,
                strict_validation=strict_validation,
                log=log,
            )
        elif name == EXTERNAL_HAZARD_COMPONENT_NAME:
            if cfg.app_config.external_hazard_policy is None:
                raise ValueError("ExternalHazardComponent policy is missing")
            runtime_components[name] = validate_external_hazard_config(
                component_cfg,
                policy=cfg.app_config.external_hazard_policy,
                strict_validation=strict_validation,
            )
            runtime_components[name]["enabled_providers"] = sorted(
                provider_name
                for provider_name, provider_cfg in runtime_user_cfg[
                    "api_components"
                ].items()
                if provider_cfg.get("enabled", True)
            )
        else:
            runtime_components[name] = component_cfg

    runtime_user_cfg["safety_components"] = runtime_components
    runtime_user_cfg["notification"] = validate_notification_config(
        cfg.user_config.notification,
        strict_validation=strict_validation,
        log=log,
    )

    runtime["user_config"] = runtime_user_cfg
    runtime["app_config"]["faults"] = validate_faults_config(
        cfg.app_config.faults,
        strict_validation=strict_validation,
        log=log,
    )
    return runtime


class AppCfgValidator:
    """Facade for validating and normalizing the SafetyFunctions configuration."""

    @staticmethod
    def validate(
        raw_cfg: Dict[str, Any],
        *,
        hass: Any | None = None,
        log: Callable[..., None] | None = None,
    ) -> Dict[str, Any]:
        strict_validation = (
            raw_cfg.get("app_config", {}).get("strict_validation", True)
        )
        try:
            cfg = AppCfg.model_validate(
                raw_cfg, context={"strict_validation": strict_validation}
            )
            if cfg.app_config.config_version != SUPPORTED_CONFIG_VERSION:
                raise AppCfgValidationError(
                    "Unsupported config_version "
                    f"{cfg.app_config.config_version}; "
                    f"supported={SUPPORTED_CONFIG_VERSION}"
                )
            runtime_cfg = _to_runtime(
                cfg,
                strict_validation=strict_validation,
                log=log,
            )
            if not runtime_cfg["app_config"]["faults"]:
                raise AppCfgValidationError(
                    "app_config.faults must define at least one fault"
                )
            if not runtime_cfg["user_config"]["safety_components"]:
                raise AppCfgValidationError(
                    "user_config.safety_components must enable at least one component"
                )
        except (ValidationError, ValueError) as exc:
            raise AppCfgValidationError(str(exc))

        if hass is not None:
            _resolve_area_names(runtime_cfg, hass)
        else:
            _log_warning(
                log,
                "Home Assistant was not provided; skipping area existence checks.",
            )

        if not strict_validation:
            log_extra_keys(cfg, log, "root")
            log_extra_keys(cfg.app_config, log, "app_config")
            log_extra_keys(cfg.app_config.validation, log, "app_config.validation")
            log_extra_keys(cfg.app_config.calibration, log, "app_config.calibration")
            log_extra_keys(
                cfg.app_config.calibration.temperature,
                log,
                "app_config.calibration.temperature",
            )
            log_extra_keys(cfg.user_config, log, "user_config")
            log_extra_keys(cfg.user_config.mqtt, log, "user_config.mqtt")

        entity_ids = _collect_entity_ids(runtime_cfg)

        if cfg.app_config.validation.validate_entity_id_syntax:
            invalid = _validate_entity_id_syntax(entity_ids)
            if invalid:
                raise AppCfgValidationError(
                    "Invalid entity_id syntax: " + ", ".join(invalid)
                )

        if cfg.app_config.validation.validate_entity_existence:
            if hass is None:
                _log_warning(
                    log,
                    "validate_entity_existence is true but hass was not provided; "
                    "skipping existence checks.",
                )
            else:
                missing = _validate_entity_existence(hass, entity_ids)
                if missing:
                    raise AppCfgValidationError(
                        "Missing entity_ids: " + ", ".join(missing)
                    )

        return runtime_cfg
