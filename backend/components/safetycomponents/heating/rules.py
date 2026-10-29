"""Qualified generic status and need/response rules with durable elapsed budgets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Mapping

from .engine import HeatingResult
from .inputs import HeatingObservation
from .output import OutputWindows
from .schema import (
    HeatingDemandPolicy,
    HeatingProfile,
    HeatingResponsePolicy,
    HeatingOutputPolicy,
    HeatingRisePolicy,
    HeatingTrackingPolicy,
    RULE_INPUTS,
)


@dataclass
class NeedEpisode:
    """One unresolved need; target changes and restarts cannot renew its budget."""

    onset_utc: float
    elapsed_seconds: float
    reference_target: float
    inhibition_started_elapsed: float | None = None


class HeatingRuleEngine:
    """Use monotonic runtime and reconciled UTC downtime, never controller internals."""

    def __init__(self, profile: HeatingProfile, interval: int, drift: int) -> None:
        self.profile = profile
        self.interval = interval
        self.drift = drift
        self.episodes: dict[str, NeedEpisode] = {}
        self._attained_since: dict[str, float] = {}
        self._wall: float | None = None
        self._mono: float | None = None
        self._clock_uncertain = False
        self._stable_since: float | None = None
        self.output = OutputWindows()

    @property
    def clock_uncertain(self) -> bool:
        """Report clock uncertainty independently of mechanical heating faults."""
        return self._clock_uncertain

    def advance(self, wall: float, mono: float) -> None:
        """Account downtime once and detect runtime wall/monotonic divergence."""
        if self._mono is None:
            elapsed = max(0.0, wall - self._wall) if self._wall is not None else 0.0
            jumped = self._wall is not None and wall < self._wall
        else:
            elapsed = max(0.0, mono - self._mono)
            jumped = (
                mono < self._mono
                or abs((wall - float(self._wall)) - elapsed) > self.drift
            )
        for episode in self.episodes.values():
            episode.elapsed_seconds = min(1800.0, episode.elapsed_seconds + elapsed)
        if elapsed > self.interval * 2:
            self._attained_since.clear()
            self.output.invalidate()
        if jumped:
            self._clock_uncertain = True
            self._stable_since = mono
            self._attained_since.clear()
            self.output.invalidate()
        elif self._clock_uncertain:
            if self._stable_since is None:
                self._stable_since = mono
            elif mono - self._stable_since >= self.profile.recovery_seconds:
                self._clock_uncertain = False
                self._stable_since = None
        self._wall, self._mono = wall, mono

    def evaluate(
        self,
        rule: str,
        inputs: Mapping[str, HeatingObservation],
        wall: float,
        mono: float,
        *,
        key: str,
        active: bool,
    ) -> HeatingResult:
        """Return a qualified predicate or explicit ineligibility without HEAL."""
        policy = self.profile.rule_policy(rule)
        if policy is None:
            return HeatingResult(None, "excluded")
        if self.clock_uncertain:
            return HeatingResult(
                None, "clock_uncertain", quality_cause="clock_uncertain"
            )
        required = set(RULE_INPUTS[rule])
        if (
            isinstance(policy, (HeatingResponsePolicy, HeatingOutputPolicy))
            and policy.inhibition_context == "mapped_reason"
        ):
            required.add("inhibition_reason")
        if required - inputs.keys():
            return HeatingResult(None, "missing_input", quality_cause="missing_input")
        if any(not inputs[role].qualified for role in required):
            self._attained_since.pop(key, None)
            if rule in {"R05", "R06"}:
                self.output.reset(key, lost=True)
            return HeatingResult(None, "unqualified_input")
        observed = [float(inputs[role].observed_at) for role in required]  # type: ignore[arg-type]
        skew = getattr(policy, "maximum_input_skew_seconds", None)
        if skew is not None and max(observed) - min(observed) > skew:
            self._attained_since.pop(key, None)
            if rule in {"R05", "R06"}:
                self.output.reset(key, lost=True)
            return HeatingResult(None, "input_skew", quality_cause="input_skew")
        values = {role: inputs[role].value for role in required}
        inputs = {role: inputs[role] for role in required}
        if rule in {"R02", "R13"}:
            role, failed = (
                ("device_status", "fault")
                if rule == "R02"
                else ("maintenance_status", "maintenance")
            )
            if values[role] not in {"clear", failed}:
                return HeatingResult(None, "unknown_code", quality_cause="unknown_code")
            return HeatingResult(values[role] == failed, "observed")
        if isinstance(policy, HeatingDemandPolicy):
            return self._demand(
                values, inputs, observed, policy, wall, mono, key, active
            )
        if isinstance(policy, HeatingOutputPolicy):
            return self._performance(
                values, inputs, observed, policy, wall, mono, key, active
            )
        assert isinstance(policy, HeatingResponsePolicy)
        return self._response(values, inputs, observed, policy, wall, mono, key, active)

    def _episode(
        self, key: str, target: float, observed: list[float], wall: float
    ) -> NeedEpisode:
        episode = self.episodes.get(key)
        if episode is None:
            onset = max(observed)
            episode = NeedEpisode(onset, min(1800.0, max(0.0, wall - onset)), target)
            self.episodes[key] = episode
        episode.reference_target = max(episode.reference_target, target)
        return episode

    def _result(
        self,
        episode: NeedEpisode,
        budget: int,
        violation: bool | None,
        reason: str,
        *,
        urgent: bool = False,
    ) -> HeatingResult:
        return HeatingResult(
            violation,
            reason,
            urgent=urgent,
            onset_utc=episode.onset_utc,
            elapsed_seconds=episode.elapsed_seconds,
            reference_target=episode.reference_target,
            remaining_seconds=max(0.0, budget - episode.elapsed_seconds),
        )

    def _attainment(
        self, key: str, attained: bool, mono: float, seconds: int, active: bool
    ) -> None:
        if not attained:
            self._attained_since.pop(key, None)
            return
        since = self._attained_since.setdefault(key, mono)
        if mono - since >= seconds and not active:
            self.episodes.pop(key, None)
            self._attained_since.pop(key, None)

    def _urgent(
        self, episode: NeedEpisode, budget: int, age: float, failure_seconds: int
    ) -> bool:
        # Keep one cadence, decision and transport reserve after first detection.
        return (
            episode.elapsed_seconds
            >= budget - age - self.interval - 1 - 30 - failure_seconds
        )

    def _demand(
        self,
        values: dict[str, Any],
        inputs: Mapping[str, HeatingObservation],
        observed: list[float],
        policy: HeatingDemandPolicy,
        wall: float,
        mono: float,
        key: str,
        active: bool,
    ) -> HeatingResult:
        if any(
            inputs[role].independence_group == inputs["heat_request"].independence_group
            for role in ("room_temperature", "target_temperature", "heating_permitted")
        ):
            return HeatingResult(None, "dependent_need", quality_cause="dependent_need")
        if values["heating_permitted"] is not True:
            self._attained_since.pop(key, None)
            return HeatingResult(None, "not_applicable")
        target, temperature = (
            float(values["target_temperature"]),
            float(values["room_temperature"]),
        )
        episode = self.episodes.get(key)
        if episode is None and target - temperature <= policy.need_on_margin_k:
            return HeatingResult(
                False if not active else None,
                "not_applicable" if active else "observed",
            )
        episode = self._episode(key, target, observed, wall)
        attained = temperature >= episode.reference_target - policy.need_off_margin_k
        comparable_target = target >= episode.reference_target
        self._attainment(
            key, attained and comparable_target, mono, policy.recovery_seconds, active
        )
        if attained and comparable_target:
            return self._result(
                episode, policy.maximum_unresolved_seconds, False, "target_attained"
            )
        if not comparable_target:
            return self._result(
                episode, policy.maximum_unresolved_seconds, None, "target_changed"
            )
        if values["heat_request"] is True:
            return self._result(
                episode, policy.maximum_unresolved_seconds, False, "request_observed"
            )
        age = max(item.maximum_age_seconds for item in inputs.values())
        urgent = self._urgent(
            episode, policy.maximum_unresolved_seconds, age, policy.failure_seconds
        )
        if episode.elapsed_seconds < policy.request_allowance_seconds and not urgent:
            return self._result(
                episode, policy.maximum_unresolved_seconds, None, "request_allowance"
            )
        return self._result(
            episode,
            policy.maximum_unresolved_seconds,
            True,
            "missing_request",
            urgent=urgent,
        )

    def _response(
        self,
        values: dict[str, Any],
        inputs: Mapping[str, HeatingObservation],
        observed: list[float],
        policy: HeatingResponsePolicy,
        wall: float,
        mono: float,
        key: str,
        active: bool,
    ) -> HeatingResult:
        target, actual = (
            float(values["requested_flow_temperature"]),
            float(values["flow_temperature"]),
        )
        episode = self.episodes.get(key)
        if values["heat_request"] is not True:
            self._attained_since.pop(key, None)
            return HeatingResult(None, "not_applicable")
        reason = str(values.get("inhibition_reason", "none"))
        blocked = values["dhw_active"] is True or reason in {"startup", "anti_cycle"}
        if (
            episode is None
            and not blocked
            and actual >= target - policy.target_recovery_margin_k
        ):
            return HeatingResult(
                False if not active else None,
                "target_attained" if not active else "not_applicable",
            )
        episode = self._episode(key, target, observed, wall)
        if target < episode.reference_target:
            self._attained_since.pop(key, None)
            return self._result(
                episode, policy.maximum_unresolved_seconds, None, "target_changed"
            )
        if not blocked:
            episode.inhibition_started_elapsed = None
            attained = (
                actual >= episode.reference_target - policy.target_recovery_margin_k
            )
            self._attainment(key, attained, mono, policy.recovery_seconds, active)
            if values["boiler_active"] is True or attained:
                return self._result(
                    episode,
                    policy.maximum_unresolved_seconds,
                    False,
                    "target_attained" if attained else "response_observed",
                )
        else:
            self._attained_since.pop(key, None)
            if episode.inhibition_started_elapsed is None:
                episode.inhibition_started_elapsed = episode.elapsed_seconds
        urgent = self._urgent(
            episode,
            policy.maximum_unresolved_seconds,
            max(item.maximum_age_seconds for item in inputs.values()),
            policy.failure_seconds,
        )
        if blocked:
            inhibited_for = episode.elapsed_seconds - float(
                episode.inhibition_started_elapsed
            )
            if inhibited_for < policy.maximum_inhibition_seconds and not urgent:
                return self._result(
                    episode,
                    policy.maximum_unresolved_seconds,
                    None,
                    "bounded_inhibition",
                )
            return self._result(
                episode,
                policy.maximum_unresolved_seconds,
                True,
                "inhibition_budget_exhausted",
                urgent=urgent,
            )
        if episode.elapsed_seconds < policy.startup_allowance_seconds and not urgent:
            return self._result(
                episode, policy.maximum_unresolved_seconds, None, "starting_allowance"
            )
        return self._result(
            episode,
            policy.maximum_unresolved_seconds,
            True,
            "no_response",
            urgent=urgent,
        )

    def _performance(
        self,
        values: dict[str, Any],
        inputs: Mapping[str, HeatingObservation],
        observed: list[float],
        policy: HeatingOutputPolicy,
        wall: float,
        mono: float,
        key: str,
        active: bool,
    ) -> HeatingResult:
        target, actual = (
            float(values["requested_flow_temperature"]),
            float(values["flow_temperature"]),
        )
        episode = self.episodes.get(key)
        recovery_margin = (
            policy.target_recovery_margin_k
            if isinstance(policy, HeatingRisePolicy)
            else policy.recovery_deficit_k
            if isinstance(policy, HeatingTrackingPolicy)
            else 0.0
        )
        age = max(item.maximum_age_seconds for item in inputs.values())

        def ineligible(reason: str, *, expired: bool = False) -> HeatingResult:
            deadline = episode is not None and self._urgent(
                episode,
                policy.maximum_unresolved_seconds,
                age,
                max(policy.failure_seconds, self.profile.failure_seconds),
            )
            lost = expired or deadline
            label = "output_window_incomplete" if lost else reason
            result = (
                self._result(episode, policy.maximum_unresolved_seconds, None, label)
                if episode is not None
                else HeatingResult(None, label)
            )
            return replace(
                result, quality_cause="output_window_incomplete" if lost else None
            )

        if values["heat_request"] is not True:
            self.output.reset(key)
            return ineligible("not_applicable")
        if (
            episode is not None
            and target < episode.reference_target - policy.target_stability_tolerance_k
        ):
            self.output.reset(key)
            return ineligible("target_changed")
        if target - actual > recovery_margin or episode is not None or active:
            if episode is None:
                self.output.reset(key)
            episode = self._episode(key, target, observed, wall)
        reference = episode.reference_target if episode is not None else target
        urgent = episode is not None and self._urgent(
            episode,
            policy.maximum_unresolved_seconds,
            age,
            max(policy.failure_seconds, self.profile.failure_seconds),
        )
        blocked = (
            values["dhw_active"] is True
            or values.get("inhibition_reason", "none") != "none"
        )
        if blocked or values["boiler_active"] is not True:
            self.output.reset(key)
            expired = urgent
            if episode is not None and blocked:
                if episode.inhibition_started_elapsed is None:
                    episode.inhibition_started_elapsed = episode.elapsed_seconds
                expired = (
                    expired
                    or episode.elapsed_seconds - episode.inhibition_started_elapsed
                    >= policy.maximum_inhibition_seconds
                )
            return ineligible(
                "bounded_inhibition" if blocked else "not_applicable", expired=expired
            )
        if episode is not None:
            episode.inhibition_started_elapsed = None
        if (
            isinstance(policy, HeatingRisePolicy)
            and reference - actual < policy.minimum_target_deficit_k
            and reference - actual > recovery_margin
            and key not in self.output.windows
        ):
            return ineligible("not_applicable")
        result = self.output.observe(
            key, policy, inputs["flow_temperature"], reference, mono, urgent=urgent
        )
        if episode is not None:
            result = replace(
                result,
                onset_utc=episode.onset_utc,
                elapsed_seconds=episode.elapsed_seconds,
                remaining_seconds=max(
                    0.0, policy.maximum_unresolved_seconds - episode.elapsed_seconds
                ),
                reference_target=episode.reference_target,
            )
            if (
                not active
                and result.violation is False
                and (result.observed_qualification_seconds or 0)
                >= policy.recovery_seconds
                and reference - actual <= recovery_margin
            ):
                self.episodes.pop(key, None)
        return result

    def snapshot(self) -> dict[str, Any]:
        """Persist only bounded budget facts; no downtime becomes recovery samples."""
        return {
            "saved_at": self._wall if self.episodes or self._clock_uncertain else None,
            "clock_uncertain": self._clock_uncertain,
            "episodes": {key: asdict(value) for key, value in self.episodes.items()},
        }

    def restore(self, snapshot: Any, allowed_keys: set[str]) -> None:
        """Reject malformed or orphaned budgets instead of resetting deadlines."""
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "saved_at",
            "clock_uncertain",
            "episodes",
        }:
            raise ValueError("invalid heating budget state")
        saved_at = snapshot["saved_at"]
        if saved_at is not None and (
            isinstance(saved_at, bool)
            or not isinstance(saved_at, (float, int))
            or not math.isfinite(saved_at)
            or saved_at < 0
        ):
            raise ValueError("invalid heating budget clock")
        if not isinstance(snapshot["clock_uncertain"], bool) or not isinstance(
            snapshot["episodes"], dict
        ):
            raise ValueError("invalid heating budget registry")
        if set(snapshot["episodes"]) - allowed_keys:
            raise ValueError("unresolved heating budget was removed")
        restored = {}
        for key, values in snapshot["episodes"].items():
            if not isinstance(values, dict) or set(values) != {
                "onset_utc",
                "elapsed_seconds",
                "reference_target",
                "inhibition_started_elapsed",
            }:
                raise ValueError("invalid heating episode")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                for name, value in values.items()
                if name != "inhibition_started_elapsed"
            ):
                raise ValueError("nonfinite heating episode")
            onset, elapsed, target = (
                values["onset_utc"],
                values["elapsed_seconds"],
                values["reference_target"],
            )
            inhibited = values["inhibition_started_elapsed"]
            if (
                not 0 <= elapsed <= 1800
                or not -273.15 < target < 1000
                or onset < 0
                or saved_at is None
                or onset > saved_at + self.drift
            ):
                raise ValueError("heating episode outside bounds")
            if inhibited is not None and (
                isinstance(inhibited, bool)
                or not isinstance(inhibited, (float, int))
                or not math.isfinite(inhibited)
                or not 0 <= inhibited <= elapsed
            ):
                raise ValueError("invalid heating inhibition onset")
            restored[key] = NeedEpisode(**values)
        self.episodes = restored
        # Restart loses observation windows; unresolved paths must prove covered
        # observations again before their quality supervision can recover.
        self.output.lost.update(restored)
        self._wall, self._mono = saved_at, None
        self._clock_uncertain = snapshot["clock_uncertain"]
