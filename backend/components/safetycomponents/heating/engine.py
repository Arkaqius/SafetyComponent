"""Generic heating capability catalog and admitted input-supervision predicate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .inputs import HeatingObservation

# Stable identities reserved by C-HVAC R01..R13. Catalog membership does not
# mean a safety path is implemented or admitted in this release.
RULES: dict[str, tuple[str, str, int]] = {
    "R01": ("sm_hsm_supervision_loss", "HeatingSupervisionLoss", 3),
    "R02": ("sm_hsm_device_fault", "HeatingDeviceFault", 3),
    "R03": ("sm_hsm_missing_demand", "HeatingMissingDemand", 3),
    "R04": ("sm_hsm_no_response", "HeatingNoResponse", 3),
    "R05": ("sm_hsm_no_flow_rise", "HeatingInsufficientOutput", 3),
    "R06": ("sm_hsm_flow_tracking", "HeatingInsufficientOutput", 3),
    "R07": ("sm_hsm_pump_mismatch", "HeatingDistributionSuspected", 3),
    "R08": ("sm_hsm_flow_return", "HeatingDistributionSuspected", 3),
    "R09": ("sm_hsm_room_delivery", "HeatingRoomDeliveryInsufficient", 3),
    "R10": ("sm_hsm_mode_overtemperature", "HeatingExcessTemperature", 2),
    "R11": ("sm_hsm_absolute_overtemperature", "HeatingExcessTemperature", 2),
    "R12": ("sm_hsm_short_cycling", "HeatingCyclingDiagnostic", 4),
    "R13": ("sm_hsm_maintenance", "HeatingMaintenance", 4),
}


@dataclass(frozen=True)
class HeatingResult:
    """Separate a diagnostic predicate from unknown or excluded safety paths."""

    violation: bool | None
    reason: str
    urgent: bool = False
    quality_cause: str | None = None
    onset_utc: float | None = None
    elapsed_seconds: float | None = None
    reference_target: float | None = None
    remaining_seconds: float | None = None
    observed_qualification_seconds: float | None = None
    window_evidence: tuple[tuple[str, float | int], ...] = ()


def supervise_inputs(inputs: Mapping[str, HeatingObservation]) -> HeatingResult:
    """Aggregate every owned cause; recovery requires every input to be valid."""
    if not inputs:
        return HeatingResult(None, "missing_input")
    invalid = any(
        item.quality not in {"valid", "availability_only"} for item in inputs.values()
    )
    health = inputs.get("source_health")
    failed = invalid or (health is not None and health.value is False)
    return HeatingResult(failed, "input_loss" if failed else "observed")


def observed_phase(inputs: Mapping[str, HeatingObservation]) -> str:
    """Resolve phase only from qualified observations, with shared-circuit DHW priority."""

    def value(role: str) -> object:
        item = inputs.get(role)
        expected_kind = "intent" if role == "heat_request" else "measurement"
        return (
            item.value
            if item and item.qualified and item.evidence_kind == expected_kind
            else None
        )

    if value("dhw_active") is True:
        return "dhw"
    if value("dhw_active") is not False:
        return "unknown"
    explicit = value("boiler_state")
    if explicit is not None:
        return str(explicit)
    if value("boiler_active") is True:
        return "heating"
    if value("boiler_active") is not False:
        return "unknown"
    if value("heat_request") is True:
        return "starting"
    if value("heat_request") is not False:
        return "unknown"
    if value("pump_active") is True:
        return "pump_overrun"
    return "idle"
