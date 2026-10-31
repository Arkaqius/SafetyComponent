"""Closed installation mappings and system-owned heating policy."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from components.core.pydantic_utils import StrictBaseModel

COMPONENT_NAME = "HeatingSystemMonitorComponent"
RuleKey = Literal[
    "R01",
    "R02",
    "R03",
    "R04",
    "R05",
    "R06",
    "R07",
    "R08",
    "R09",
    "R10",
    "R11",
    "R12",
    "R13",
]
SignalRole = Literal[
    "source_health",
    "boiler_active",
    "boiler_state",
    "dhw_active",
    "pump_active",
    "power_percent",
    "power_w",
    "flow_temperature",
    "return_temperature",
    "requested_flow_temperature",
    "heat_request",
    "heating_permitted",
    "heat_delivery_active",
    "room_inhibited",
    "device_status",
    "maintenance_status",
    "inhibition_reason",
    "burner_starts_ch",
    "burner_starts_dhw",
    "room_temperature",
    "target_temperature",
]
BOOLEAN_ROLES = {
    "source_health",
    "boiler_active",
    "dhw_active",
    "pump_active",
    "heat_request",
    "heat_delivery_active",
    "room_inhibited",
    "heating_permitted",
}
TEXT_ROLES = {
    "boiler_state",
    "device_status",
    "maintenance_status",
    "inhibition_reason",
}
TEMPERATURE_ROLES = {
    "flow_temperature",
    "return_temperature",
    "requested_flow_temperature",
    "room_temperature",
    "target_temperature",
}


class HeatingModel(StrictBaseModel):
    """Reject misspelled or executable configuration fields."""

    model_config = ConfigDict(extra="forbid")


class HeatingStatusPolicy(HeatingModel):
    """Reviewed qualification of a fresh, explicitly classified current status."""

    evidence_reference: str = Field(min_length=1)
    failure_seconds: int = Field(ge=0, le=1800)
    recovery_seconds: int = Field(ge=1, le=3600)


class HeatingDemandPolicy(HeatingStatusPolicy):
    """Independent permitted room-need hysteresis and a bounded request allowance."""

    need_on_margin_k: float = Field(gt=0, allow_inf_nan=False)
    need_off_margin_k: float = Field(ge=0, allow_inf_nan=False)
    request_allowance_seconds: int = Field(ge=0, le=1800)
    maximum_unresolved_seconds: int = Field(ge=1, le=1800)
    maximum_input_skew_seconds: int = Field(ge=0, le=60)
    independent_need_reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def _hysteresis(self) -> HeatingDemandPolicy:
        if self.need_off_margin_k >= self.need_on_margin_k:
            raise ValueError(
                "room-need recovery margin must be below activation margin"
            )
        return self


class HeatingResponsePolicy(HeatingStatusPolicy):
    """Commissioned shared-circuit CH response and bounded inhibition timing."""

    startup_allowance_seconds: int = Field(ge=0, le=1800)
    maximum_inhibition_seconds: int = Field(ge=0, le=1800)
    maximum_unresolved_seconds: int = Field(ge=1, le=1800)
    target_recovery_margin_k: float = Field(ge=0, allow_inf_nan=False)
    maximum_input_skew_seconds: int = Field(ge=0, le=60)
    inhibition_context: Literal["none", "mapped_reason"]


class HeatingOutputPolicy(HeatingStatusPolicy):
    """Commissioned coverage and stable-target contract for physical CH output."""

    startup_allowance_seconds: int = Field(ge=0, le=1800)
    maximum_inhibition_seconds: int = Field(ge=0, le=1800)
    maximum_unresolved_seconds: int = Field(ge=1, le=1800)
    maximum_input_skew_seconds: int = Field(ge=0, le=60)
    inhibition_context: Literal["none", "mapped_reason"]
    observation_window_seconds: int = Field(ge=1, le=1800)
    minimum_sample_count: int = Field(ge=2, le=1801)
    maximum_sample_gap_seconds: int = Field(ge=1, le=1800)
    target_stability_tolerance_k: float = Field(ge=0, allow_inf_nan=False)


class HeatingRisePolicy(HeatingOutputPolicy):
    """Endpoint-rise bands for an eligible, sufficiently loaded flow window."""

    minimum_target_deficit_k: float = Field(gt=0, allow_inf_nan=False)
    minimum_rise_k: float = Field(gt=0, allow_inf_nan=False)
    recovery_rise_k: float = Field(gt=0, allow_inf_nan=False)
    target_recovery_margin_k: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _rise_bands(self) -> HeatingRisePolicy:
        if self.recovery_rise_k <= self.minimum_rise_k:
            raise ValueError("rise recovery must exceed the failure boundary")
        if self.target_recovery_margin_k >= self.minimum_target_deficit_k:
            raise ValueError(
                "rise target recovery must be narrower than its activation deficit"
            )
        return self


class HeatingTrackingPolicy(HeatingOutputPolicy):
    """Covered flow-deficit failure window and narrower positive recovery band."""

    failure_deficit_k: float = Field(gt=0, allow_inf_nan=False)
    recovery_deficit_k: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _tracking_bands(self) -> HeatingTrackingPolicy:
        if self.recovery_deficit_k >= self.failure_deficit_k:
            raise ValueError("tracking recovery must be narrower than failure")
        return self


class HeatingPumpPolicy(HeatingStatusPolicy):
    """A commissioned physical CH burner/pump relationship."""

    hydraulic_reference: str = Field(min_length=1)
    topology_requires_pump: Literal[True]
    startup_allowance_seconds: int = Field(ge=0, le=1800)
    maximum_unresolved_seconds: int = Field(ge=1, le=1800)
    maximum_input_skew_seconds: int = Field(ge=0, le=60)


class HeatingTrendPolicy(HeatingStatusPolicy):
    """Original-observation coverage for distribution and room delivery."""

    startup_allowance_seconds: int = Field(ge=0, le=1800)
    maximum_inhibition_seconds: int = Field(ge=0, le=1800)
    maximum_unresolved_seconds: int = Field(ge=1, le=1800)
    maximum_input_skew_seconds: int = Field(ge=0, le=60)
    inhibition_context: Literal["none", "mapped_reason"]
    observation_window_seconds: int = Field(ge=1, le=1800)
    minimum_sample_count: int = Field(ge=2, le=1801)
    maximum_sample_gap_seconds: int = Field(ge=1, le=1800)


class HeatingDifferentialPolicy(HeatingTrendPolicy):
    """Loaded physical flow/return limits; low load alone is not a fault."""

    hydraulic_reference: str = Field(min_length=1)
    load_role: Literal["power_percent", "power_w"]
    minimum_load: float = Field(gt=0, allow_inf_nan=False)
    minimum_flow_temperature_c: float = Field(gt=-273.15, lt=1000, allow_inf_nan=False)
    failure_delta_k: float = Field(gt=0, allow_inf_nan=False)
    recovery_delta_k: float = Field(ge=0, allow_inf_nan=False)
    inverted_failure_k: float = Field(gt=0, allow_inf_nan=False)
    inverted_recovery_k: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _bands(self) -> HeatingDifferentialPolicy:
        if (
            self.recovery_delta_k >= self.failure_delta_k
            or self.inverted_recovery_k >= self.inverted_failure_k
        ):
            raise ValueError(
                "distribution recovery bands must be narrower than failure"
            )
        if self.load_role == "power_percent" and self.minimum_load > 100:
            raise ValueError("percent load must fit the physical input range")
        return self


class HeatingRoomDeliveryPolicy(HeatingTrendPolicy):
    """Cooling during an independently evidenced room heat-delivery attempt."""

    delivery_reference: str = Field(min_length=1)
    need_on_margin_k: float = Field(gt=0, allow_inf_nan=False)
    need_off_margin_k: float = Field(ge=0, allow_inf_nan=False)
    minimum_cooling_k: float = Field(gt=0, allow_inf_nan=False)
    recovery_rise_k: float = Field(gt=0, allow_inf_nan=False)
    target_stability_tolerance_k: float = Field(ge=0, allow_inf_nan=False)
    room_inhibition_context: Literal["none", "mapped"]

    @model_validator(mode="after")
    def _bands(self) -> HeatingRoomDeliveryPolicy:
        if self.need_off_margin_k >= self.need_on_margin_k:
            raise ValueError(
                "room-delivery recovery band must be narrower than need-on"
            )
        return self


class HeatingThermalAllocation(HeatingModel):
    """Reviewed equipment response allocation, never a universal boiler deadline."""

    allocation_key: str = Field(pattern=r"^HSM-H05/[A-Za-z][A-Za-z0-9]*$")
    manufacturer_reference: str = Field(min_length=1)
    hydraulic_reference: str = Field(min_length=1)
    maximum_response_seconds: int = Field(ge=1, le=86400)
    detection_budget_seconds: int = Field(ge=1, le=86400)
    decision_budget_seconds: int = Field(ge=1, le=86400)
    notification_budget_seconds: int = Field(ge=30, le=86400)

    @model_validator(mode="after")
    def _allocation(self) -> HeatingThermalAllocation:
        if (
            self.detection_budget_seconds
            + self.decision_budget_seconds
            + self.notification_budget_seconds
            > self.maximum_response_seconds
        ):
            raise ValueError(
                "thermal portions exceed the equipment response allocation"
            )
        return self


class HeatingTemperatureEnvelope(HeatingModel):
    """Operating envelope including native hysteresis and measurement tolerance."""

    operating_maximum_c: float = Field(gt=-273.15, lt=1000, allow_inf_nan=False)
    native_hysteresis_k: float = Field(ge=0, allow_inf_nan=False)
    measurement_tolerance_k: float = Field(ge=0, allow_inf_nan=False)
    recovery_margin_k: float = Field(gt=0, allow_inf_nan=False)

    @property
    def failure_c(self) -> float:
        """Return the inclusive physical alarm boundary in normalized Celsius."""
        return (
            self.operating_maximum_c
            + self.native_hysteresis_k
            + self.measurement_tolerance_k
        )

    @property
    def recovery_c(self) -> float:
        """Return the stricter clear boundary."""
        return self.failure_c - self.recovery_margin_k

    @model_validator(mode="after")
    def _range(self) -> HeatingTemperatureEnvelope:
        if not -273.15 < self.recovery_c < self.failure_c < 1000:
            raise ValueError("thermal envelope must fit the physical measurement range")
        return self


class HeatingModeTemperaturePolicy(HeatingStatusPolicy):
    """Reviewed mode-specific envelopes for the commissioned hydraulic system."""

    allocation: HeatingThermalAllocation
    maximum_input_skew_seconds: int = Field(ge=0, le=60)
    envelopes: dict[
        Literal["idle", "starting", "heating", "dhw", "pump_overrun"],
        HeatingTemperatureEnvelope,
    ]

    @model_validator(mode="after")
    def _modes(self) -> HeatingModeTemperaturePolicy:
        if set(self.envelopes) != {
            "idle",
            "starting",
            "heating",
            "dhw",
            "pump_overrun",
        }:
            raise ValueError(
                "mode temperature policy requires every physical operating envelope"
            )
        return self


class HeatingAbsoluteTemperaturePolicy(HeatingStatusPolicy):
    """Absolute flow protection independent of demand or operating mode."""

    allocation: HeatingThermalAllocation
    absolute_limit_c: float = Field(gt=-273.15, lt=1000, allow_inf_nan=False)
    measurement_tolerance_k: float = Field(ge=0, allow_inf_nan=False)
    recovery_margin_k: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _range(self) -> HeatingAbsoluteTemperaturePolicy:
        threshold = self.absolute_limit_c - self.measurement_tolerance_k
        if not -273.15 < threshold - self.recovery_margin_k < threshold < 1000:
            raise ValueError(
                "absolute temperature boundaries must fit the physical range"
            )
        return self


class HeatingCyclingPolicy(HeatingStatusPolicy):
    """Covered CH/DHW counters and interval-bounded burner transitions."""

    counter_reference: str = Field(min_length=1)
    maximum_input_skew_seconds: int = Field(ge=0, le=3600)
    observation_window_seconds: int = Field(ge=1, le=3600)
    minimum_sample_count: int = Field(ge=2, le=3601)
    maximum_sample_gap_seconds: int = Field(ge=1, le=3600)
    maximum_counter_gap_seconds: int = Field(ge=1, le=3600)
    maximum_starts_ch: int = Field(ge=1, le=100000)
    maximum_starts_dhw: int = Field(ge=1, le=100000)
    recovery_starts_ch: int = Field(ge=0, le=100000)
    recovery_starts_dhw: int = Field(ge=0, le=100000)
    short_cycle_seconds: int = Field(ge=1, le=3600)
    minimum_short_cycles: int = Field(ge=1, le=100000)
    recovery_short_cycles: int = Field(ge=0, le=100000)
    minimum_recovery_cycles: int = Field(ge=1, le=100000)

    @model_validator(mode="after")
    def _bands(self) -> HeatingCyclingPolicy:
        if (
            self.recovery_starts_ch >= self.maximum_starts_ch
            or self.recovery_starts_dhw >= self.maximum_starts_dhw
            or self.recovery_short_cycles >= self.minimum_short_cycles
            or self.minimum_recovery_cycles
            > min(self.recovery_starts_ch, self.recovery_starts_dhw)
            or self.short_cycle_seconds <= 2 * self.maximum_sample_gap_seconds
        ):
            raise ValueError(
                "cycling recovery/transition bands are not independently observable"
            )
        return self


RULE_POLICY_FIELDS = {
    "R02": "device_fault",
    "R03": "missing_demand",
    "R04": "no_response",
    "R05": "flow_rise",
    "R06": "flow_tracking",
    "R07": "pump_response",
    "R08": "flow_return",
    "R09": "room_delivery",
    "R10": "mode_temperature",
    "R11": "absolute_temperature",
    "R12": "cycling",
    "R13": "maintenance",
}
RULE_INPUTS = {
    "R02": {"device_status"},
    "R03": {
        "room_temperature",
        "target_temperature",
        "heating_permitted",
        "heat_request",
    },
    "R04": {
        "heat_request",
        "boiler_active",
        "dhw_active",
        "flow_temperature",
        "requested_flow_temperature",
    },
    "R13": {"maintenance_status"},
    "R07": {"boiler_active", "dhw_active", "pump_active"},
    "R08": {
        "boiler_active",
        "dhw_active",
        "pump_active",
        "flow_temperature",
        "return_temperature",
    },
    "R09": {
        "boiler_active",
        "dhw_active",
        "pump_active",
        "room_temperature",
        "target_temperature",
        "heating_permitted",
        "heat_delivery_active",
    },
    "R10": {
        "flow_temperature",
        "boiler_active",
        "dhw_active",
        "pump_active",
        "heat_request",
    },
    "R11": {"flow_temperature"},
    "R12": {"burner_starts_ch", "burner_starts_dhw", "boiler_active", "dhw_active"},
}
RULE_INPUTS["R05"] = RULE_INPUTS["R04"]
RULE_INPUTS["R06"] = RULE_INPUTS["R04"]
INTENT_ROLES = {
    "heat_request",
    "target_temperature",
    "heating_permitted",
    "requested_flow_temperature",
    "inhibition_reason",
    "room_inhibited",
}


def required_inputs(rule: str, policy: HeatingStatusPolicy | None) -> set[str]:
    """Resolve the exact commissioned dependencies shared by validation/runtime."""
    required = set(RULE_INPUTS[rule])
    if (
        isinstance(
            policy, (HeatingResponsePolicy, HeatingOutputPolicy, HeatingTrendPolicy)
        )
        and policy.inhibition_context == "mapped_reason"
    ):
        required.add("inhibition_reason")
    if isinstance(policy, HeatingDifferentialPolicy):
        required.add(policy.load_role)
    if (
        isinstance(policy, HeatingRoomDeliveryPolicy)
        and policy.room_inhibition_context == "mapped"
    ):
        required.add("room_inhibited")
    return required


class HeatingInput(HeatingModel):
    """Select a state/attribute and declare its semantics without service calls."""

    entity_id: str
    attribute: str | None = None
    value_map: dict[str, bool | float | str] = Field(default_factory=dict)
    unit: Literal["°C", "°F", "K", "%", "W", "kW", "count"] | None = None
    scale: float = Field(default=1.0, allow_inf_nan=False)
    offset: float = Field(default=0.0, allow_inf_nan=False)
    freshness: Literal["source_timestamp", "availability_only"] = "availability_only"
    observed_at_entity_id: str | None = None
    observed_at_attribute: str | None = None
    max_age_seconds: int = Field(default=120, ge=1, le=86400)
    evidence_kind: Literal["measurement", "intent", "contact"]
    independence_group: str = Field(min_length=1, max_length=100)
    shared_temperature: bool = False

    @field_validator("entity_id", "observed_at_entity_id")
    @classmethod
    def _entity(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value):
            raise ValueError("expected a Home Assistant entity ID")
        return value

    @field_validator("attribute", "observed_at_attribute")
    @classmethod
    def _attribute(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_]+", value):
            raise ValueError("attribute must be a literal attribute name")
        return value

    @model_validator(mode="after")
    def _timestamp_contract(self) -> HeatingInput:
        if self.freshness == "source_timestamp" and not (
            self.observed_at_attribute or self.observed_at_entity_id
        ):
            raise ValueError(
                "source_timestamp requires an observation timestamp selector"
            )
        if self.freshness == "availability_only" and (
            self.observed_at_attribute or self.observed_at_entity_id
        ):
            raise ValueError("timestamp selectors require source_timestamp freshness")
        if self.scale == 0:
            raise ValueError("input scale must not erase observations")
        return self


class HeatingRoom(HeatingModel):
    """Optional room evidence, independently bound rather than inferred by name."""

    friendly_name: str = Field(min_length=1)
    inputs: dict[
        Literal[
            "room_temperature",
            "target_temperature",
            "heating_permitted",
            "heat_delivery_active",
            "room_inhibited",
        ],
        HeatingInput,
    ]


class HeatingInstallation(HeatingModel):
    """A selected installation; an empty registry creates no default system."""

    friendly_name: str = Field(min_length=1)
    profile: str = "Diagnostic"
    inputs: dict[SignalRole, HeatingInput] = Field(min_length=1, max_length=32)
    rooms: dict[str, HeatingRoom] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def _stable_rooms(self) -> HeatingInstallation:
        for role, binding in self.inputs.items():
            if binding.shared_temperature and role not in TEMPERATURE_ROLES:
                raise ValueError("only temperature inputs may share C-TEMP ownership")
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key) for key in self.rooms):
            raise ValueError("room keys must be stable alphanumeric identifiers")
        if len({key.lower() for key in self.rooms}) != len(self.rooms):
            raise ValueError("room keys collide after normalization")
        return self


class HeatingProfile(HeatingModel):
    """System-owned qualification of diagnostic input supervision."""

    enabled_rules: list[RuleKey] = Field(default_factory=lambda: ["R01"])
    provenance: str = Field(min_length=1)
    failure_seconds: int = Field(default=5, ge=0, le=1800)
    recovery_seconds: int = Field(default=60, ge=1, le=3600)
    device_fault: HeatingStatusPolicy | None = None
    missing_demand: HeatingDemandPolicy | None = None
    no_response: HeatingResponsePolicy | None = None
    flow_rise: HeatingRisePolicy | None = None
    flow_tracking: HeatingTrackingPolicy | None = None
    pump_response: HeatingPumpPolicy | None = None
    flow_return: HeatingDifferentialPolicy | None = None
    room_delivery: HeatingRoomDeliveryPolicy | None = None
    mode_temperature: HeatingModeTemperaturePolicy | None = None
    absolute_temperature: HeatingAbsoluteTemperaturePolicy | None = None
    cycling: HeatingCyclingPolicy | None = None
    maintenance: HeatingStatusPolicy | None = None

    @model_validator(mode="after")
    def _admission(self) -> HeatingProfile:
        if "R01" not in self.enabled_rules or len(set(self.enabled_rules)) != len(
            self.enabled_rules
        ):
            raise ValueError("heating profiles require one R01 supervisor")
        for rule, field in RULE_POLICY_FIELDS.items():
            if (rule in self.enabled_rules) != (getattr(self, field) is not None):
                raise ValueError(
                    f"{rule} enablement and its reviewed {field} policy must agree"
                )
        if self.mode_temperature and self.absolute_temperature:
            mode, absolute = self.mode_temperature, self.absolute_temperature
            if mode.allocation != absolute.allocation:
                raise ValueError(
                    "mode and absolute protection require the same equipment allocation"
                )
            if any(
                envelope.failure_c
                >= absolute.absolute_limit_c - absolute.measurement_tolerance_k
                for envelope in mode.envelopes.values()
            ):
                raise ValueError(
                    "mode envelopes must remain below the absolute thermal boundary"
                )
        return self

    def rule_policy(self, rule: str) -> HeatingStatusPolicy | None:
        """Return selected system-owned policy without changing R01 defaults."""
        field = RULE_POLICY_FIELDS.get(rule)
        return getattr(self, field) if field else None


class HeatingCalibration(HeatingModel):
    """Bounded evaluation and persistence policy for all heating systems."""

    evaluation_interval_seconds: int = Field(default=5, ge=1, le=30)
    state_file: str = "/config/appdaemon/heating_monitor_state.json"
    maximum_systems: int = Field(default=8, ge=1, le=16)
    maximum_clock_drift_seconds: int = Field(default=2, ge=1, le=10)
    profiles: dict[str, HeatingProfile] = Field(
        default_factory=lambda: {
            "Diagnostic": HeatingProfile(
                provenance="Input availability diagnostics only; no thermal safety allocation"
            )
        }
    )


class HeatingConfig(HeatingCalibration):
    """Compiled runtime policy and installation registry."""

    systems: dict[str, HeatingInstallation] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _systems(self) -> HeatingConfig:
        if len(self.systems) > self.maximum_systems:
            raise ValueError("heating installation storage bound exceeded")
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key) for key in self.systems):
            raise ValueError(
                "installation keys must be stable alphanumeric identifiers"
            )
        if len({key.lower() for key in self.systems}) != len(self.systems):
            raise ValueError("heating installation keys collide after normalization")
        for system in self.systems.values():
            if system.profile not in self.profiles:
                raise ValueError("unknown heating profile")
            if not any(
                not binding.shared_temperature for binding in system.inputs.values()
            ) and not any(
                not binding.shared_temperature
                for room in system.rooms.values()
                for binding in room.inputs.values()
            ):
                raise ValueError("R01 requires at least one component-owned input")
            profile = self.profiles[system.profile]
            for rule in profile.enabled_rules:
                if rule == "R01":
                    continue
                policy = profile.rule_policy(rule)
                assert policy is not None
                required = required_inputs(rule, policy)
                room_maps: list[HeatingRoom | None] = (
                    list(system.rooms.values())
                    if rule in {"R03", "R09"} and system.rooms
                    else [None]
                )
                for room in room_maps:
                    bindings: dict[str, HeatingInput] = {
                        str(role): binding for role, binding in system.inputs.items()
                    }
                    if room:
                        bindings.update(
                            {
                                str(role): binding
                                for role, binding in room.inputs.items()
                            }
                        )
                    missing = required - bindings.keys()
                    if missing:
                        raise ValueError(
                            f"{rule} requires mapped inputs: {sorted(missing)}"
                        )
                    selected = [bindings[role] for role in required]
                    for role in required:
                        binding = bindings[role]
                        kind = "intent" if role in INTENT_ROLES else "measurement"
                        if (
                            binding.freshness != "source_timestamp"
                            or binding.evidence_kind != kind
                        ):
                            raise ValueError(
                                f"{rule}/{role} requires fresh original {kind} observations"
                            )
                    if rule == "R03" and any(
                        bindings[role].independence_group
                        == bindings["heat_request"].independence_group
                        for role in (
                            "room_temperature",
                            "target_temperature",
                            "heating_permitted",
                        )
                    ):
                        raise ValueError(
                            "R03 requires independently sourced room need and permission"
                        )
                    maximum_age = max(binding.max_age_seconds for binding in selected)
                    latency = (
                        maximum_age + 2 * self.evaluation_interval_seconds + 1 + 30
                    )
                    if (
                        rule
                        in {
                            "R02",
                            "R03",
                            "R04",
                            "R05",
                            "R06",
                            "R07",
                            "R08",
                            "R09",
                            "R10",
                            "R11",
                        }
                        and latency + profile.failure_seconds > 60
                    ):
                        raise ValueError(
                            f"{rule} required input loss exceeds the 60-second source budget"
                        )
                    if isinstance(policy, (HeatingDemandPolicy, HeatingResponsePolicy)):
                        allowance = (
                            policy.request_allowance_seconds
                            if isinstance(policy, HeatingDemandPolicy)
                            else policy.startup_allowance_seconds
                            + policy.maximum_inhibition_seconds
                        )
                        if (
                            latency + allowance + policy.failure_seconds
                            > policy.maximum_unresolved_seconds
                        ):
                            raise ValueError(
                                f"{rule} complete timing allocation exceeds its unresolved-need budget"
                            )
                    if isinstance(
                        policy,
                        (HeatingOutputPolicy, HeatingTrendPolicy, HeatingCyclingPolicy),
                    ):
                        cadence = self.evaluation_interval_seconds
                        window = policy.observation_window_seconds
                        gap = policy.maximum_sample_gap_seconds
                        if (
                            isinstance(policy, HeatingCyclingPolicy)
                            and not cadence
                            <= policy.maximum_counter_gap_seconds
                            <= window
                        ):
                            raise ValueError(
                                "cycling counter coverage is not achievable at its cadence"
                            )
                        if (
                            window < cadence
                            or not cadence <= gap <= window
                            or policy.minimum_sample_count
                            > (window + cadence - 1) // cadence + 1
                        ):
                            raise ValueError(
                                f"{rule} observation coverage is not achievable at its cadence"
                            )
                        retention = window
                        if isinstance(policy, HeatingCyclingPolicy):
                            retention += (
                                policy.maximum_counter_gap_seconds
                                + policy.maximum_input_skew_seconds
                            )
                        if (retention + cadence - 1) // cadence + 2 > 4096:
                            raise ValueError(
                                "observation retention exceeds bounded capacity"
                            )
                    if isinstance(policy, (HeatingOutputPolicy, HeatingTrendPolicy)):
                        if (
                            latency
                            + policy.startup_allowance_seconds
                            + policy.maximum_inhibition_seconds
                            + window
                            + gap
                            + max(policy.failure_seconds, profile.failure_seconds)
                            > policy.maximum_unresolved_seconds
                        ):
                            raise ValueError(
                                f"{rule} complete output timing exceeds its unresolved-need budget"
                            )
                    if (
                        isinstance(policy, HeatingPumpPolicy)
                        and latency
                        + policy.startup_allowance_seconds
                        + max(policy.failure_seconds, profile.failure_seconds)
                        > policy.maximum_unresolved_seconds
                    ):
                        raise ValueError(
                            "pump response timing exceeds its unresolved-need budget"
                        )
                    if isinstance(
                        policy,
                        (
                            HeatingModeTemperaturePolicy,
                            HeatingAbsoluteTemperaturePolicy,
                        ),
                    ):
                        if (
                            maximum_age
                            + 2 * self.evaluation_interval_seconds
                            + policy.failure_seconds
                            > policy.allocation.detection_budget_seconds
                        ):
                            raise ValueError(
                                "thermal detection exceeds the equipment allocation"
                            )
        return self
