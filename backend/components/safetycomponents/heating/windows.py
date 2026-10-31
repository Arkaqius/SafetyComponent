"""Bounded, source-qualified observation windows shared by physical checks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sample:
    """Immutable original source stamps, first receipt and physical values."""

    stamps: tuple[float, ...]
    seen: float
    values: tuple[float, ...]


@dataclass
class ObservedWindow:
    """Keep cached reports from extending coverage or qualification time."""

    samples: list[Sample] = field(default_factory=list)
    lost: bool = False
    pending: tuple[bool, str] | None = None
    pending_sample: Sample | None = None

    def reset(self, *, lost: bool = False) -> None:
        """Discard unqualified evidence while preserving known coverage loss."""
        self.samples.clear()
        self.pending = self.pending_sample = None
        self.lost = self.lost or lost

    def add(
        self,
        sample: Sample,
        span: int,
        gap: int,
        count: int,
        *,
        retain_span: int | None = None,
    ) -> str | None:
        """Require every original source to advance; bound source/runtime gaps."""
        if self.samples:
            last = self.samples[-1]
            if any(
                at < old for at, old in zip(sample.stamps, last.stamps, strict=True)
            ) or any(
                at == old and sample.values[index] != last.values[index]
                for index, (at, old) in enumerate(
                    zip(sample.stamps, last.stamps, strict=True)
                )
            ):
                self.reset(lost=True)
                return "invalid"
            if sample.seen - last.seen > gap or any(
                at - old > gap
                for at, old in zip(sample.stamps, last.stamps, strict=True)
            ):
                self.reset(lost=True)
            elif not all(
                at > old for at, old in zip(sample.stamps, last.stamps, strict=True)
            ):
                if sample.stamps != last.stamps:
                    self.pending = self.pending_sample = None
                    return "partial"
                return self._coverage(span, count)
        self.samples.append(sample)
        last = self.samples[-1]
        while len(self.samples) > 2 and self._span(self.samples[1], last) >= (
            retain_span or span
        ):
            self.samples.pop(0)
        if len(self.samples) > 4096:
            self.reset(lost=True)
            return "invalid"
        result = self._coverage(span, count)
        if result is None:
            self.lost = False
        return result

    def _coverage(self, span: int, count: int) -> str | None:
        if (
            len(self.samples) < count
            or self._span(self.samples[0], self.samples[-1]) < span
        ):
            return "lost" if self.lost else "collecting"
        return None

    @staticmethod
    def _span(first: Sample, last: Sample) -> float:
        return min(
            last.seen - first.seen,
            *(at - old for at, old in zip(last.stamps, first.stamps, strict=True)),
        )

    def qualify(self, violation: bool | None, reason: str) -> float | None:
        """Accrue one continuous predicate from original observations only."""
        if violation is None:
            self.pending = self.pending_sample = None
            return None
        token = (violation, reason if violation else "recovery")
        last = self.samples[-1]
        if self.pending != token or self.pending_sample is None:
            self.pending, self.pending_sample = token, last
        return max(0.0, self._span(self.pending_sample, last))

    def summary(self) -> tuple[tuple[str, float | int], ...]:
        """Retain a small decision proof rather than a full measurement buffer."""
        first, last = self.samples[0], self.samples[-1]
        return (
            ("anchor_at", min(first.stamps)),
            ("latest_at", min(last.stamps)),
            (
                "observed_span_seconds",
                min(
                    at - old for at, old in zip(last.stamps, first.stamps, strict=True)
                ),
            ),
            ("runtime_span_seconds", last.seen - first.seen),
            ("sample_count", len(self.samples)),
            (
                "maximum_source_gap_seconds",
                max(
                    max(at - old for at, old in zip(b.stamps, a.stamps, strict=True))
                    for a, b in zip(self.samples, self.samples[1:], strict=False)
                ),
            ),
        )
