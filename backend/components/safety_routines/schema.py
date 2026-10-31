"""Closed configuration contracts for bounded, read-only safety routines."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityId = Annotated[str, Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$", max_length=255)]
StableId = Annotated[str, Field(pattern=r"^[A-Z][A-Za-z0-9]*$", max_length=48)]
Text = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]
State = Annotated[str, Field(min_length=1, max_length=64, pattern=r"\S")]


class RoutineModel(BaseModel):
    """Reject coercion, non-finite thresholds and unknown configuration keys."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Reading(RoutineModel):
    """Bind a value to explicit evidence of its physical observation time."""

    entity_id: EntityId
    attribute: Text | None = None
    observed_at_entity_id: EntityId | None = None
    observed_at_attribute: Text | None = None
    max_age_seconds: int = Field(default=300, ge=1, le=86400)

    @model_validator(mode="after")
    def timestamp_required(self) -> Reading:
        """Require exactly one original timestamp source, never HA update time."""
        if bool(self.observed_at_entity_id) == bool(self.observed_at_attribute):
            raise ValueError(
                "provide exactly one observed_at_entity_id or observed_at_attribute"
            )
        return self


class RoutineCondition(Reading):
    """Known matching states apply a check; known other states skip it."""

    pass_states: list[State] = Field(min_length=1, max_length=16)
    skip_states: list[State] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def disjoint_states(self) -> RoutineCondition:
        """Keep applicability and deliberate exclusion unambiguous."""
        if set(self.pass_states) & set(self.skip_states):
            raise ValueError("condition pass_states and skip_states must be disjoint")
        return self


class RoutineCheck(Reading):
    """Evaluate a state or an inclusive numeric range without side effects."""

    name: Text
    kind: Literal["state", "numeric_range"] = "state"
    expected_states: list[State] | None = Field(
        default=None, min_length=1, max_length=16
    )
    minimum: float | None = None
    maximum: float | None = None
    unit: Text | None = None
    condition: RoutineCondition | None = None

    @model_validator(mode="after")
    def check_contract(self) -> RoutineCheck:
        """Require complete, non-contradictory expectations for each kind."""
        if self.kind == "state":
            if not self.expected_states or any(
                v is not None for v in (self.minimum, self.maximum, self.unit)
            ):
                raise ValueError(
                    "state checks require expected_states and no numeric settings"
                )
        else:
            if (
                self.expected_states is not None
                or not self.unit
                or (self.minimum is None and self.maximum is None)
            ):
                raise ValueError(
                    "numeric checks require unit and a bound, without expected_states"
                )
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("minimum must not exceed maximum")
            if self.attribute is not None:
                raise ValueError(
                    "numeric checks use sensor state with unit_of_measurement"
                )
        return self


class RoutineTrigger(RoutineModel):
    """Select one exact state transition or one named HA event."""

    kind: Literal["state", "event"]
    entity_id: EntityId | None = None
    from_state: State | None = None
    to_state: State | None = None
    event: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,100}$")] | None = None

    @model_validator(mode="after")
    def trigger_contract(self) -> RoutineTrigger:
        """Prevent partial triggers and loops through the routine API events."""
        if self.kind == "state":
            if (
                not self.entity_id
                or self.from_state is None
                or self.to_state is None
                or self.event is not None
            ):
                raise ValueError(
                    "state trigger requires entity_id, from_state and to_state only"
                )
            if self.from_state == self.to_state:
                raise ValueError("trigger must describe a state transition")
        elif (
            not self.event
            or self.event.startswith("safety_routine_")
            or any(
                value is not None
                for value in (self.entity_id, self.from_state, self.to_state)
            )
        ):
            raise ValueError("event trigger requires a non-reserved event name only")
        return self


class SafetyRoutine(RoutineModel):
    """One scenario with bounded delay, sampling window and check inventory."""

    name: Text
    enabled: bool = True
    delay_seconds: int = Field(default=0, ge=0, le=600)
    observation_seconds: int = Field(default=0, ge=0, le=300)
    triggers: list[RoutineTrigger] = Field(default_factory=list, max_length=4)
    checks: dict[StableId, RoutineCheck] = Field(min_length=1, max_length=24)


class SafetyRoutinesConfig(RoutineModel):
    """Optional additive runtime service; an empty registry has no checks."""

    routines: dict[StableId, SafetyRoutine] = Field(default_factory=dict, max_length=16)
