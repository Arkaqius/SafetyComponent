"""Physical pump, loaded flow/return and per-room delivery supervision."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Mapping

from .engine import HeatingResult
from .inputs import HeatingObservation
from .schema import (
    HeatingDifferentialPolicy,
    HeatingPumpPolicy,
    HeatingRoomDeliveryPolicy,
    HeatingTrendPolicy,
)
from .windows import ObservedWindow, Sample

if TYPE_CHECKING:
    from .rules import HeatingRuleEngine


@dataclass
class TrendFrame:
    """A comparable physical interval; changing context discards its samples."""

    started: float
    target: float
    window: ObservedWindow = field(default_factory=ObservedWindow)


class DistributionRules:
    """Use physical path evidence without guessing a hydraulic topology."""

    def __init__(self, runtime: HeatingRuleEngine) -> None:
        self.runtime = runtime
        self.frames: dict[str, TrendFrame] = {}
        self.lost: set[str] = set()
        self.pump_started: dict[str, float] = {}

    def reset(self, key: str, *, lost: bool = False) -> None:
        """Invalidate current observations without resetting the durable need."""
        self.frames.pop(key, None)
        self.pump_started.pop(key, None)
        self.runtime._attained_since.pop(key, None)
        if lost:
            self.lost.add(key)

    def invalidate(self) -> None:
        """Rebuild physical windows after clock or scheduling discontinuity."""
        self.lost.update(self.frames)
        self.frames.clear()
        self.pump_started.clear()

    def evaluate(
        self,
        policy: HeatingPumpPolicy | HeatingTrendPolicy,
        inputs: Mapping[str, HeatingObservation],
        wall: float,
        mono: float,
        key: str,
        active: bool,
    ) -> HeatingResult:
        """Return a failure only for a physically eligible commissioned path."""
        values: dict[str, Any] = {role: item.value for role, item in inputs.items()}
        episode = self.runtime.episodes.get(key)
        room = isinstance(policy, HeatingRoomDeliveryPolicy)
        target = float(values["target_temperature"]) if room else 0.0
        temperature = float(values["room_temperature"]) if room else 0.0
        permitted = not room or values["heating_permitted"] is True
        ch = values["boiler_active"] is True and values["dhw_active"] is False
        if isinstance(policy, HeatingRoomDeliveryPolicy):
            needed = target - temperature > policy.need_on_margin_k
        elif isinstance(policy, HeatingPumpPolicy):
            needed = ch and values["pump_active"] is False
        else:
            assert isinstance(policy, HeatingDifferentialPolicy)
            delta = float(values["flow_temperature"]) - float(
                values["return_temperature"]
            )
            needed = (
                ch
                and values["pump_active"] is True
                and float(values[policy.load_role]) >= policy.minimum_load
                and float(values["flow_temperature"])
                >= policy.minimum_flow_temperature_c
                and (
                    delta > policy.failure_delta_k or delta < -policy.inverted_failure_k
                )
            )
        if episode is None and permitted and needed:
            if room:
                self.reset(key)
            episode = self.runtime._episode(
                key, target, [item.source_time for item in inputs.values()], wall
            )
        if episode is not None and room and target >= episode.reference_target:
            episode.reference_target = target
        age = max(item.maximum_age_seconds for item in inputs.values())
        urgent = episode is not None and self.runtime._urgent(
            episode,
            policy.maximum_unresolved_seconds,
            age,
            max(policy.failure_seconds, self.runtime.profile.failure_seconds),
        )

        def unknown(reason: str, *, lost: bool = False) -> HeatingResult:
            label = "distribution_window_incomplete" if urgent or lost else reason
            base = (
                self.runtime._result(
                    episode, policy.maximum_unresolved_seconds, None, label
                )
                if episode
                else HeatingResult(None, label)
            )
            return replace(base, quality_cause=label if urgent or lost else None)

        if isinstance(policy, HeatingPumpPolicy):
            if not ch:
                self.reset(key)
                return unknown("not_applicable")
            since = self.pump_started.setdefault(key, mono)
            if values["pump_active"] is True:
                self.runtime._attainment(
                    key, True, mono, policy.recovery_seconds, active
                )
                return HeatingResult(False, "pump_relationship_recovered")
            self.runtime._attained_since.pop(key, None)
            if mono - since < policy.startup_allowance_seconds:
                return unknown("starting_allowance")
            return HeatingResult(
                True,
                "pump_relationship_failed",
                window_evidence=(("startup_elapsed_seconds", mono - since),),
            )

        blocked = (
            values.get("inhibition_reason", "none") != "none"
            or room
            and values.get("room_inhibited", False) is True
        )
        if (
            not ch
            or values["pump_active"] is not True
            or not permitted
            or blocked
            or room
            and values["heat_delivery_active"] is not True
        ):
            self.reset(key)
            expired = False
            if episode is not None and (blocked or values["dhw_active"] is True):
                if episode.inhibition_started_elapsed is None:
                    episode.inhibition_started_elapsed = episode.elapsed_seconds
                expired = (
                    episode.elapsed_seconds - episode.inhibition_started_elapsed
                    >= policy.maximum_inhibition_seconds
                )
            return unknown(
                "bounded_inhibition"
                if blocked or values["dhw_active"] is True
                else "not_applicable",
                lost=expired,
            )
        if episode is not None:
            episode.inhibition_started_elapsed = None
        if (
            room
            and episode is not None
            and isinstance(policy, HeatingRoomDeliveryPolicy)
            and target < episode.reference_target - policy.target_stability_tolerance_k
        ):
            self.reset(key)
            return unknown("target_changed")
        if isinstance(policy, HeatingDifferentialPolicy) and (
            float(values[policy.load_role]) < policy.minimum_load
            or float(values["flow_temperature"]) < policy.minimum_flow_temperature_c
        ):
            self.reset(key)
            return unknown("insufficient_load")
        reference = episode.reference_target if episode is not None else target
        frame = self.frames.get(key)
        if (
            frame is None
            or isinstance(policy, HeatingRoomDeliveryPolicy)
            and abs(frame.target - reference) > policy.target_stability_tolerance_k
        ):
            frame = TrendFrame(mono, reference)
            frame.window.lost = key in self.lost
            self.frames[key] = frame
        if mono - frame.started < policy.startup_allowance_seconds:
            return unknown("starting_allowance", lost=key in self.lost)
        roles = (
            ("room_temperature",)
            if room
            else ("flow_temperature", "return_temperature")
        )
        sample = Sample(
            tuple(inputs[role].source_time for role in roles),
            mono,
            tuple(float(values[role]) for role in roles),
        )
        coverage = frame.window.add(
            sample,
            policy.observation_window_seconds,
            policy.maximum_sample_gap_seconds,
            policy.minimum_sample_count,
        )
        if coverage:
            if coverage in {"lost", "invalid"}:
                self.lost.add(key)
            return unknown("collecting_samples", lost=key in self.lost)
        self.lost.discard(key)
        first, last = frame.window.samples[0], frame.window.samples[-1]
        evidence: tuple[tuple[str, float | int], ...]
        if isinstance(policy, HeatingDifferentialPolicy):
            deltas = [item.values[0] - item.values[1] for item in frame.window.samples]
            if all(delta > policy.failure_delta_k for delta in deltas):
                violation, reason = True, "distribution_excess_delta"
            elif all(delta < -policy.inverted_failure_k for delta in deltas):
                violation, reason = True, "distribution_inverted_delta"
            elif -policy.inverted_recovery_k <= deltas[-1] <= policy.recovery_delta_k:
                violation, reason = False, "distribution_recovered"
            else:
                violation, reason = None, "output_hysteresis"
            evidence = (
                ("latest_delta_k", deltas[-1]),
                ("minimum_delta_k", min(deltas)),
                ("maximum_delta_k", max(deltas)),
                ("failure_delta_k", policy.failure_delta_k),
                ("recovery_delta_k", policy.recovery_delta_k),
                ("inverted_failure_k", policy.inverted_failure_k),
                ("inverted_recovery_k", policy.inverted_recovery_k),
            )
        else:
            assert isinstance(policy, HeatingRoomDeliveryPolicy)
            change = last.values[0] - first.values[0]
            attained = temperature >= reference - policy.need_off_margin_k
            if attained or change >= policy.recovery_rise_k:
                violation, reason = False, "room_delivery_recovered"
            elif episode is not None and change <= -policy.minimum_cooling_k:
                violation, reason = True, "room_delivery_cooling"
            else:
                violation, reason = None, "output_hysteresis"
            evidence = (
                ("room_change_k", change),
                ("reference_target", reference),
                ("minimum_cooling_k", policy.minimum_cooling_k),
                ("recovery_rise_k", policy.recovery_rise_k),
            )
        duration = frame.window.qualify(violation, reason)
        if (
            violation is False
            and not active
            and duration is not None
            and duration >= policy.recovery_seconds
            and (
                not isinstance(policy, HeatingRoomDeliveryPolicy)
                or temperature >= reference - policy.need_off_margin_k
            )
        ):
            self.runtime.episodes.pop(key, None)
        return HeatingResult(
            violation,
            reason,
            observed_qualification_seconds=duration,
            onset_utc=episode.onset_utc if episode else None,
            reference_target=reference if room else None,
            remaining_seconds=max(
                0, policy.maximum_unresolved_seconds - episode.elapsed_seconds
            )
            if episode
            else None,
            window_evidence=frame.window.summary()
            + evidence
            + (
                ("failure_seconds", policy.failure_seconds),
                ("recovery_seconds", policy.recovery_seconds),
            ),
        )
