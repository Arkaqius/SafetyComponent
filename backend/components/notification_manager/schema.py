"""Pydantic schema and validation for notification configuration."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from pydantic import ConfigDict, ValidationError, field_validator

from components.core.pydantic_utils import StrictBaseModel, log_extra_keys


class NotificationConfig(StrictBaseModel):
    """Schema for notification configuration."""

    model_config = ConfigDict(extra="allow")

    light_entity: Optional[str] = None
    alarm_entity: Optional[str] = None
    dashboard_1_entity: Optional[str] = None
    dashboard_2_entity: Optional[str] = None
    dashboard_3_entity: Optional[str] = None
    dashboard_4_entity: Optional[str] = None

    @field_validator(
        "dashboard_1_entity",
        "dashboard_2_entity",
        "dashboard_3_entity",
        "dashboard_4_entity",
    )
    @classmethod
    def _validate_dashboard_sensor(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(
            r"sensor\.[a-z0-9_]+", value
        ):
            raise ValueError(
                "dashboard notification entity must be a valid sensor entity_id"
            )
        return value


def validate_notification_config(
    notification_cfg: dict[str, Any],
    *,
    strict_validation: bool = True,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Validate notification configuration via Pydantic schema."""

    try:
        validated = NotificationConfig.model_validate(
            notification_cfg, context={"strict_validation": strict_validation}
        )
        if not strict_validation:
            log_extra_keys(validated, log, "user_config.notification")
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return validated.model_dump()
