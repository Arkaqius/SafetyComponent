"""Utility for validating and normalizing the SafetyFunctions app configuration."""

from __future__ import annotations

from typing import Any, Callable, Dict
import re

from pydantic import ValidationError

from components.app_config_validator.schema import AppCfg
from components.core.pydantic_utils import log_extra_keys
from components.faults_manager.schema import validate_faults_config
from components.notification_manager.schema import validate_notification_config
from components.safetycomponents.temperature.schema import (
    COMPONENT_NAME as TEMPERATURE_COMPONENT_NAME,
    validate_temperature_config,
)


class AppCfgValidationError(Exception):
    """Raised when the provided app configuration does not satisfy the schema."""

SUPPORTED_CONFIG_VERSION = 1
ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


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
                    "temperature_sensor_rate",
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


def _to_runtime(
    cfg: AppCfg,
    *,
    strict_validation: bool,
    log: Callable[..., None] | None,
) -> Dict[str, Any]:
    runtime = cfg.model_dump(by_alias=True)
    runtime_user_cfg = runtime.get("user_config", {})

    enabled_components = cfg.user_config.enabled_components()
    runtime_components: Dict[str, Any] = {}
    for name, component_cfg in enabled_components.items():
        if name == TEMPERATURE_COMPONENT_NAME:
            runtime_components[name] = validate_temperature_config(
                component_cfg,
                strict_validation=strict_validation,
                log=log,
                calibration=cfg.app_config.calibration.temperature.model_dump(),
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
        except (ValidationError, ValueError) as exc:
            raise AppCfgValidationError(str(exc))

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
