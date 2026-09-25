"""Qualification policy for host available memory corroborated by PSI."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable
from time import monotonic


@dataclass(frozen=True)
class MemoryPressureResult:
    """One memory rule outcome with fault and evidence validity kept separate."""

    status: str
    fault_active: bool
    evidence_valid: bool


class MemoryPressureRule:
    """Require both low available memory and elevated PSI before level two."""

    def __init__(
        self,
        *,
        low_available_mib: float,
        recovery_available_mib: float,
        high_psi_percent: float,
        recovery_psi_percent: float,
        qualification_seconds: float,
        recovery_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 0 < low_available_mib < recovery_available_mib:
            raise ValueError("Memory recovery margin must exceed the low threshold")
        if not 0 <= recovery_psi_percent < high_psi_percent <= 100:
            raise ValueError("PSI recovery margin must be below the high threshold")
        if qualification_seconds <= 0 or recovery_seconds <= 0:
            raise ValueError("Memory qualification times must be positive")
        self.low_available_mib = low_available_mib
        self.recovery_available_mib = recovery_available_mib
        self.high_psi_percent = high_psi_percent
        self.recovery_psi_percent = recovery_psi_percent
        self.qualification_seconds = qualification_seconds
        self.recovery_seconds = recovery_seconds
        self.clock = clock
        self.fault_active = False
        self._low_since: float | None = None
        self._recovery_since: float | None = None

    def observe(
        self,
        available_mib: float | None,
        psi_percent: float | None,
    ) -> MemoryPressureResult:
        """Never assert or clear a fault from missing or malformed evidence."""

        if not self._valid(available_mib, minimum=0) or not self._valid(
            psi_percent, minimum=0, maximum=100
        ):
            self._low_since = None
            self._recovery_since = None
            return MemoryPressureResult("unknown", self.fault_active, False)

        now = self.clock()
        assert available_mib is not None and psi_percent is not None
        low = available_mib <= self.low_available_mib and psi_percent >= self.high_psi_percent
        recovered = (
            available_mib >= self.recovery_available_mib
            and psi_percent <= self.recovery_psi_percent
        )

        if not self.fault_active:
            if not low:
                self._low_since = None
                return MemoryPressureResult("normal", False, True)
            if self._low_since is None:
                self._low_since = now
            if now - self._low_since < self.qualification_seconds:
                return MemoryPressureResult("qualifying", False, True)
            self.fault_active = True
            self._recovery_since = None
            return MemoryPressureResult("active", True, True)

        if not recovered:
            self._recovery_since = None
            return MemoryPressureResult("active", True, True)
        if self._recovery_since is None:
            self._recovery_since = now
        if now - self._recovery_since < self.recovery_seconds:
            return MemoryPressureResult("recovering", True, True)
        self.fault_active = False
        self._low_since = None
        self._recovery_since = None
        return MemoryPressureResult("normal", False, True)

    @staticmethod
    def _valid(
        value: float | None, *, minimum: float, maximum: float | None = None
    ) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return isfinite(value) and value >= minimum and (
            maximum is None or value <= maximum
        )
