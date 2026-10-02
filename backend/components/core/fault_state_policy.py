"""Fault-owned evaluation state and priority policy.

Predicates return only ``bool``. Missing evidence and invocation failures use
``mark_unavailable``; they must never be passed as a fabricated ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Callable


class FaultCategory(str, Enum):
    """Hazard/equipment condition or diagnostic coverage failure."""

    H = "H"
    D = "D"


class FaultEvaluationStatus(str, Enum):
    """Evaluation status, independent of active condition and shadowing."""

    NOT_EVALUATED = "NOT_EVALUATED"
    PASS = "PASS"
    PENDING_FAILURE = "PENDING_FAILURE"
    FAIL = "FAIL"
    PENDING_RECOVERY = "PENDING_RECOVERY"
    UNEVALUABLE = "UNEVALUABLE"
    INHIBITED = "INHIBITED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class PriorityProfile:
    """Defaults selected by the existing fault/notification level."""

    level: int
    mobile: bool
    submission_deadline_seconds: int | None
    repeat_on_activation: bool
    latch_required: bool
    operator_control_default: bool


PRIORITY_PROFILES: dict[int, PriorityProfile] = {
    1: PriorityProfile(1, True, 10, True, True, False),
    2: PriorityProfile(2, True, 30, False, False, False),
    3: PriorityProfile(3, True, 30, False, False, False),
    4: PriorityProfile(4, False, None, False, False, False),
}


@dataclass
class FaultEvaluation:
    """Aggregate Boolean contributions with fault-owned timing and eligibility.

    The current configured combination rule is OR: one valid violation is
    actionable even when another contributor is unavailable. Recovery requires
    valid negative evidence from *every* bound contributor.
    """

    contributors: set[str] = field(default_factory=set)
    failure_delay_seconds: float = 0.0
    recovery_delay_seconds: float = 0.0
    clock: Callable[[], float] = monotonic
    status: FaultEvaluationStatus = FaultEvaluationStatus.NOT_EVALUATED
    active: bool = False
    active_contributors: set[str] = field(default_factory=set)
    shadowed_by: set[str] = field(default_factory=set)
    latched: bool = False
    inhibited: bool = False
    disabled: bool = False
    _results: dict[str, bool | None] = field(default_factory=dict)
    _pending_since: float | None = None
    _pending_kind: str | None = None

    def __post_init__(self) -> None:
        if self.failure_delay_seconds < 0 or self.recovery_delay_seconds < 0:
            raise ValueError("Fault qualification delays must be nonnegative")
        for contributor in self.contributors:
            self._results.setdefault(contributor, None)

    def bind(self, contributor: str) -> None:
        """Declare an expected contributor without pretending it was evaluated."""

        self.contributors.add(contributor)
        self._results.setdefault(contributor, None)

    def observe(self, contributor: str, violation: bool) -> FaultEvaluationStatus:
        """Accept a valid Boolean predicate result and recompute status."""

        if not isinstance(violation, bool):
            raise TypeError("Safety mechanism result must be bool")
        self.bind(contributor)
        self._results[contributor] = violation
        return self._advance()

    def mark_unavailable(self, contributor: str) -> FaultEvaluationStatus:
        """Invalidate evidence without manufacturing recovery."""

        self.bind(contributor)
        self._results[contributor] = None
        return self._advance()

    def set_control(
        self, *, inhibited: bool = False, disabled: bool = False
    ) -> FaultEvaluationStatus:
        """Reflect validated control policy without erasing prior evidence.

        This is a state primitive, not an operator-control API or permission gate.
        """

        self.inhibited = inhibited
        self.disabled = disabled
        return self._advance()

    def _advance(self) -> FaultEvaluationStatus:
        if self.disabled:
            self._reset_pending()
            self.status = FaultEvaluationStatus.DISABLED
            return self.status
        if self.inhibited:
            self._reset_pending()
            self.status = FaultEvaluationStatus.INHIBITED
            return self.status
        values = tuple(self._results.values())
        violations = {name for name, value in self._results.items() if value is True}
        if violations:
            if not self.active and not self._qualified(
                "failure", self.failure_delay_seconds
            ):
                self.status = FaultEvaluationStatus.PENDING_FAILURE
                return self.status
            self.active = True
            if all(value is not None for value in values):
                self.active_contributors = violations
            else:
                self.active_contributors.update(violations)
            self._reset_pending()
            self.status = FaultEvaluationStatus.FAIL
        elif not values:
            self._reset_pending()
            self.status = FaultEvaluationStatus.NOT_EVALUATED
        elif any(value is None for value in values):
            self._reset_pending()
            self.status = FaultEvaluationStatus.UNEVALUABLE
        elif self.active and not self._qualified("recovery", self.recovery_delay_seconds):
            self.status = FaultEvaluationStatus.PENDING_RECOVERY
        else:
            self.active = False
            self.active_contributors.clear()
            self._reset_pending()
            self.status = FaultEvaluationStatus.PASS
        return self.status

    def _qualified(self, kind: str, delay: float) -> bool:
        if delay == 0:
            return True
        now = self.clock()
        if self._pending_kind != kind:
            self._pending_kind = kind
            self._pending_since = now
        return self._pending_since is not None and now - self._pending_since >= delay

    def _reset_pending(self) -> None:
        self._pending_kind = None
        self._pending_since = None
