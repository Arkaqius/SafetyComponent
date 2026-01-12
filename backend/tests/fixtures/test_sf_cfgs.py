import pytest


def _base_faults():
    return {
        "RiskyTemperature": {
            "name": "Unsafe temperature",
            "level": 2,
            "related_sms": ["sm_tc_1", "sm_tc_3"],
        },
        "RiskyTemperatureForecast": {
            "name": "Unsafe temperature forecast",
            "level": 3,
            "related_sms": ["sm_tc_2", "sm_tc_4"],
        },
    }


def _temperature_component_rooms():
    return {
        "Office": {
            "CAL_LOW_TEMP_THRESHOLD": 18.0,
            "CAL_HIGH_TEMP_THRESHOLD": 28.0,
            "CAL_FORECAST_TIMESPAN": 2.0,
            "temperature_sensor": "sensor.office_temperature",
            "window_sensor": "sensor.office_window_contact_contact",
        },
        "Kitchen": {
            "CAL_LOW_TEMP_THRESHOLD": 18.0,
            "CAL_HIGH_TEMP_THRESHOLD": 28.0,
            "CAL_FORECAST_TIMESPAN": 2.0,
            "temperature_sensor": "sensor.kitchen_temperature",
            "window_sensor": "sensor.kitchen_window_contact_contact",
        },
    }


def _base_user_config():
    return {
        "components_enabled": {"TemperatureComponent": True},
        "notification": {"light_entity": "light.warning_light"},
        "common_entities": {"outside_temp": "sensor.dom_temperature"},
        "safety_components": {
            "TemperatureComponent": {
                "defaults": {
                    "CAL_LOW_TEMP_THRESHOLD": 18.0,
                    "CAL_HIGH_TEMP_THRESHOLD": 28.0,
                    "CAL_FORECAST_TIMESPAN": 2.0,
                },
                "rooms": _temperature_component_rooms(),
            }
        },
    }


def _door_window_component_config():
    return {
        "occupancy_sensor": "sensor.house_occupancy",
        "defaults": {
            "T_door_close_timeout": 0,
            "T_window_close_timeout": 0,
            "T_escalate": 0,
            "T_stable": 0,
            "AutoLockEnabled": False,
            "AutoCloseWindowsEnabled": False,
            "OccupancyGateStates": ["Unoccupied", "Kids"],
        },
        "external_doors": {
            "FrontDoor": {
                "door_sensor": "binary_sensor.front_door_contact",
            }
        },
        "critical_windows": {
            "KitchenWindow": {
                "window_sensor": "binary_sensor.kitchen_window_contact",
            }
        },
    }


def _app_config_base():
    return {
        "module": "SafetyFunctions",
        "class": "SafetyFunctions",
        "log_level": "DEBUG",
        "app_config": {
            "config_version": 1,
            "strict_validation": True,
            "validation": {
                "validate_entity_id_syntax": True,
                "validate_entity_existence": False,
            },
            "faults": _base_faults(),
        },
        "user_config": _base_user_config(),
    }


@pytest.fixture(scope="module")
def app_config_valid():
    return _app_config_base()


@pytest.fixture(scope="module")
def app_config_door_window_valid():
    cfg = _app_config_base()
    cfg["app_config"]["faults"]["DoorOpenTimeout"] = {
        "name": "Door open timeout",
        "level": 2,
        "related_sms": ["sm_sec_door_timeout"],
    }
    cfg["app_config"]["faults"]["WindowOpenUnsafe"] = {
        "name": "Window open unsafe",
        "level": 2,
        "related_sms": ["sm_sec_window_safety"],
    }
    cfg["user_config"]["components_enabled"] = {
        "TemperatureComponent": False,
        "DoorWindowSecurityComponent": True,
    }
    cfg["user_config"]["safety_components"]["DoorWindowSecurityComponent"] = (
        _door_window_component_config()
    )
    return cfg


@pytest.fixture(scope="module")
def app_config_2_faults_to_single_symptom():
    cfg = _app_config_base()
    cfg["app_config"]["faults"] = {
        "RiskyTemperature": {
            "name": "Unsafe temperature",
            "level": 2,
            "related_sms": ["sm_tc_1"],
        },
        "RiskyTemperatureForecast": {
            "name": "Unsafe temperature forecast",
            "level": 3,
            "related_sms": ["sm_tc_1"],
        },
    }
    return {"SafetyFunctions": cfg}


@pytest.fixture(scope="module")
def app_config_fault_withou_smc():
    cfg = _app_config_base()
    cfg["app_config"]["faults"] = {
        "RiskyTemperature": {
            "name": "Unsafe temperature",
            "level": 2,
            "related_sms": ["sm_tc_9999"],
        },
        "RiskyTemperatureForecast": {
            "name": "Unsafe temperature forecast",
            "level": 3,
            "related_sms": ["sm_tc_9999"],
        },
    }
    return {"SafetyFunctions": cfg}
