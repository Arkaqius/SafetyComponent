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


RULE_POLICY_FIELDS = {
    "R02": "device_fault",
    "R03": "missing_demand",
    "R04": "no_response",
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
}
INTENT_ROLES = {
    "heat_request",
    "target_temperature",
    "heating_permitted",
    "requested_flow_temperature",
    "inhibition_reason",
}


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
        Literal["room_temperature", "target_temperature", "heating_permitted"],
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
    maintenance: HeatingStatusPolicy | None = None

    @model_validator(mode="after")
    def _admission(self) -> HeatingProfile:
        if "R01" not in self.enabled_rules or len(set(self.enabled_rules)) != len(
            self.enabled_rules
        ):
            raise ValueError("heating profiles require one R01 supervisor")
        if set(self.enabled_rules) - {"R01", *RULE_POLICY_FIELDS}:
            raise ValueError("Only R01/R02/R03/R04/R13 are implemented and admissible")
        for rule, field in RULE_POLICY_FIELDS.items():
            if (rule in self.enabled_rules) != (getattr(self, field) is not None):
                raise ValueError(
                    f"{rule} enablement and its reviewed {field} policy must agree"
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
                required = set(RULE_INPUTS[rule])
                if (
                    rule == "R04"
                    and isinstance(policy, HeatingResponsePolicy)
                    and policy.inhibition_context == "mapped_reason"
                ):
                    required.add("inhibition_reason")
                room_maps = (
                    list(system.rooms.values())
                    if rule == "R03" and system.rooms
                    else [None]
                )
                for room in room_maps:
                    bindings = {**system.inputs, **(room.inputs if room else {})}
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
                        rule in {"R02", "R03", "R04"}
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
        return self
