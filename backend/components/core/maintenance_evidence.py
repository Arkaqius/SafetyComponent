"""Qualification rules for fresh host resources and successful backup evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any


class ResourceRule:
    """Require uninterrupted bad/recovery evidence, retaining faults on unknown."""

    def __init__(self, threshold: float, recovery: float, qualification: float, recovery_seconds: float, *, low: bool) -> None:
        self.threshold = threshold
        self.recovery = recovery
        self.qualification = qualification
        self.recovery_seconds = recovery_seconds
        self.low = low
        self.active = False
        self.bad_since: float | None = None
        self.good_since: float | None = None

    def observe(self, value: float | None) -> str:
        """Return observation status without converting unavailable into clear."""
        if value is None:
            self.bad_since = self.good_since = None
            return "unknown"
        now = monotonic()
        bad = value <= self.threshold if self.low else value >= self.threshold
        recovered = value >= self.recovery if self.low else value <= self.recovery
        if not self.active:
            if bad:
                if self.bad_since is None:
                    self.bad_since = now
                if now - self.bad_since >= self.qualification:
                    self.active = True
            else:
                self.bad_since = None
        elif recovered:
            if self.good_since is None:
                self.good_since = now
            if now - self.good_since >= self.recovery_seconds:
                self.active = False
                self.bad_since = self.good_since = None
        else:
            self.good_since = None
        return ("low" if self.low else "high") if self.active else "qualifying" if self.bad_since is not None else "normal"


def aware_time(value: Any) -> datetime | None:
    """Reject malformed, timezone-free and future attestations."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
            return None
        return parsed
    except (ValueError, TypeError, OverflowError):
        return None
