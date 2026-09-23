#!/usr/bin/env python3
"""Compile the deployable AppDaemon config from system and user sources."""

from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from configuration_model import (
    CONFIGURATION_MODEL_VERSION,
    UserConfigurationV2,
    compile_user_config_v2,
    deep_merge,
    user_configuration_schema,
    validate_user_configuration_v2,
)
from system_configuration import (
    system_configuration_schema,
    validate_system_configuration,
)

BACKEND_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BACKEND_DIR / "config"
SYSTEM_CONFIG_PATH = CONFIG_DIR / "system_config.yml"
USER_CONFIG_PATH = CONFIG_DIR / "user_config.yml"
OUTPUT_PATH = BACKEND_DIR / "app_cfg.yaml"


def load_mapping(path: Path) -> dict[str, Any]:
    """Load one YAML source and require a mapping root."""

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def compile_config(
    system_path: Path = SYSTEM_CONFIG_PATH,
    user_path: Path = USER_CONFIG_PATH,
    *,
    log_level: str | None = None,
    home_assistant_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete AppDaemon configuration."""

    system = validate_system_configuration(load_mapping(system_path))
    user = load_mapping(user_path)
    app_definition = system.get("app_definition")
    validation = system.get("validation")
    calibration = system.get("calibration")
    runtime_cfg = system.get("runtime_cfg")
    user_config = user.get("user_config")
    for name, value in (
        ("app_definition", app_definition),
        ("validation", validation),
        ("calibration", calibration),
        ("runtime_cfg", runtime_cfg),
        ("user_config", user_config),
    ):
        if not isinstance(value, dict):
            raise ValueError(f"Missing mapping: {name}")

    model_version = user_config.get("model_version")
    if model_version != CONFIGURATION_MODEL_VERSION:
        raise ValueError(
            f"Unsupported user_config.model_version={model_version}; "
            f"supported={CONFIGURATION_MODEL_VERSION}"
        )
    configured_version = system.get("system_config", {}).get("version")
    if configured_version != CONFIGURATION_MODEL_VERSION:
        raise ValueError(
            "system_config.version does not support "
            f"user model_version={model_version}"
        )
    source = validate_user_configuration_v2(user_config)
    runtime_defaults = _build_runtime_defaults(calibration, runtime_cfg)
    if source.installation.site is not None and home_assistant_config is None:
        raise ValueError(
            "Home Assistant Core location is required to compile site configuration"
        )
    merged_user_config = compile_user_config_v2(
        runtime_defaults, user_config, home_assistant_config or {}
    )
    app_config = _build_app_config(validation, calibration, runtime_cfg, source)
    resolved_app_definition = copy.deepcopy(app_definition)
    if log_level is not None:
        resolved_app_definition["log_level"] = log_level.upper()

    return {
        "SafetyFunctions": {
            **resolved_app_definition,
            "app_config": app_config,
            "user_config": merged_user_config,
        }
    }


def _strip_default_prefix(values: dict[str, Any]) -> dict[str, Any]:
    """Translate system-owned default names to effective runtime names."""

    return {
        key.removeprefix("default_"): copy.deepcopy(value)
        for key, value in values.items()
    }


def _build_runtime_defaults(
    calibration: dict[str, Any], runtime_cfg: dict[str, Any]
) -> dict[str, Any]:
    """Build installation-independent defaults consumed by the v2 compiler."""

    temperature = calibration.get("temperature", {})
    entity_monitor = calibration.get("entity_monitor", {})
    external_hazard = calibration.get("external_hazard", {})
    safety_door = calibration.get("safety_door", {})
    internal_hazard = copy.deepcopy(
        calibration.get("internal_environmental_hazard", {})
    )
    internal_hazard["health_failure_debounce_seconds"] = internal_hazard.pop(
        "default_health_failure_debounce_seconds"
    )
    internal_hazard["health_recovery_debounce_seconds"] = internal_hazard.pop(
        "default_health_recovery_debounce_seconds"
    )
    providers = runtime_cfg.get("providers", {})

    return {
        "notification": copy.deepcopy(runtime_cfg.get("notification", {})),
        "recovery": copy.deepcopy(runtime_cfg.get("recovery", {})),
        "mqtt": copy.deepcopy(runtime_cfg.get("mqtt", {})),
        "api_components": {
            name: {"enabled": bool(config.get("enabled", True))}
            for name, config in providers.items()
        },
        "safety_components": {
            "TemperatureComponent": {
                "defaults": {
                    "CAL_LOW_TEMP_THRESHOLD": temperature.get(
                        "default_low_temperature_c"
                    ),
                    "CAL_HIGH_TEMP_THRESHOLD": temperature.get(
                        "default_high_temperature_c"
                    ),
                    "CAL_FORECAST_TIMESPAN": temperature.get("forecast_horizon_hours"),
                }
            },
            "SafetyDoorsComponent": {
                "defaults": {
                    "timeout_seconds": safety_door.get("default_timeout_seconds")
                }
            },
            "ExternalHazardComponent": {
                "defaults": {
                    "hazards": copy.deepcopy(external_hazard.get("default_hazards", []))
                }
            },
            "EntityMonitorComponent": {
                "component_overrides": copy.deepcopy(
                    entity_monitor.get("component_overrides", {})
                )
            },
            "InternalEnvironmentalHazardMonitorComponent": internal_hazard,
        },
    }


def _build_app_config(
    validation: dict[str, Any],
    calibration: dict[str, Any],
    runtime_cfg: dict[str, Any],
    source: UserConfigurationV2,
) -> dict[str, Any]:
    """Resolve system defaults and installation overrides for runtime policy."""

    temperature = {
        key: copy.deepcopy(value)
        for key, value in calibration.get("temperature", {}).items()
        if not key.startswith("default_") and key != "forecast_horizon_hours"
    }
    system_entity_monitor = calibration.get("entity_monitor", {})
    entity_monitor = {
        "startup_grace_seconds": system_entity_monitor.get(
            "default_startup_grace_seconds"
        ),
        "default_failure_debounce_seconds": system_entity_monitor.get(
            "default_failure_debounce_seconds"
        ),
        "default_recovery_debounce_seconds": system_entity_monitor.get(
            "default_recovery_debounce_seconds"
        ),
        "evaluation_interval_seconds": system_entity_monitor.get(
            "default_evaluation_interval_seconds"
        ),
        "unhealthy_summary_limit": system_entity_monitor.get("unhealthy_summary_limit"),
        "component_overrides": copy.deepcopy(
            system_entity_monitor.get("component_overrides", {})
        ),
    }
    user_entity_monitor = source.installation.component_settings.entity_monitor
    if user_entity_monitor.startup_grace_seconds is not None:
        entity_monitor["startup_grace_seconds"] = (
            user_entity_monitor.startup_grace_seconds
        )
    if user_entity_monitor.evaluation_interval_seconds is not None:
        entity_monitor["evaluation_interval_seconds"] = (
            user_entity_monitor.evaluation_interval_seconds
        )

    external = calibration.get("external_hazard", {})
    weather = _strip_default_prefix(external.get("weather", {}))
    air_quality = _strip_default_prefix(external.get("outdoor_air_quality", {}))
    user_external = source.installation.component_settings.external_hazard
    weather = deep_merge(weather, user_external.weather.model_dump(exclude_none=True))
    air_quality = deep_merge(
        air_quality,
        user_external.outdoor_air_quality.model_dump(exclude_none=True),
    )
    provider_policy = {
        name: {
            key: copy.deepcopy(value)
            for key, value in provider.items()
            if key != "enabled"
        }
        for name, provider in runtime_cfg.get("providers", {}).items()
    }

    return {
        "validation": copy.deepcopy(validation),
        "calibration": {
            "temperature": temperature,
            "entity_monitor": entity_monitor,
        },
        "external_hazard_policy": {
            "actuation_mode": external.get("actuation_mode"),
            "clear_delay_seconds": external.get("clear_delay_seconds"),
            "weather": weather,
            "outdoor_air_quality": air_quality,
            "providers": provider_policy,
        },
        "faults": copy.deepcopy(runtime_cfg.get("faults", {})),
    }


def write_compiled_config(config: dict[str, Any], output_path: Path) -> None:
    """Write deterministic generated YAML with an ownership header."""

    body = yaml.safe_dump(
        config,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    output_path.write_text(
        "# Generated by backend/build_app_config.py.\n"
        "# Edit backend/config/user_config.yml for the installation model or\n"
        "# backend/config/system_config.yml for software policy/calibration.\n" + body,
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--print-user-schema",
        action="store_true",
        help="Print the complete user_config model v2 JSON Schema and exit.",
    )
    parser.add_argument(
        "--print-system-schema",
        action="store_true",
        help="Print the complete system_config JSON Schema and exit.",
    )
    parser.add_argument(
        "--system",
        type=Path,
        default=SYSTEM_CONFIG_PATH,
        help="Path to the system policy and calibration source.",
    )
    parser.add_argument(
        "--user",
        type=Path,
        default=USER_CONFIG_PATH,
        help="Path to the installation-owned configuration source.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Path for the generated AppDaemon apps file.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "FATAL"),
        help="Override the packaged AppDaemon application log level.",
    )
    parser.add_argument(
        "--home-assistant-config",
        type=Path,
        help="Current Home Assistant Core /api/config JSON, required for site coordinates.",
    )
    args = parser.parse_args()
    if args.print_user_schema:
        print(
            json.dumps(
                user_configuration_schema(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.print_system_schema:
        print(
            json.dumps(
                system_configuration_schema(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    compiled = compile_config(
        system_path=args.system,
        user_path=args.user,
        log_level=args.log_level,
        home_assistant_config=(
            json.loads(args.home_assistant_config.read_text(encoding="utf-8"))
            if args.home_assistant_config
            else None
        ),
    )
    if args.check:
        existing = load_mapping(args.output)
        if existing != compiled:
            raise SystemExit(f"{args.output} is not up to date")
        return
    write_compiled_config(compiled, args.output)


if __name__ == "__main__":
    main()
