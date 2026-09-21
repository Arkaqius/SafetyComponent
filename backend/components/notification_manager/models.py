"""Runtime value objects for notification delivery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DeliveryDisposition(str, Enum):
    """Result of submitting one payload to one Home Assistant service."""

    ACCEPTED = "accepted_by_home_assistant"
    FAILED = "failed"
    QUEUED = "queued"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class TargetDeliveryResult:
    """One target service submission result."""

    service: str
    disposition: DeliveryDisposition
    error: str | None = None


@dataclass(frozen=True)
class DeliveryBatchResult:
    """Aggregate result for an explicit list of targets."""

    targets: tuple[TargetDeliveryResult, ...]

    @property
    def accepted(self) -> bool:
        """Return true only when every configured target accepted the call."""

        return bool(self.targets) and all(
            target.disposition == DeliveryDisposition.ACCEPTED
            for target in self.targets
        )

    @property
    def completed(self) -> bool:
        """Return true when no configured target requires retry."""

        return bool(self.targets) and all(
            target.disposition == DeliveryDisposition.ACCEPTED
            for target in self.targets
        )

    @property
    def error(self) -> str | None:
        """Summarize failed targets without claiming device delivery status."""

        failures = [
            f"{target.service}: {target.error or target.disposition.value}"
            for target in self.targets
            if target.disposition != DeliveryDisposition.ACCEPTED
        ]
        return "; ".join(failures) if failures else None

    @property
    def failed_services(self) -> tuple[str, ...]:
        """Return only targets that still require retry."""

        return tuple(
            target.service
            for target in self.targets
            if target.disposition != DeliveryDisposition.ACCEPTED
        )


@dataclass
class PendingDelivery:
    """Persistable delivery scheduled for retry."""

    delivery_id: str
    tag: str
    level: int
    title: str
    message: str
    kind: str
    created_at: float
    deadline_at: float
    next_attempt_at: float
    attempts: int = 0
    target_services: tuple[str, ...] = ()
    deadline_missed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""

        return vars(self).copy()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PendingDelivery":
        """Restore a validated shape from JSON primitives."""

        return cls(
            delivery_id=str(value["delivery_id"]),
            tag=str(value["tag"]),
            level=int(value["level"]),
            title=str(value["title"]),
            message=str(value["message"]),
            kind=str(value["kind"]),
            created_at=float(value["created_at"]),
            deadline_at=float(value["deadline_at"]),
            next_attempt_at=float(value["next_attempt_at"]),
            attempts=int(value.get("attempts", 0)),
            target_services=tuple(
                str(item) for item in value.get("target_services", ())
            ),
            deadline_missed=bool(value.get("deadline_missed", False)),
        )
