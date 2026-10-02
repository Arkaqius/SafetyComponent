"""Scoped diagnostic restriction and coverage contract tests."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from components.core.degradation import (
    CoverageState,
    DegradationRegistry,
    DegradationTarget,
    DiagnosticBinding,
    RestrictionEffect,
    compile_runtime_bindings,
)
from components.core.fault_state_policy import FaultCategory
from components.core.types_common import Fault, FaultState, RecoveryResult
from components.recovery_manager.recovery_manager import RecoveryManager


def _registry(*, recovery_only: bool = False) -> DegradationRegistry:
    symptoms = {
        name: SimpleNamespace(sm_name=name)
        for name in ("room_a", "room_b", "input_a", "provider_a", "external_only")
    }
    faults = {
        name: Fault(name, [name], 3, category=category)
        for name, category in (
            ("room_a", FaultCategory.H),
            ("room_b", FaultCategory.H),
            ("input_a", FaultCategory.D),
            ("provider_a", FaultCategory.D),
            ("external_only", FaultCategory.D),
        )
    }
    effect = RestrictionEffect.RECOVERY if recovery_only else RestrictionEffect.EVALUATION
    target = DegradationTarget("room_a", "temperature", "room_a", effect)
    return DegradationRegistry(symptoms, faults, (
        DiagnosticBinding("input_a", (target,)),
        DiagnosticBinding("provider_a", (target,)),
        DiagnosticBinding("external_only", (), external_only=True),
    ))


def test_room_loss_is_local_and_overlapping_causes_clear_independently() -> None:
    registry = _registry()
    for name in ("input_a", "provider_a", "external_only", "room_a", "room_b"):
        registry.observe(symptom_id=name, state=FaultState.CLEARED)
    assert registry.snapshot()["state"] == CoverageState.FULL.value

    registry.observe(symptom_id="input_a", state=FaultState.SET)
    registry.observe(symptom_id="provider_a", state=FaultState.SET)
    assert registry.snapshot()["state"] == CoverageState.DEGRADED.value
    assert registry.causes_for("room_b", RestrictionEffect.EVALUATION) == ()
    assert not registry.recovery_allowed("room_a")
    assert registry.recovery_allowed("room_b")

    registry.observe(symptom_id="input_a", state=FaultState.CLEARED)
    assert registry.causes_for("room_a", RestrictionEffect.EVALUATION) == ("provider_a",)
    registry.mark_unavailable(symptom_id="provider_a")
    assert not registry.recovery_allowed("room_a")
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value
    registry.observe(symptom_id="provider_a", state=FaultState.CLEARED)
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value
    registry.observe(symptom_id="room_a", state=FaultState.CLEARED)
    assert registry.snapshot()["state"] == CoverageState.FULL.value


def test_restart_starts_unknown_and_never_infers_a_clear() -> None:
    registry = _registry()
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value
    assert not registry.recovery_allowed("room_a")
    assert not registry.recovery_allowed("room_b")
    registry.observe(symptom_id="room_a", state=FaultState.SET)
    registry.observe(symptom_id="input_a", state=FaultState.CLEARED)
    registry.observe(symptom_id="provider_a", state=FaultState.CLEARED)
    registry.observe(symptom_id="external_only", state=FaultState.CLEARED)
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value


def test_recovery_only_loss_is_degraded_but_not_global() -> None:
    registry = _registry(recovery_only=True)
    for name in ("input_a", "provider_a", "external_only", "room_a", "room_b"):
        registry.observe(symptom_id=name, state=FaultState.CLEARED)
    registry.observe(symptom_id="input_a", state=FaultState.SET)
    assert registry.snapshot()["state"] == CoverageState.DEGRADED.value
    assert not registry.recovery_allowed("room_a")
    assert registry.recovery_allowed("room_b")


def test_declared_exclusion_is_partial_without_removing_baseline() -> None:
    registry = _registry()
    for name in ("input_a", "provider_a", "external_only", "room_a", "room_b"):
        registry.observe(symptom_id=name, state=FaultState.CLEARED)
    registry.set_exclusion("room_a", "operator_disabled")
    snapshot = registry.snapshot()
    assert snapshot["state"] == CoverageState.PARTIAL.value
    assert snapshot["baseline_count"] == 2
    assert snapshot["exclusions"] == {"room_a": "operator_disabled"}
    assert not registry.recovery_allowed("room_a")
    registry.set_exclusion("room_a", None)
    assert registry.snapshot()["state"] == CoverageState.FULL.value


def test_missing_and_ambiguous_targets_are_rejected() -> None:
    registry = _registry()
    symptoms = registry._symptoms
    faults = registry._faults
    with pytest.raises(ValueError, match="Missing H target"):
        DegradationRegistry(symptoms, faults, (
            DiagnosticBinding("input_a", (
                DegradationTarget("missing", "temperature", "room", RestrictionEffect.EVALUATION),
            )),
            DiagnosticBinding("provider_a", (), external_only=True),
            DiagnosticBinding("external_only", (), external_only=True),
        ))
    with pytest.raises(ValueError, match="without degradation declarations"):
        DegradationRegistry(symptoms, faults, (
            DiagnosticBinding("input_a", (), external_only=True),
        ))
    with pytest.raises(ValueError, match="Duplicate H target"):
        target = DegradationTarget("room_a", "temperature", "room_a", RestrictionEffect.EVALUATION)
        DegradationRegistry(symptoms, faults, (
            DiagnosticBinding("input_a", (target, target)),
            DiagnosticBinding("provider_a", (), external_only=True),
            DiagnosticBinding("external_only", (), external_only=True),
        ))


def test_provider_subsets_keep_weather_and_aq_independent() -> None:
    symptoms = {
        "weather": SimpleNamespace(
            sm_name="sm_ext_weather_exposure", parameters={"opening_name": "balcony"}
        ),
        "aq": SimpleNamespace(
            sm_name="sm_ext_outdoor_air_quality_exposure",
            parameters={"opening_name": "balcony"},
        ),
        "weather_provider": SimpleNamespace(
            sm_name="sm_ext_provider_unavailable",
            parameters={"capability": "WeatherPointModel"},
        ),
        "aq_provider": SimpleNamespace(
            sm_name="sm_ext_provider_unavailable",
            parameters={"capability": "OutdoorAirQuality"},
        ),
    }
    faults = {
        "weather": Fault("weather", ["sm_ext_weather_exposure"], 2),
        "aq": Fault("aq", ["sm_ext_outdoor_air_quality_exposure"], 3),
        "provider": Fault(
            "provider", ["sm_ext_provider_unavailable"], 3,
            category=FaultCategory.D,
        ),
    }
    registry = DegradationRegistry(
        symptoms, faults, compile_runtime_bindings(symptoms, ())
    )
    for symptom_id in ("weather_provider", "aq_provider", "weather", "aq"):
        registry.observe(symptom_id=symptom_id, state=FaultState.CLEARED)
    registry.observe(symptom_id="aq_provider", state=FaultState.SET)
    assert registry.causes_for("weather", RestrictionEffect.EVALUATION) == ()
    assert registry.causes_for("aq", RestrictionEffect.EVALUATION) == ("aq_provider",)
    assert registry.recovery_allowed(
        "weather", evidence_source="OpenMeteoWeatherApiComponent"
    )
    assert not registry.recovery_allowed(
        "aq", evidence_source="OpenMeteoAirQualityApiComponent"
    )


def test_redundant_weather_source_keeps_its_recovery_eligible() -> None:
    symptoms = {
        "weather": SimpleNamespace(
            sm_name="sm_ext_weather_exposure", parameters={"opening_name": "gate"}
        ),
        "point": SimpleNamespace(
            sm_name="sm_ext_provider_unavailable",
            parameters={"capability": "WeatherPointModel"},
        ),
        "warning": SimpleNamespace(
            sm_name="sm_ext_provider_unavailable",
            parameters={"capability": "OfficialWeatherWarnings"},
        ),
    }
    faults = {
        "weather": Fault("weather", ["sm_ext_weather_exposure"], 2),
        "provider": Fault(
            "provider", ["sm_ext_provider_unavailable"], 3,
            category=FaultCategory.D,
        ),
    }
    registry = DegradationRegistry(
        symptoms, faults, compile_runtime_bindings(symptoms, ())
    )
    for symptom_id in ("point", "warning", "weather"):
        registry.observe(symptom_id=symptom_id, state=FaultState.CLEARED)
    registry.observe(symptom_id="point", state=FaultState.SET)
    registry.observe(
        symptom_id="weather", state=FaultState.SET,
        additional_info={"source": "ImgwWarningsApiComponent"},
    )
    assert not registry.recovery_allowed(
        "weather", evidence_source="OpenMeteoWeatherApiComponent"
    )
    assert registry.recovery_allowed(
        "weather", evidence_source="ImgwWarningsApiComponent"
    )


def test_rejected_binding_keeps_only_its_known_scope_unknown() -> None:
    original = _registry()
    target_a = DegradationTarget(
        "room_a", "temperature", "room_a", RestrictionEffect.EVALUATION
    )
    registry = DegradationRegistry(
        original._symptoms,
        original._faults,
        (
            DiagnosticBinding("input_a", (
                target_a,
                DegradationTarget("missing", "temperature", "room_a", RestrictionEffect.EVALUATION),
            )),
            DiagnosticBinding("provider_a", (), external_only=True),
            DiagnosticBinding("external_only", (), external_only=True),
        ),
        isolate_invalid=True,
    )
    for symptom_id in original._symptoms:
        registry.observe(symptom_id=symptom_id, state=FaultState.CLEARED)
    assert "input_a" in registry.binding_errors
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value
    assert not registry.recovery_allowed("room_a")
    assert registry.recovery_allowed("room_b")
    assert registry.snapshot()["affected"][0]["cause_state"] == "invalid_binding"


def test_unmapped_diagnostic_does_not_block_unrelated_recovery() -> None:
    original = _registry()
    registry = DegradationRegistry(
        original._symptoms,
        original._faults,
        (
            DiagnosticBinding("input_a", (
                DegradationTarget("room_a", "temperature", "room_a", RestrictionEffect.EVALUATION),
            )),
            DiagnosticBinding("external_only", (), external_only=True),
        ),
        isolate_invalid=True,
    )
    for symptom_id in original._symptoms:
        registry.observe(symptom_id=symptom_id, state=FaultState.CLEARED)
    assert registry.binding_errors == {"provider_a": "Missing degradation declaration"}
    assert registry.snapshot()["state"] == CoverageState.UNKNOWN.value
    assert registry.recovery_allowed("room_b")


def test_recovery_manager_blocks_only_dependent_actuator_and_withdraws_proposal() -> None:
    registry = _registry()
    for symptom_id in registry._symptoms:
        registry.observe(symptom_id=symptom_id, state=FaultState.CLEARED)
    manager = RecoveryManager(
        Mock(), Mock(), {}, Mock(), Mock(), Mock(), degradation=registry
    )
    manager._is_dry_test_failed = Mock(return_value=False)
    manager._isRecoveryConflict = Mock(return_value=False)
    manager._recovery_clear_by_name = Mock()
    manager._proposals = {
        "room_a": {
            "status": "AWAITING_CONFIRMATION", "source": "SafetyComponent"
        },
        "room_b": {
            "status": "AWAITING_CONFIRMATION", "source": "SafetyComponent"
        },
    }
    result = RecoveryResult({}, {"cover.example": "closed"}, [])
    registry.observe(symptom_id="input_a", state=FaultState.SET)
    manager.invalidate_restricted_proposals()

    assert not manager._validate_recovery_action(
        SimpleNamespace(name="room_a"), result
    )
    assert manager._validate_recovery_action(
        SimpleNamespace(name="room_b"), result
    )
    manager._recovery_clear_by_name.assert_called_once_with("room_a")
