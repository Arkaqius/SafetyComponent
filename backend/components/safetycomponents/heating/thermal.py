"""Independent absolute and phase-specific physical temperature protection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from .engine import HeatingResult, observed_phase
from .inputs import HeatingObservation
from .schema import HeatingAbsoluteTemperaturePolicy, HeatingModeTemperaturePolicy

if TYPE_CHECKING:
    from .rules import HeatingRuleEngine


class ThermalRules:
    """Keep the original stricter clear reference across phase changes/restart."""

    def __init__(self, runtime: HeatingRuleEngine) -> None:
        self.runtime = runtime

    def evaluate(
        self,
        policy: HeatingModeTemperaturePolicy | HeatingAbsoluteTemperaturePolicy,
        inputs: Mapping[str, HeatingObservation],
        wall: float,
        key: str,
    ) -> HeatingResult:
        """Positive valid heat evidence remains actionable during diagnostic loss."""
        flow = inputs["flow_temperature"]
        temperature = flow.number
        if isinstance(policy, HeatingModeTemperaturePolicy):
            phase = observed_phase(inputs)
            envelope = next(
                (item for name, item in policy.envelopes.items() if name == phase), None
            )
            if envelope is None:
                return HeatingResult(
                    None, "thermal_mode_unknown", quality_cause="thermal_mode_unknown"
                )
            failure, recovery = envelope.failure_c, envelope.recovery_c
        else:
            failure = policy.absolute_limit_c - policy.measurement_tolerance_k
            recovery = failure - policy.recovery_margin_k
        episode = self.runtime.episodes.get(key)
        if temperature >= failure:
            if episode is None:
                episode = self.runtime._episode(key, recovery, [flow.source_time], wall)
            else:
                episode.reference_target = min(episode.reference_target, recovery)
            violation, reason = True, "thermal_limit_exceeded"
        elif self.runtime.clock_uncertain:
            return HeatingResult(
                None, "clock_uncertain", quality_cause="clock_uncertain"
            )
        elif temperature <= min(
            recovery, episode.reference_target if episode else recovery
        ):
            violation, reason = False, "thermal_recovered"
        else:
            violation, reason = None, "thermal_recovery_wait"
        return HeatingResult(
            violation,
            reason,
            reference_target=episode.reference_target if episode else recovery,
            window_evidence=(
                ("temperature_c", temperature),
                ("failure_threshold_c", failure),
                ("current_recovery_threshold_c", recovery),
                (
                    "original_recovery_threshold_c",
                    episode.reference_target if episode else recovery,
                ),
                ("failure_seconds", policy.failure_seconds),
                ("recovery_seconds", policy.recovery_seconds),
                (
                    "equipment_response_seconds",
                    policy.allocation.maximum_response_seconds,
                ),
                (
                    "detection_budget_seconds",
                    policy.allocation.detection_budget_seconds,
                ),
            ),
        )
