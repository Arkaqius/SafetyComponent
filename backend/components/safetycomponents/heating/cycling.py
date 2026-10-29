"""Informational cycling diagnostics from covered counters and burner samples."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .engine import HeatingResult
from .inputs import HeatingObservation
from .schema import HeatingCyclingPolicy
from .windows import ObservedWindow, Sample


@dataclass(frozen=True)
class Cycle:
    """An observed cycle with defensible lower and upper duration bounds."""

    mode: str
    start: float
    stop: float
    lower: float
    upper: float


@dataclass
class CyclingFrame:
    """Ephemeral baselines and transitions; restart never restores fake samples."""

    fast: ObservedWindow = field(default_factory=ObservedWindow)
    counters: dict[str, ObservedWindow] = field(
        default_factory=lambda: {"ch": ObservedWindow(), "dhw": ObservedWindow()}
    )
    processed: Sample | None = None
    opening: tuple[str, float, float] | None = None
    cycles: list[Cycle] = field(default_factory=list)
    qualifiers: dict[str, tuple[bool, float, float]] = field(default_factory=dict)


class CyclingRules:
    """Track mode-specific maintenance causes without inferring thermal danger."""

    def __init__(self) -> None:
        self.frames: dict[str, CyclingFrame] = {}
        self.active_modes: dict[str, set[str]] = {}

    def reset(self, key: str) -> None:
        """Rebuild history while retaining affected CH/DHW incident causes."""
        self.frames.pop(key, None)

    def invalidate(self) -> None:
        """Discard windows after timing discontinuity without healing a cause."""
        self.frames.clear()

    @staticmethod
    def _transition(frame: CyclingFrame, current: Sample) -> None:
        previous = frame.processed
        if previous is None or previous.stamps == current.stamps:
            frame.processed = current
            return
        was_on, now_on = bool(previous.values[0]), bool(current.values[0])
        mode = "dhw" if current.values[1] else "ch"
        if not was_on and now_on:
            frame.opening = (mode, previous.stamps[0], current.stamps[0])
        elif (
            was_on and now_on and frame.opening is not None and frame.opening[0] != mode
        ):
            frame.opening = None
        elif was_on and not now_on:
            if frame.opening is not None:
                cause, earliest, latest = frame.opening
                frame.cycles.append(
                    Cycle(
                        cause,
                        earliest,
                        current.stamps[0],
                        max(0.0, previous.stamps[0] - latest),
                        current.stamps[0] - earliest,
                    )
                )
            frame.opening = None
        frame.processed = current

    def evaluate(
        self,
        policy: HeatingCyclingPolicy,
        inputs: Mapping[str, HeatingObservation],
        mono: float,
        key: str,
    ) -> HeatingResult:
        """Require actual coverage; idle/reset/ambiguous history never proves HEAL."""
        frame = self.frames.setdefault(key, CyclingFrame())
        window = policy.observation_window_seconds
        retain = (
            window
            + policy.maximum_counter_gap_seconds
            + policy.maximum_input_skew_seconds
        )
        fast_roles = ("boiler_active", "dhw_active")
        fast = Sample(
            tuple(inputs[role].source_time for role in fast_roles),
            mono,
            tuple(inputs[role].number for role in fast_roles),
        )
        if max(fast.stamps) - min(fast.stamps) > policy.maximum_sample_gap_seconds:
            self.reset(key)
            return HeatingResult(None, "cycling_history_incomplete")
        fast_coverage = frame.fast.add(
            fast,
            window,
            policy.maximum_sample_gap_seconds,
            policy.minimum_sample_count,
            retain_span=retain,
        )
        if fast_coverage == "partial":
            frame.qualifiers.clear()
            frame.opening = frame.processed = None
            return HeatingResult(None, "cycling_history_incomplete")
        if fast_coverage in {"lost", "invalid"}:
            self.reset(key)
            return HeatingResult(None, "cycling_history_incomplete")
        self._transition(frame, frame.fast.samples[-1])
        counter_coverage: dict[str, str | None] = {}
        for mode in ("ch", "dhw"):
            source = inputs[f"burner_starts_{mode}"]
            series = frame.counters[mode]
            value = source.number
            if series.samples and value < series.samples[-1].values[0]:
                self.reset(key)
                return HeatingResult(None, "cycling_counter_reset")
            counter_coverage[mode] = series.add(
                Sample((source.source_time,), mono, (value,)),
                window,
                policy.maximum_counter_gap_seconds,
                2,
            )
            if counter_coverage[mode] in {"lost", "invalid"}:
                self.reset(key)
                return HeatingResult(None, "cycling_history_incomplete")
        if len(frame.cycles) > 4096:
            self.reset(key)
            return HeatingResult(None, "cycling_history_incomplete")
        cutoff = min(fast.stamps) - retain
        frame.cycles = [cycle for cycle in frame.cycles if cycle.stop >= cutoff]
        if fast_coverage or any(counter_coverage.values()):
            return HeatingResult(None, "collecting_samples")
        statuses: dict[str, bool | None] = {}
        durations: dict[str, float] = {}
        proof: list[tuple[str, float | int]] = []
        active_modes = self.active_modes.get(key, set())
        for mode in ("ch", "dhw"):
            series = frame.counters[mode]
            first, last = series.samples[0], series.samples[-1]
            start, end = first.stamps[0], last.stamps[0]
            if (
                max(frame.fast.samples[0].stamps) > start
                or min(frame.fast.samples[-1].stamps) < end
            ):
                return HeatingResult(None, "cycling_history_incomplete")
            span = end - start
            starts = last.values[0] - first.values[0]
            cycles = [
                cycle
                for cycle in frame.cycles
                if cycle.mode == mode and cycle.start >= start and cycle.stop <= end
            ]
            short = [
                cycle for cycle in cycles if cycle.upper < policy.short_cycle_seconds
            ]
            long = [
                cycle for cycle in cycles if cycle.lower >= policy.short_cycle_seconds
            ]
            rate, short_rate = starts * window / span, len(short) * window / span
            maximum = (
                policy.maximum_starts_ch if mode == "ch" else policy.maximum_starts_dhw
            )
            recovery = (
                policy.recovery_starts_ch
                if mode == "ch"
                else policy.recovery_starts_dhw
            )
            if rate > maximum and short_rate >= policy.minimum_short_cycles:
                status: bool | None = True
            elif (
                starts == len(cycles)
                and len(short) + len(long) == len(cycles)
                and rate <= recovery
                and short_rate <= policy.recovery_short_cycles
                and len(long) >= policy.minimum_recovery_cycles
            ):
                status = False
            elif mode not in active_modes and starts == 0:
                status = False  # Not a recovery of an affected mode.
            else:
                status = None
            statuses[mode] = status
            at, seen = (
                min(end, min(frame.fast.samples[-1].stamps)),
                min(last.seen, frame.fast.samples[-1].seen),
            )
            if status is None:
                frame.qualifiers.pop(mode, None)
                durations[mode] = 0
            else:
                pending = frame.qualifiers.get(mode)
                if pending is None or pending[0] is not status:
                    pending = (status, at, seen)
                    frame.qualifiers[mode] = pending
                durations[mode] = max(0.0, min(at - pending[1], seen - pending[2]))
            if status is True and durations[mode] >= policy.failure_seconds:
                active_modes.add(mode)
                self.active_modes[key] = active_modes
            proof.extend(
                (
                    (f"{mode}_anchor_at", start),
                    (f"{mode}_latest_at", end),
                    (f"{mode}_covered_seconds", span),
                    (f"{mode}_counter_delta", starts),
                    (f"{mode}_starts_per_window", rate),
                    (f"{mode}_short_cycles", len(short)),
                    (f"{mode}_long_cycles", len(long)),
                )
            )
        failed = [mode for mode, status in statuses.items() if status is True]
        if failed:
            violation, reason, duration = (
                True,
                "cycling_excessive",
                max(durations[mode] for mode in failed),
            )
        elif active_modes and all(statuses[mode] is False for mode in active_modes):
            violation, reason, duration = (
                False,
                "cycling_recovered",
                min(durations[mode] for mode in active_modes),
            )
        elif active_modes:
            return HeatingResult(
                None,
                "cycling_comparable_operation_needed",
                window_evidence=tuple(proof),
            )
        elif all(status is False for status in statuses.values()):
            violation, reason, duration = False, "observed", min(durations.values())
        else:
            return HeatingResult(None, "not_applicable", window_evidence=tuple(proof))
        return HeatingResult(
            violation,
            reason,
            observed_qualification_seconds=duration,
            window_evidence=tuple(proof)
            + (
                ("short_cycle_seconds", policy.short_cycle_seconds),
                ("minimum_short_cycles", policy.minimum_short_cycles),
            ),
        )
