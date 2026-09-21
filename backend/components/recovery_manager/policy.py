"""Narrow policy boundary for validating proposed recovery results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from components.core.types_common import RecoveryResult


@dataclass(frozen=True)
class RecoveryPolicyDecision:
    """Decision returned by one registered recovery policy evaluator."""

    allowed: bool
    reason: str | None = None


class RecoveryPolicyEvaluator(Protocol):
    """Evaluate a proposed recovery action without executing it."""

    def evaluate_recovery_policy(
        self, recovery_result: RecoveryResult
    ) -> RecoveryPolicyDecision: ...
