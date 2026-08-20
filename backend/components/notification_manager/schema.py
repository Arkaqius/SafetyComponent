"""Validated configuration for mobile notification delivery."""

from __future__ import annotations

import re
from typing import Any, Callable, Literal, Optional

from pydantic import (
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys


_SERVICE_RE = re.compile(r"^[a-z0-9_]+/[a-z0-9_]+$")
_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class MobileProfile(StrictBaseModel):
    """Android and iOS presentation properties for one safety level."""

    color: str
    notification_icon: str
    android_channel: str
    android_importance: Literal["default", "high", "max"] = "default"
    android_priority: Literal["normal", "high"] = "normal"
    android_ttl: int = Field(default=0, ge=0)
    vibration_pattern: str | None = None
    ios_interruption_level: Literal[
        "passive", "active", "time-sensitive", "critical"
    ] = "active"
    ios_critical_sound: bool = False

    @model_validator(mode="after")
    def _validate_critical_sound(self) -> "MobileProfile":
        if self.ios_critical_sound and self.ios_interruption_level != "critical":
            raise ValueError(
                "ios_critical_sound requires ios_interruption_level=critical"
            )
        return self


def _default_profiles() -> dict[int, MobileProfile]:
    return {
        1: MobileProfile(
            color="#FF0000",
            notification_icon="mdi:exit-run",
            android_channel="Safety critical",
            android_importance="max",
            android_priority="high",
            android_ttl=0,
            vibration_pattern="100, 1000, 100, 1000, 100",
            ios_interruption_level="time-sensitive",
        ),
        2: MobileProfile(
            color="#FFA500",
            notification_icon="mdi:hazard-lights",
            android_channel="Safety hazards",
            android_importance="high",
            android_priority="high",
            android_ttl=0,
            vibration_pattern="100, 500, 100, 500",
            ios_interruption_level="time-sensitive",
        ),
        3: MobileProfile(
            color="#FFFF00",
            notification_icon="mdi:home-alert",
            android_channel="Safety warnings",
            android_importance="default",
            android_priority="normal",
            android_ttl=0,
            ios_interruption_level="active",
        ),
    }


class MobilePushConfig(StrictBaseModel):
    """Explicit Home Assistant Companion notification routing."""

    services: list[str] = Field(default_factory=lambda: ["notify/all_phones"])
    default_url: str = "https://ha.kojbito.org/5c36e1c9_hakit"
    profiles: dict[int, MobileProfile] = Field(default_factory=_default_profiles)

    @field_validator("services")
    @classmethod
    def _validate_services(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(service.strip().lower() for service in value))
        if not normalized:
            raise ValueError("At least one explicit mobile notify service is required")
        invalid = [
            service for service in normalized if not _SERVICE_RE.fullmatch(service)
        ]
        if invalid:
            raise ValueError(
                "Mobile notify services must use AppDaemon domain/service format: "
                + ", ".join(invalid)
            )
        if "notify/notify" in normalized:
            raise ValueError(
                "notify/notify is ambiguous; configure an explicit group or device"
            )
        if any(not service.startswith("notify/") for service in normalized):
            raise ValueError("Mobile notification services must use the notify domain")
        return normalized

    @field_validator("default_url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://", "/")):
            raise ValueError(
                "Notification URL must be HTTPS, HTTP, or an HA-relative path"
            )
        return value

    @field_validator("profiles")
    @classmethod
    def _validate_profiles(
        cls, value: dict[int, MobileProfile]
    ) -> dict[int, MobileProfile]:
        if set(value) != {1, 2, 3}:
            raise ValueError("Mobile profiles must define exactly levels 1, 2, and 3")
        return value


class RetryPolicy(StrictBaseModel):
    """Bounded retry and deadline policy for HA service acceptance."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    base_delay_seconds: int = Field(default=5, ge=1, le=300)
    max_delay_seconds: int = Field(default=60, ge=1, le=3600)
    deadlines_seconds: dict[int, int] = Field(
        default_factory=lambda: {1: 10, 2: 30, 3: 30}
    )

    @field_validator("deadlines_seconds")
    @classmethod
    def _validate_deadlines(cls, value: dict[int, int]) -> dict[int, int]:
        if set(value) != {1, 2, 3} or any(seconds <= 0 for seconds in value.values()):
            raise ValueError(
                "Delivery deadlines must be positive for levels 1, 2, and 3"
            )
        return value

    @model_validator(mode="after")
    def _validate_backoff(self) -> "RetryPolicy":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be greater than or equal to "
                "base_delay_seconds"
            )
        return self


class LevelOneRepeatPolicy(StrictBaseModel):
    """Controlled L1 repeat behavior until acknowledgement."""

    enabled: bool = True
    interval_seconds: int = Field(default=60, ge=10, le=3600)
    max_repeats: int = Field(default=3, ge=0, le=100)


class PersistenceConfig(StrictBaseModel):
    """AppDaemon-external state used to survive app reloads."""

    enabled: bool = True
    state_file: str = "/config/appdaemon/notification_state.json"

    @field_validator("state_file")
    @classmethod
    def _validate_state_file(cls, value: str) -> str:
        if not value.strip() or not value.lower().endswith(".json"):
            raise ValueError("Notification state_file must be a non-empty JSON path")
        return value


class LocalAnnunciatorConfig(StrictBaseModel):
    """Optional local output bindings, independent from mobile transport."""

    light_entity: str | None = None
    alarm_entity: str | None = None

    @field_validator("light_entity", "alarm_entity")
    @classmethod
    def _validate_entity(cls, value: str | None) -> str | None:
        if value is not None and not _ENTITY_RE.fullmatch(value):
            raise ValueError(f"Invalid Home Assistant entity ID: {value}")
        return value


class NotificationConfig(StrictBaseModel):
    """Complete notification lifecycle and delivery configuration."""

    model_config = ConfigDict(extra="allow")

    mobile: MobilePushConfig = Field(default_factory=MobilePushConfig)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    level_one_repeat: LevelOneRepeatPolicy = Field(default_factory=LevelOneRepeatPolicy)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    local: LocalAnnunciatorConfig = Field(default_factory=LocalAnnunciatorConfig)
    diagnostics_sensor_id: str = "sensor.notification_delivery_health"
    wan_entity: str | None = None
    wan_online_states: list[str] = Field(
        default_factory=lambda: ["on", "online", "connected"]
    )
    allowed_detail_fields: list[str] = Field(
        default_factory=lambda: [
            "location",
            "hazard",
            "openings",
            "observed_value",
            "threshold",
            "evidence_kind",
            "providers",
            "capability",
            "source",
            "source_time",
            "valid_to",
            "freshness",
            "source_reference",
            "severity",
            "confirmation",
            "stations",
            "recommendation",
        ]
    )

    # Backward-compatible input aliases. Runtime code consumes ``local`` only.
    light_entity: Optional[str] = None
    alarm_entity: Optional[str] = None

    @field_validator("diagnostics_sensor_id", "wan_entity")
    @classmethod
    def _validate_optional_entity(cls, value: str | None) -> str | None:
        if value is not None and not _ENTITY_RE.fullmatch(value):
            raise ValueError(f"Invalid Home Assistant entity ID: {value}")
        return value

    @field_validator("wan_online_states", "allowed_detail_fields")
    @classmethod
    def _normalize_unique_strings(cls, value: list[str]) -> list[str]:
        normalized = list(
            dict.fromkeys(item.strip().lower() for item in value if item.strip())
        )
        if not normalized:
            raise ValueError("Configured string list must not be empty")
        return normalized

    @model_validator(mode="after")
    def _merge_legacy_local_bindings(self) -> "NotificationConfig":
        if self.light_entity and not self.local.light_entity:
            self.local.light_entity = self.light_entity
        if self.alarm_entity and not self.local.alarm_entity:
            self.local.alarm_entity = self.alarm_entity
        return self


def validate_notification_config(
    notification_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Validate and normalize notification configuration."""

    try:
        validated = NotificationConfig.model_validate(
            notification_cfg, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            log_extra_keys(validated, log, "user_config.notification")
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    runtime = validated.model_dump()
    runtime.pop("light_entity", None)
    runtime.pop("alarm_entity", None)
    return runtime
