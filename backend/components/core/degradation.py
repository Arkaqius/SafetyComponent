"""Compile diagnostic-to-hazard bindings and track scoped coverage loss.

The registry keeps evidence for each diagnostic contributor independently. A
diagnostic clear restores a capability only after every cause on that target
has valid clear evidence; it never clears the hazard fault itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping

from components.core.fault_state_policy import FaultCategory
from components.core.types_common import Fault, FaultState, Symptom

_PROVIDER_FOR_CAPABILITY = {
    "WeatherPointModel": "OpenMeteoWeatherApiComponent",
    "OfficialWeatherWarnings": "ImgwWarningsApiComponent",
    "OutdoorAirQuality": "OpenMeteoAirQualityApiComponent",
}


class CoverageState(str, Enum):
    """Coverage of the installed H-fault baseline, independent of severity."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class RestrictionEffect(str, Enum):
    """Which part of an H capability a dependency can restrict."""

    EVALUATION = "evaluation"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class DegradationTarget:
    """One exact installed H symptom affected by a diagnostic contributor."""

    symptom_id: str
    capability: str
    subject: str
    effect: RestrictionEffect


@dataclass(frozen=True)
class DiagnosticBinding:
    """A D symptom and its explicit H targets, or an external-only declaration."""

    symptom_id: str
    targets: tuple[DegradationTarget, ...]
    external_only: bool = False
    error: str | None = None


class DegradationRegistry:
    """Validate bindings, retain independent causes, and derive coverage."""

    def __init__(
        self,
        symptoms: Mapping[str, Symptom],
        faults: Mapping[str, Fault],
        bindings: Iterable[DiagnosticBinding],
        *,
        on_change: Callable[[], None] | None = None,
        isolate_invalid: bool = False,
    ) -> None:
        self._symptoms = symptoms
        self._faults = faults
        self._on_change = on_change
        self._owners: dict[str, str] = {}
        for fault in faults.values():
            for symptom_id in fault.related_symptom_ids:
                self._bind_owner(symptom_id, fault.name)
            for symptom_id, symptom in symptoms.items():
                if symptom.sm_name in fault.related_symptoms and not fault.related_symptom_ids:
                    self._bind_owner(symptom_id, fault.name)
        self._bindings: dict[str, DiagnosticBinding] = {}
        self._rejected: dict[str, tuple[DegradationTarget, ...]] = {}
        self._binding_errors: dict[str, str] = {}
        self._baseline: set[str] = {
            symptom_id for symptom_id, owner in self._owners.items()
            if faults[owner].category == FaultCategory.H
        }
        self._evidence: dict[str, bool | None] = {
            symptom_id: None for symptom_id in symptoms
        }
        self._exclusions: dict[str, str] = {}
        self._requires_reevaluation: set[tuple[str, str]] = set()
        for binding in bindings:
            if binding.symptom_id in self._binding_errors:
                self._reject(binding, f"Duplicate D binding: {binding.symptom_id}")
                if not isolate_invalid:
                    raise ValueError(self._binding_errors[binding.symptom_id])
                continue
            try:
                self._install(binding)
            except ValueError as exc:
                if not isolate_invalid:
                    raise
                self._reject(binding, str(exc))
        missing = {
            symptom_id for symptom_id, owner in self._owners.items()
            if faults[owner].category == FaultCategory.D
        } - self._bindings.keys()
        if missing:
            if not isolate_invalid:
                raise ValueError("D symptoms without degradation declarations: " + ", ".join(sorted(missing)))
            for symptom_id in missing:
                if symptom_id not in self._binding_errors:
                    self._binding_errors[symptom_id] = "Missing degradation declaration"
                    self._rejected[symptom_id] = ()
        self._requires_reevaluation.update(
            (target.symptom_id, target.capability)
            for binding in self._bindings.values()
            for target in binding.targets
            if target.effect == RestrictionEffect.EVALUATION
        )

    @property
    def binding_errors(self) -> dict[str, str]:
        """Return diagnostic binding rejections for configuration reporting."""

        return dict(self._binding_errors)

    def _reject(self, binding: DiagnosticBinding, reason: str) -> None:
        """Quarantine one D declaration and its still-identifiable H targets."""

        previous = self._bindings.pop(binding.symptom_id, None)
        candidates = (*self._rejected.get(binding.symptom_id, ()),
                      *(previous.targets if previous else ()), *binding.targets)
        self._rejected[binding.symptom_id] = tuple(dict.fromkeys(
            target for target in candidates if target.symptom_id in self._baseline
        ))
        self._binding_errors[binding.symptom_id] = reason

    def _bind_owner(self, symptom_id: str, fault_name: str) -> None:
        if symptom_id not in self._symptoms:
            raise ValueError(f"Fault {fault_name} references missing symptom {symptom_id}")
        owner = self._owners.get(symptom_id)
        if owner is not None and owner != fault_name:
            raise ValueError(f"Ambiguous fault owner for {symptom_id}: {owner}, {fault_name}")
        self._owners[symptom_id] = fault_name

    def _install(self, binding: DiagnosticBinding) -> None:
        if binding.error is not None:
            raise ValueError(f"Invalid D binding {binding.symptom_id}: {binding.error}")
        if binding.symptom_id in self._bindings:
            raise ValueError(f"Duplicate D binding: {binding.symptom_id}")
        owner = self._owners.get(binding.symptom_id)
        if owner is None or self._faults[owner].category != FaultCategory.D:
            raise ValueError(f"Binding source is not an installed D symptom: {binding.symptom_id}")
        if binding.external_only == bool(binding.targets):
            raise ValueError(f"D binding needs H targets or explicit external-only scope: {binding.symptom_id}")
        if len(set(binding.targets)) != len(binding.targets):
            raise ValueError(f"Duplicate H target for {binding.symptom_id}")
        for target in binding.targets:
            if target.symptom_id not in self._baseline:
                raise ValueError(f"Missing H target {target.symptom_id} for {binding.symptom_id}")
            if not target.capability or not target.subject:
                raise ValueError(f"Incomplete H scope for {binding.symptom_id}")
        self._bindings[binding.symptom_id] = binding

    def observe(
        self,
        *,
        symptom_id: str,
        state: FaultState,
        additional_info: Mapping[str, object] | None = None,
        **_: object,
    ) -> None:
        """Apply a qualified symptom event before recovery consumers run."""

        if symptom_id not in self._evidence:
            raise ValueError(f"Unknown symptom {symptom_id}")
        if state not in (FaultState.SET, FaultState.CLEARED):
            return
        self._evidence[symptom_id] = state == FaultState.SET
        binding = self._bindings.get(symptom_id)
        if binding is not None:
            self._requires_reevaluation.update(
                (target.symptom_id, target.capability)
                for target in binding.targets
                if target.effect == RestrictionEffect.EVALUATION
            )
        elif symptom_id in self._baseline:
            source = str((additional_info or {}).get("source", ""))
            for target_id, capability in tuple(self._requires_reevaluation):
                if target_id != symptom_id or not self._source_depends_on(capability, source):
                    continue
                if any(
                    self._evidence[d_source] is not False
                    and any(
                        target.symptom_id == symptom_id
                        and target.capability == capability
                        and target.effect == RestrictionEffect.EVALUATION
                        for target in d_binding.targets
                    )
                    for d_source, d_binding in self._bindings.items()
                ):
                    continue
                self._requires_reevaluation.discard((target_id, capability))
        if self._on_change is not None:
            self._on_change()

    def mark_unavailable(self, *, symptom_id: str, **_: object) -> None:
        """Invalidate evidence without interpreting loss as a clear."""

        if symptom_id not in self._evidence:
            raise ValueError(f"Unknown symptom {symptom_id}")
        self._evidence[symptom_id] = None
        binding = self._bindings.get(symptom_id)
        if binding is not None:
            self._requires_reevaluation.update(
                (target.symptom_id, target.capability)
                for target in binding.targets
                if target.effect == RestrictionEffect.EVALUATION
            )
        if self._on_change is not None:
            self._on_change()

    def causes_for(
        self,
        symptom_id: str,
        effect: RestrictionEffect,
        *,
        evidence_source: str | None = None,
    ) -> tuple[str, ...]:
        """Return active and unresolved diagnostic causes for one H target."""

        if symptom_id not in self._baseline:
            return ()
        causes = []
        for source, binding in self._bindings.items():
            if self._evidence[source] is False:
                continue
            if any(
                target.symptom_id == symptom_id and target.effect == effect
                and self._source_depends_on(target.capability, evidence_source)
                for target in binding.targets
            ):
                causes.append(source)
        return tuple(sorted(causes))

    @staticmethod
    def _source_depends_on(capability: str, evidence_source: str | None) -> bool:
        provider = _PROVIDER_FOR_CAPABILITY.get(capability)
        if provider is None or not evidence_source:
            return True
        if evidence_source not in _PROVIDER_FOR_CAPABILITY.values():
            return True
        return evidence_source == provider

    def recovery_allowed(
        self, symptom_id: str, *, evidence_source: str | None = None
    ) -> bool:
        """Permit recovery only when all scoped restrictions have clear evidence."""

        return self._evidence.get(symptom_id) is not None and symptom_id not in self._exclusions and not any(
            target.symptom_id == symptom_id
            and self._source_depends_on(target.capability, evidence_source)
            for targets in self._rejected.values() for target in targets
        ) and not self.causes_for(
            symptom_id, RestrictionEffect.EVALUATION,
            evidence_source=evidence_source,
        ) and not self.causes_for(
            symptom_id, RestrictionEffect.RECOVERY,
            evidence_source=evidence_source,
        ) and not any(
            target_id == symptom_id
            and self._source_depends_on(capability, evidence_source)
            for target_id, capability in self._requires_reevaluation
        )

    def set_exclusion(self, symptom_id: str, reason: str | None) -> None:
        """Record or remove a validated baseline exclusion without shrinking it."""

        if symptom_id not in self._baseline:
            raise ValueError(f"Exclusion is not an installed H symptom: {symptom_id}")
        if reason is None:
            self._exclusions.pop(symptom_id, None)
        elif reason:
            self._exclusions[symptom_id] = reason
        else:
            raise ValueError("Exclusion reason must not be empty")
        if self._on_change is not None:
            self._on_change()

    def snapshot(self, *, limit: int | None = None) -> dict[str, object]:
        """Summarize coverage against the installed H-symptom baseline."""

        if limit is not None and limit < 1:
            raise ValueError("Coverage summary limit must be positive")

        affected: list[dict[str, str]] = []
        unresolved: list[str] = []
        for symptom_id in sorted(self._baseline):
            if (
                self._evidence[symptom_id] is None
                or any(target_id == symptom_id for target_id, _ in self._requires_reevaluation)
            ) and symptom_id not in self._exclusions:
                unresolved.append(symptom_id)
        for source, binding in sorted(self._bindings.items()):
            evidence = self._evidence[source]
            if evidence is False:
                continue
            for target in binding.targets:
                affected.append({
                    "cause": source,
                    "cause_state": "active" if evidence else "unresolved",
                    "fault": self._owners[target.symptom_id],
                    "symptom": target.symptom_id,
                    "capability": target.capability,
                    "subject": target.subject,
                    "effect": target.effect.value,
                })
        for source, targets in sorted(self._rejected.items()):
            for target in targets:
                affected.append({
                    "cause": source,
                    "cause_state": "invalid_binding",
                    "fault": self._owners[target.symptom_id],
                    "symptom": target.symptom_id,
                    "capability": target.capability,
                    "subject": target.subject,
                    "effect": target.effect.value,
                })
        if any(item["cause_state"] == "active" for item in affected):
            state = CoverageState.DEGRADED
        elif self._binding_errors or unresolved or any(
            item["cause_state"] == "unresolved" for item in affected
        ):
            state = CoverageState.UNKNOWN
        elif self._exclusions:
            state = CoverageState.PARTIAL
        else:
            state = CoverageState.FULL
        return {
            "state": state.value,
            "baseline_count": len(self._baseline),
            "unresolved_h_count": len(unresolved),
            "unresolved_h_symptoms": unresolved[:limit],
            "exclusions": dict(sorted(self._exclusions.items())),
            "binding_errors": dict(sorted(self._binding_errors.items())),
            "affected_count": len(affected),
            "affected": affected[:limit],
            "affected_omitted": max(0, len(affected) - limit) if limit is not None else 0,
        }


def compile_runtime_bindings(
    symptoms: Mapping[str, Symptom],
    monitor_bindings: Iterable[DiagnosticBinding],
) -> tuple[DiagnosticBinding, ...]:
    """Expand direct D rows against exact installed H symptom identities.

    Entity Monitor supplies Group A/B declarations. Provider and detector
    components own their own D symptoms and therefore declare their scope here.
    Unknown D owners deliberately remain unbound for strict validation.
    """

    bindings = list(monitor_bindings)
    bound = {binding.symptom_id for binding in bindings}
    for symptom_id, symptom in symptoms.items():
        if symptom_id in bound:
            continue
        if symptom.sm_name == "sm_ext_provider_unavailable":
            capability = str(symptom.parameters.get("capability", ""))
            if capability not in {
                "WeatherPointModel", "OfficialWeatherWarnings", "OutdoorAirQuality"
            }:
                bindings.append(DiagnosticBinding(
                    symptom_id, (), error=f"Unknown provider capability {capability!r}"
                ))
                continue
            mechanism = (
                "sm_ext_outdoor_air_quality_exposure"
                if capability == "OutdoorAirQuality"
                else "sm_ext_weather_exposure"
            )
            targets = tuple(
                DegradationTarget(
                    target_id, capability,
                    str(target.parameters["opening_name"]),
                    RestrictionEffect.EVALUATION,
                )
                for target_id, target in symptoms.items()
                if target.sm_name == mechanism
            )
            bindings.append(DiagnosticBinding(symptom_id, targets, external_only=not targets))
        elif symptom.sm_name == "sm_iehm_detector_health":
            detector_key = str(symptom.parameters.get("detector_key", ""))
            matches = [
                target_id for target_id, target in symptoms.items()
                if target.sm_name.startswith("sm_iehm_")
                and target.sm_name != "sm_iehm_detector_health"
                and target.parameters.get("detector_key") == detector_key
            ]
            if len(matches) != 1:
                bindings.append(DiagnosticBinding(
                    symptom_id, (),
                    error=f"Detector {detector_key} needs one installed H alarm, got {len(matches)}",
                ))
                continue
            bindings.append(DiagnosticBinding(symptom_id, (
                DegradationTarget(
                    matches[0], "detector_alarm", detector_key,
                    RestrictionEffect.EVALUATION,
                ),
            )))
        elif symptom.sm_name.startswith("sm_fsm_"):
            bindings.append(DiagnosticBinding(symptom_id, (), external_only=True))
    return tuple(bindings)
