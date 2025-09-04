# tests/test_initialization.py

import pytest
from shared.temperature_component import TemperatureComponent
from shared.fault_manager import FaultManager
from .fixtures.hass_fixture import mock_get_state, MockBehavior  # Import utilities from conftest.py


@pytest.mark.init
@pytest.mark.positive
def test_initialize_dicts_symptom(mocked_hass_app_basic):
    app_instance, _, __ = mocked_hass_app_basic
    app_instance.initialize()

    # Assert the 'symptoms' dictionary content
    symptom = app_instance.symptoms["RiskyTemperatureOffice"]
    assert symptom.name == "RiskyTemperatureOffice"
    assert symptom.sm_name == "sm_tc_1"
    assert symptom.parameters["CAL_LOW_TEMP_THRESHOLD"] == 18.0

    # Assert the 'faults' dictionary content
    fault = app_instance.fault_dict["RiskyTemperature"]
    assert fault["name"] == "Unsafe temperature"
    assert fault["level"] == 2
    assert fault["related_sms"][0] == "sm_tc_1"

    # Assert the 'notification_cfg' dictionary content
    notification = app_instance.notification_cfg
    assert notification["light_entity"] == "light.warning_light"


def test_NotificationManager_init(mocked_hass_app_basic):
    app_instance, _, __ = mocked_hass_app_basic
    app_instance.initialize()

    assert app_instance.notify_man.hass_app is not None
    assert app_instance.notify_man.notification_config is app_instance.notification_cfg


def test_temperature_component_initialization(mocked_hass_app_with_temp_component):
    app_instance, _, __, MockTemperatureComponent , mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    assert isinstance(
        app_instance.sm_modules["TemperatureComponent"], TemperatureComponent
    )


def test_fault_manager_initialization(mocked_hass_app_with_temp_component):
    app_instance, _, __, MockTemperatureComponent , mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    assert isinstance(app_instance.fm, FaultManager)
    assert app_instance.fm.notify_interface == app_instance.notify_man.notify
    assert app_instance.fm.recovery_interface == app_instance.reco_man.recovery
    assert (
        app_instance.fm.sm_modules["TemperatureComponent"]
        == app_instance.sm_modules["TemperatureComponent"]
    )


def test_assign_fm(mocked_hass_app_with_temp_component):
    app_instance, _, __, ___ , mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    for module in app_instance.sm_modules.values():
        assert module.fault_man is app_instance.fm


def test_app_health_set_to_good_at_end_of_init(mocked_hass_app_with_temp_component):
    app_instance, _, mock_log_method, ___ , mock_behaviors_default = mocked_hass_app_with_temp_component
    app_instance.initialize()

    mock_log_method.assert_called_with("Safety app started successfully", level="DEBUG")
