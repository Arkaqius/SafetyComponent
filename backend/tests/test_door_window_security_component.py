# tests/test_door_window_security_component.py

from typing import Iterator, List

import pytest

from components.core.types_common import FaultState
from .fixtures.hass_fixture import (
    MockBehavior,
    mock_get_state,
    update_mocked_get_state,
)


def test_door_open_timeout_sets_fault(mocked_hass_app_with_door_window_component):
    """
    Test Case: Door open timeout triggers symptom and fault.
    """
    app_instance, _, __, mock_behaviors_default = (
        mocked_hass_app_with_door_window_component
    )

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("binary_sensor.front_door_contact", iter(["on"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.initialize()

    app_instance.sm_modules["DoorWindowSecurityComponent"].sm_sec_door_timeout(
        app_instance.sm_modules["DoorWindowSecurityComponent"].safety_mechanisms[
            "DoorOpenTimeoutFrontDoor"
        ]
    )

    assert (
        app_instance.fm.check_symptom("DoorOpenTimeoutFrontDoor")
        == FaultState.SET
    )
    assert app_instance.fm.check_fault("DoorOpenTimeout") == FaultState.SET


def test_window_open_ignored_when_not_gated(mocked_hass_app_with_door_window_component):
    """
    Test Case: Window open does not trigger when occupancy is not gated.
    """
    app_instance, _, __, mock_behaviors_default = (
        mocked_hass_app_with_door_window_component
    )

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.house_occupancy", iter(["Occupied"])),
        MockBehavior("binary_sensor.kitchen_window_contact", iter(["on"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.initialize()

    app_instance.sm_modules["DoorWindowSecurityComponent"].sm_sec_window_safety(
        app_instance.sm_modules["DoorWindowSecurityComponent"].safety_mechanisms[
            "WindowOpenUnsafeKitchenWindow"
        ]
    )

    assert (
        app_instance.fm.check_symptom("WindowOpenUnsafeKitchenWindow")
        != FaultState.SET
    )
    assert app_instance.fm.check_fault("WindowOpenUnsafe") != FaultState.SET


def test_window_open_sets_fault_when_gated(mocked_hass_app_with_door_window_component):
    """
    Test Case: Window open triggers when occupancy is gated.
    """
    app_instance, _, __, mock_behaviors_default = (
        mocked_hass_app_with_door_window_component
    )

    test_mock_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.house_occupancy", iter(["Unoccupied"])),
        MockBehavior("binary_sensor.kitchen_window_contact", iter(["on"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, test_mock_behaviours
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.initialize()

    app_instance.sm_modules["DoorWindowSecurityComponent"].sm_sec_window_safety(
        app_instance.sm_modules["DoorWindowSecurityComponent"].safety_mechanisms[
            "WindowOpenUnsafeKitchenWindow"
        ]
    )

    assert (
        app_instance.fm.check_symptom("WindowOpenUnsafeKitchenWindow")
        == FaultState.SET
    )
    assert app_instance.fm.check_fault("WindowOpenUnsafe") == FaultState.SET


def test_window_clears_when_occupancy_not_gated(
    mocked_hass_app_with_door_window_component,
):
    """
    Test Case: Window fault clears when occupancy exits gated state.
    """
    app_instance, _, __, mock_behaviors_default = (
        mocked_hass_app_with_door_window_component
    )

    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.initialize()

    sm = app_instance.sm_modules["DoorWindowSecurityComponent"].safety_mechanisms[
        "WindowOpenUnsafeKitchenWindow"
    ]

    set_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.house_occupancy", iter(["Unoccupied"])),
        MockBehavior("binary_sensor.kitchen_window_contact", iter(["on"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, set_behaviours
    )
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.sm_modules["DoorWindowSecurityComponent"].sm_sec_window_safety(sm)
    assert (
        app_instance.fm.check_symptom("WindowOpenUnsafeKitchenWindow")
        == FaultState.SET
    )

    reset_behaviours: List[MockBehavior[str, Iterator[str]]] = [
        MockBehavior("sensor.house_occupancy", iter(["Occupied"])),
        MockBehavior("binary_sensor.kitchen_window_contact", iter(["on"])),
    ]
    mock_behaviors_default = update_mocked_get_state(
        mock_behaviors_default, reset_behaviours
    )
    app_instance.get_state.side_effect = lambda entity_id, **kwargs: mock_get_state(
        entity_id, mock_behaviors_default
    )

    app_instance.sm_modules["DoorWindowSecurityComponent"].sm_sec_window_safety(sm)
    assert (
        app_instance.fm.check_symptom("WindowOpenUnsafeKitchenWindow")
        == FaultState.CLEARED
    )
    assert app_instance.fm.check_fault("WindowOpenUnsafe") == FaultState.CLEARED
