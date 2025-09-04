"""
This module provides utilities for loading fault and symptom configurations from dictionaries, typically derived from YAML configuration files.
It supports getting Fault and symptom objects, which are essential components of the safety management system within a Home Assistant environment.
These utilities facilitate the dynamic setup of safety mechanisms based on external configurations.
"""

from shared.fault_manager import Fault


def get_faults(faults_dict: dict) -> dict[str, Fault]:
    """
    Parses a dictionary of fault configurations and initializes Fault objects for each.

    Each fault configuration must include 'related_sms' (related safety mechanisms) and
    a 'level' level. The function creates a Fault object for each entry and collects them
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
            fault_name, fault_data["related_sms"], fault_data["level"]
        )
    return ret_val
