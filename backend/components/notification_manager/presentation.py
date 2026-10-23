"""Render concise localized mobile text without changing fault evidence."""

from __future__ import annotations

from typing import Any

from components.core.entity_names import friendly_entity_name
from components.core.localization import Localizer


class NotificationPresentation:
    """Keep operator text separate from raw fault context and delivery policy."""

    def __init__(self, app: Any, localizer: Localizer) -> None:
        self.app = app
        self.localizer = localizer

    def input_subject(self, context: dict[str, Any]) -> str | None:
        """Resolve input names without describing their evaluation status."""
        entity_ids = context.get("entity_id")
        if isinstance(entity_ids, str) and context.get("failed_check"):
            names = list(dict.fromkeys(
                friendly_entity_name(self.app, entity_id.strip(), self.localizer.text("notification.subject.input"))
                for entity_id in entity_ids.split(",") if entity_id.strip()
            ))
            return ", ".join(names) if names else None
        return None

    def problem(self, friendly_name: str | None, context: dict[str, Any]) -> str:
        """Identify affected inputs using HA names and localized failure wording."""
        subject = self.input_subject(context)
        check = str(context.get("failed_check", ""))
        if subject:
            known_checks = {"availability", "freshness", "required_value", "allowed_values", "finite_number", "numeric_range", "rate_of_change", "recovery_command"}
            return self.localizer.text(
                f"notification.input.{check if check in known_checks else 'invalid'}",
                entity=subject,
            )
        return friendly_name or self.localizer.text("notification.problem.generic")

    def title(self, problem: str, level: int, details: dict[str, Any]) -> str:
        """Put the concrete problem and location before any supporting detail."""
        location = details.get("location")
        if isinstance(location, str) and location.strip():
            problem = self.localizer.text("notification.problem.location", problem=problem, location=location)
        return self.localizer.text("notification.problem.urgent", problem=problem) if level == 1 else problem

    def body(self, recommendations: list[str], level: int) -> str:
        """Retain complete urgent instructions and bound lower-priority lists."""
        unique = list(dict.fromkeys(text.strip() for text in recommendations if text.strip()))
        if not unique:
            return self.localizer.text("notification.open_details")
        visible = unique if level == 1 else unique[:2]
        lines = visible if len(visible) == 1 else [f"• {text}" for text in visible]
        if len(unique) > len(visible):
            lines.append(self.localizer.text("notification.more_actions", count=len(unique) - len(visible)))
        return "\n".join(lines)

    def default_recommendation(self, context: dict[str, Any]) -> str:
        """Render missing-reading states without forwarding machine values."""
        check = context.get("failed_check")
        if isinstance(check, str) and check in {"availability", "freshness"}:
            return self.localizer.text("notification.inspect_input")
        value = context.get("observed_value")
        if isinstance(value, str) and value.lower() in {"unavailable", "unknown", "none"}:
            return self.localizer.text(f"notification.observation.{value.lower()}")
        return self.localizer.text("notification.open_details")
