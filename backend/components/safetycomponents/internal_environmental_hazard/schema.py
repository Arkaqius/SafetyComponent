"""Configuration schema for internal environmental binary detectors."""

from __future__ import annotations

import re
from typing import Any, Callable, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys

COMPONENT_NAME = "InternalEnvironmentalHazardMonitorComponent"
HazardKind = Literal["smoke", "flammable_gas", "carbon_monoxide"]
_DETECTOR_KEY = re.compile(r"^[A-Za-z0-9]+$")


class BinaryDetectorProfile(StrictBaseModel):
    """System-owned interpretation contract for one binary detector family."""

    version: str
    provenance: str
    alarm_states: list[str] = Field(min_length=1)
    clear_states: list[str] = Field(min_length=1)
    test_states: list[str] = Field(default_factory=list)
    unavailable_states: list[str] = Field(
        default_factory=lambda: ["unknown", "unavailable"]
    )
    clear_duration_seconds: int = Field(default=30, ge=1, le=3600)
    authoritative_clear: bool = True

    @field_validator(
        "version",
        "provenance",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile text values must not be empty")
        return normalized

    @field_validator(
        "alarm_states",
        "clear_states",
        "test_states",
        "unavailable_states",
    )
    @classmethod
    def _normalize_states(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip().lower() for value in values]
        if any(not value for value in normalized):
            raise ValueError("detector states must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("detector states must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def _validate_state_contract(self) -> "BinaryDetectorProfile":
        state_sets = {
            "alarm": set(self.alarm_states),
            "clear": set(self.clear_states),
            "test": set(self.test_states),
            "unavailable": set(self.unavailable_states),
        }
        names = list(state_sets)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                overlap = state_sets[left_name] & state_sets[right_name]
                if overlap:
                    raise ValueError(
                        f"profile {left_name}/{right_name} states overlap: "
                        f"{sorted(overlap)}"
                    )
        if not self.authoritative_clear:
            raise ValueError(
                "enabled binary profiles require authoritative clear semantics"
            )
        return self


class InternalDetectorConfig(StrictBaseModel):
    """Installation binding for one hazard channel."""

    area_id: str
    entity_id: str
    friendly_name: str
    hazard: HazardKind
    profile: str
    gas_identity: str | None = None
    enabled: bool = True

    @field_validator("area_id", "entity_id", "friendly_name", "profile")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("detector binding values must not be empty")
        return normalized

    @field_validator("gas_identity")
    @classmethod
    def _normalize_gas_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("gas_identity must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_gas_identity(self) -> "InternalDetectorConfig":
        if self.hazard == "flammable_gas" and self.gas_identity is None:
            raise ValueError("flammable_gas detectors require gas_identity")
        if self.hazard != "flammable_gas" and self.gas_identity is not None:
            raise ValueError("gas_identity is valid only for flammable_gas detectors")
        return self


class InternalEnvironmentPersistence(StrictBaseModel):
    """Bounded state persistence policy."""

    enabled: bool = True
    state_file: str = "/config/appdaemon/internal_environment_state.json"
    maximum_detectors: int = Field(default=64, ge=1, le=256)

    @field_validator("state_file")
    @classmethod
    def _state_file_not_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("state_file must not be empty")
        return normalized


class InternalEnvironmentalHazardMonitorConfig(StrictBaseModel):
    """Top-level policy and detector bindings for the internal monitor."""

    profiles: dict[str, BinaryDetectorProfile] = Field(min_length=1)
    detectors: dict[str, InternalDetectorConfig] = Field(min_length=1)
    health_failure_debounce_seconds: int = Field(default=5, ge=0, le=60)
    health_recovery_debounce_seconds: int = Field(default=60, ge=1, le=3600)
    persistence: InternalEnvironmentPersistence = Field(
        default_factory=InternalEnvironmentPersistence
    )

    @model_validator(mode="after")
    def _validate_bindings(self) -> "InternalEnvironmentalHazardMonitorConfig":
        enabled = {
            key: detector
            for key, detector in self.detectors.items()
            if detector.enabled
        }
        if not enabled:
            raise ValueError("at least one internal detector must be enabled")
        if len(enabled) > self.persistence.maximum_detectors:
            raise ValueError("enabled detector count exceeds persistence bound")

        seen_channels: set[tuple[str, str]] = set()
        for key, detector in enabled.items():
            if not _DETECTOR_KEY.fullmatch(key):
                raise ValueError(
                    f"detector key '{key}' must contain only ASCII letters and digits"
                )
            if detector.profile not in self.profiles:
                raise ValueError(
                    f"detector '{key}' references unknown profile "
                    f"'{detector.profile}'"
                )
            channel = (detector.entity_id, detector.hazard)
            if channel in seen_channels:
                raise ValueError(
                    f"duplicate detector channel for {detector.entity_id}/"
                    f"{detector.hazard}"
                )
            seen_channels.add(channel)
        return self

    def to_runtime(self) -> dict[str, Any]:
        """Return normalized policy with disabled bindings removed."""

        return {
            "profiles": {
                key: profile.model_dump() for key, profile in self.profiles.items()
            },
            "detectors": {
                key: detector.model_dump(exclude_none=True)
                for key, detector in self.detectors.items()
                if detector.enabled
            },
            "health_failure_debounce_seconds": self.health_failure_debounce_seconds,
            "health_recovery_debounce_seconds": self.health_recovery_debounce_seconds,
            "persistence": self.persistence.model_dump(),
        }


def validate_internal_environmental_hazard_config(
    raw_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Validate and normalize internal environmental detector configuration."""

    try:
        validated = InternalEnvironmentalHazardMonitorConfig.model_validate(
            raw_cfg, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            base = f"user_config.safety_components.{COMPONENT_NAME}"
            log_extra_keys(validated, log, base)
            log_extra_keys(validated.persistence, log, f"{base}.persistence")
            for key, profile in validated.profiles.items():
                log_extra_keys(profile, log, f"{base}.profiles.{key}")
            for key, detector in validated.detectors.items():
                log_extra_keys(detector, log, f"{base}.detectors.{key}")
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return validated.to_runtime()
