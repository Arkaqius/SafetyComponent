"""Build localized manual proposals without an actuator dependency."""

from __future__ import annotations

from typing import Any

from components.core.entity_names import friendly_entity_name
from components.core.localization import Localizer
from components.core.types_common import RecoveryAction, RecoveryResult, Symptom


def manual_action(
    name: str,
    *,
    subject: str,
    instruction_key: str,
    result_key: str,
    area_id: str | None = None,
    area_name: str | None = None,
    entity_id: str | None = None,
    closed_contact: bool = False,
    completion_condition: str = "owner_clear",
    manual_report_allowed: bool = False,
    purpose: str = "capability_repair",
) -> RecoveryAction:
    """Declare manual work completed by a contact or its owner's clear evidence."""

    return RecoveryAction(
        name,
        {
            "subject": subject,
            "friendly_name": subject,
            "instruction_key": instruction_key,
            "result_key": result_key,
            "area_id": area_id,
            "location": area_name,
            "entity_id": entity_id,
            "closed_contact": closed_contact,
            "completion_condition": completion_condition,
            "manual_report_allowed": manual_report_allowed,
            "purpose": purpose,
        },
        _manual_result,
    )


def _manual_result(
    hass_app: Any, symptom: Symptom, common_entities: Any, **params: Any
) -> RecoveryResult:
    """Create instructions; the component remains responsible for healthy evidence."""

    del common_entities
    localizer = getattr(hass_app, "localizer", None)
    if not isinstance(localizer, Localizer):
        localizer = Localizer()
    subject = friendly_entity_name(hass_app, params.get("entity_id"), params["subject"])
    instruction = localizer.text(params["instruction_key"], subject=subject)
    if str(params["instruction_key"]).startswith("hazard.guidance."):
        instruction = f"{subject}: {instruction}"
    expected = localizer.text(params["result_key"], subject=subject)
    closed = bool(params["closed_contact"])
    check_key = str(symptom.parameters.get("check_key", ""))
    return RecoveryResult(
        changed_sensors={params["entity_id"]: "off"} if closed else {},
        changed_actuators={},
        notifications=[instruction],
        instruction=instruction,
        execution_policy="manual",
        reason=localizer.text(f"recovery.reason_{check_key}") if check_key else "",
        source=type(symptom.module).__name__,
        completion_condition="opening_closed" if closed else params["completion_condition"],
        expected_result=expected,
        purpose="hazard_mitigation" if closed else params["purpose"],
        manual_report_allowed=params["manual_report_allowed"],
    )
