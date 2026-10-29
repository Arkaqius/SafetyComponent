"""Bounded CH output windows qualified by distinct original observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .engine import HeatingResult
from .inputs import HeatingObservation
from .schema import HeatingOutputPolicy, HeatingRisePolicy, HeatingTrackingPolicy


@dataclass(frozen=True)
class FlowSample:
    """One original physical flow observation and its first runtime receipt."""

    at: float
    seen: float
    temperature: float


@dataclass
class FlowWindow:
    """Ephemeral measurement and qualification state; never restored as samples."""

    target: float
    started: float
    samples: list[FlowSample] = field(default_factory=list)
    pending: bool | None = None
    pending_at: float | None = None
    pending_seen: float | None = None


class OutputWindows:
    """Keep source sample coverage separate from durable unresolved-need time."""

    def __init__(self) -> None:
        self.windows: dict[str, FlowWindow] = {}
        self.lost: set[str] = set()

    def reset(self, key: str, *, lost: bool = False) -> None:
        """Discard invalid samples without clearing the owning active condition."""
        self.windows.pop(key, None)
        if lost:
            self.lost.add(key)

    def invalidate(self) -> None:
        """Cancel every live window after a clock or scheduling discontinuity."""
        self.lost.update(self.windows)
        self.windows.clear()

    def observe(
        self,
        key: str,
        policy: HeatingOutputPolicy,
        flow: HeatingObservation,
        target: float,
        mono: float,
        *,
        urgent: bool,
    ) -> HeatingResult:
        """Require covered source/runtime spans, then accrue distinct-sample time."""
        window = self.windows.get(key)
        if window is None or (
            abs(target - window.target) > policy.target_stability_tolerance_k
            and not math.isclose(
                abs(target - window.target),
                policy.target_stability_tolerance_k,
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            window = FlowWindow(target, mono)
            self.windows[key] = window
        if mono - window.started < policy.startup_allowance_seconds:
            lost = urgent or key in self.lost
            return HeatingResult(
                None,
                "output_window_incomplete" if lost else "starting_allowance",
                quality_cause="output_window_incomplete" if lost else None,
            )
        assert flow.observed_at is not None
        sample = FlowSample(flow.observed_at, mono, float(flow.value))
        if window.samples:
            last = window.samples[-1]
            if (
                sample.at < last.at
                or sample.at == last.at
                and sample.temperature != last.temperature
            ):
                self.reset(key, lost=True)
                return HeatingResult(
                    None, "output_sample_invalid", quality_cause="output_sample_invalid"
                )
            if (
                sample.at - last.at > policy.maximum_sample_gap_seconds
                or mono - last.seen > policy.maximum_sample_gap_seconds
            ):
                window.samples.clear()
                window.pending = window.pending_at = window.pending_seen = None
                self.lost.add(key)
        if not window.samples or sample.at > window.samples[-1].at:
            window.samples.append(sample)
        last = window.samples[-1]
        while len(window.samples) > 2:
            candidate = window.samples[1]
            if (
                last.at - candidate.at < policy.observation_window_seconds
                or last.seen - candidate.seen < policy.observation_window_seconds
            ):
                break
            window.samples.pop(0)
        if len(window.samples) > 4096:
            self.reset(key, lost=True)
            return HeatingResult(
                None,
                "output_window_incomplete",
                quality_cause="output_window_incomplete",
            )
        first = window.samples[0]
        if (
            len(window.samples) < policy.minimum_sample_count
            or last.at - first.at < policy.observation_window_seconds
            or last.seen - first.seen < policy.observation_window_seconds
        ):
            return HeatingResult(
                None,
                "output_window_incomplete"
                if key in self.lost or urgent
                else "collecting_samples",
                quality_cause="output_window_incomplete"
                if key in self.lost or urgent
                else None,
            )
        self.lost.discard(key)
        deficit = target - last.temperature
        if isinstance(policy, HeatingRisePolicy):
            rise = last.temperature - first.temperature
            if deficit <= policy.target_recovery_margin_k:
                violation, reason = False, "target_attained"
            elif rise >= policy.recovery_rise_k:
                violation, reason = False, "flow_rise_recovered"
            elif (
                deficit >= policy.minimum_target_deficit_k
                and rise < policy.minimum_rise_k
            ):
                violation, reason = True, "flow_rise_insufficient"
            else:
                violation, reason = None, "output_hysteresis"
        else:
            assert isinstance(policy, HeatingTrackingPolicy)
            if deficit <= policy.recovery_deficit_k:
                violation, reason = False, "flow_tracking_recovered"
            elif all(
                target - item.temperature > policy.failure_deficit_k
                for item in window.samples
            ):
                violation, reason = True, "flow_tracking_deficit"
            else:
                violation, reason = None, "output_hysteresis"
        if violation is None:
            window.pending = window.pending_at = window.pending_seen = None
            return HeatingResult(None, reason)
        if window.pending is not violation or window.pending_at is None:
            window.pending, window.pending_at, window.pending_seen = (
                violation,
                last.at,
                last.seen,
            )
        duration = max(
            0.0,
            min(last.at - window.pending_at, last.seen - float(window.pending_seen)),
        )
        thresholds: tuple[tuple[str, float | int], ...] = (
            (
                ("minimum_rise_k", policy.minimum_rise_k),
                ("recovery_rise_k", policy.recovery_rise_k),
                ("minimum_target_deficit_k", policy.minimum_target_deficit_k),
                ("target_recovery_margin_k", policy.target_recovery_margin_k),
            )
            if isinstance(policy, HeatingRisePolicy)
            else (
                ("failure_deficit_k", policy.failure_deficit_k),
                ("recovery_deficit_k", policy.recovery_deficit_k),
            )
        )
        return HeatingResult(
            violation,
            reason,
            observed_qualification_seconds=duration,
            window_evidence=(
                ("anchor_at", first.at),
                ("latest_at", last.at),
                ("anchor_temperature", first.temperature),
                ("latest_temperature", last.temperature),
                ("observed_span_seconds", last.at - first.at),
                ("runtime_span_seconds", last.seen - first.seen),
                ("sample_count", len(window.samples)),
                ("observed_qualification_seconds", duration),
                ("failure_seconds", policy.failure_seconds),
                ("recovery_seconds", policy.recovery_seconds),
                *thresholds,
                ("required_sample_count", policy.minimum_sample_count),
                ("required_span_seconds", policy.observation_window_seconds),
                ("maximum_gap_seconds", policy.maximum_sample_gap_seconds),
                (
                    "observed_maximum_gap_seconds",
                    max(
                        b.at - a.at
                        for a, b in zip(
                            window.samples, window.samples[1:], strict=False
                        )
                    ),
                ),
                (
                    "runtime_maximum_gap_seconds",
                    max(
                        b.seen - a.seen
                        for a, b in zip(
                            window.samples, window.samples[1:], strict=False
                        )
                    ),
                ),
                ("rise_k", last.temperature - first.temperature),
                ("target", target),
                ("latest_deficit_k", deficit),
                (
                    "minimum_deficit_k",
                    min(target - item.temperature for item in window.samples),
                ),
                (
                    "maximum_deficit_k",
                    max(target - item.temperature for item in window.samples),
                ),
            ),
        )
