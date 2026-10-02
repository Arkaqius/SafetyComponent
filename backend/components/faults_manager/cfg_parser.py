"""
This module provides utilities for loading fault and symptom configurations from dictionaries, typically derived from YAML configuration files.
It supports getting Fault and symptom objects, which are essential components of the safety management system within a Home Assistant environment.
These utilities facilitate the dynamic setup of safety mechanisms based on external configurations.
"""

from components.core.types_common import Fault, Symptom
from components.core.fault_state_policy import FaultCategory


# Static SM families remain known even when their optional component is absent.
# Dynamic Entity Monitor and functional-safety families are validated against
# their registered live symptoms below.
KNOWN_OPTIONAL_SMS = frozenset(
    {
        "sm_tc_1",
        "sm_tc_2",
        "sm_tc_3",
        "sm_tc_4",
        "sm_safety_door_open_timeout",
        "sm_ext_weather_exposure",
        "sm_ext_outdoor_air_quality_exposure",
        "sm_ext_provider_unavailable",
        "sm_iehm_smoke",
        "sm_iehm_flammable_gas",
        "sm_iehm_carbon_monoxide",
        "sm_iehm_water_leak",
        "sm_iehm_detector_health",
    }
)


def get_faults(faults_dict: dict) -> dict[str, Fault]:
    """
    Parses a dictionary of fault configurations and initializes Fault objects for each.

    Each fault configuration must include 'related_sms' (related safety mechanisms) and
    a 'level' level. Optional 'shadows' can define other faults to suppress when set.
    The function creates a Fault object for each entry and collects them
    into a dictionary keyed by the fault name.

    Args:
        faults_dict: A dictionary with fault names as keys and dictionaries containing
                     'related_sms' and 'level' as values.

    Returns:
        A dictionary mapping fault names to initialized Fault objects.
    ret_val: dict[str, Fault] = {}
    """
    ret_val: dict[str, Fault] = {}
    for fault_name, fault_data in faults_dict.items():
        ret_val[fault_name] = Fault(
            fault_name,
            fault_data["related_sms"],
            fault_data["level"],
            fault_data.get("shadows", []),
            friendly_name=fault_data.get("name", fault_name),
            category=FaultCategory(fault_data.get("category", "H")),
            related_symptom_ids=fault_data.get("related_symptom_ids", []),
        )
    return ret_val


def validate_fault_routes(
    symptoms: dict[str, Symptom], faults: dict[str, Fault]
) -> None:
    """Validate live contributor ownership and the shadow dependency graph."""

    known_sms = KNOWN_OPTIONAL_SMS | {
        symptom.sm_name for symptom in symptoms.values()
    }
    for fault in faults.values():
        unknown_sms = sorted(set(fault.related_symptoms) - known_sms)
        if unknown_sms:
            raise ValueError(f"Unknown SM IDs in {fault.name}: {unknown_sms}")
        if len(set(fault.related_symptom_ids)) != len(fault.related_symptom_ids):
            raise ValueError(f"Duplicate contributor binding in {fault.name}")
        for symptom_id in fault.related_symptom_ids:
            symptom = symptoms.get(symptom_id)
            if symptom is None or symptom.sm_name not in fault.related_symptoms:
                raise ValueError(
                    f"Invalid contributor binding {symptom_id} in {fault.name}"
                )
        for shadow in fault.shadows:
            if shadow not in faults or shadow == fault.name:
                raise ValueError(f"Invalid shadow target {shadow} in {fault.name}")

    for symptom_id, symptom in symptoms.items():
        owners = [
            fault.name
            for fault in faults.values()
            if (
                symptom_id in fault.related_symptom_ids
                if fault.related_symptom_ids
                else symptom.sm_name in fault.related_symptoms
            )
        ]
        if len(owners) != 1:
            raise ValueError(
                f"Expected one fault owner for {symptom_id}, got {owners}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise ValueError(f"Shadow cycle involving {name}")
        if name in visited:
            return
        visiting.add(name)
        for target in faults[name].shadows:
            visit(target)
        visiting.remove(name)
        visited.add(name)

    for fault_name in faults:
        visit(fault_name)
