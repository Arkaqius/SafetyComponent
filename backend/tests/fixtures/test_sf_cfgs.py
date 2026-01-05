import pytest


def _base_faults():
    return {
        "RiskyTemperature": {
            "name": "Unsafe temperature",
            "level": 2,
            "related_sms": ["sm_tc_1"],
        },
        "RiskyTemperatureForecast": {
            "name": "Unsafe temperature forecast",
            "level": 3,
            "related_sms": ["sm_tc_2"],
        },
    }


def _temperature_component_rooms():
    return {
        "Office": {
            "CAL_LOW_TEMP_THRESHOLD": 18.0,
            "CAL_FORECAST_TIMESPAN": 2.0,
            "temperature_sensor": "sensor.office_temperature",
            "temperature_sensor_rate": "sensor.office_temperature_rate",
            "window_sensor": "sensor.office_window_contact_contact",
        },
        "Kitchen": {
            "CAL_LOW_TEMP_THRESHOLD": 18.0,
            "CAL_FORECAST_TIMESPAN": 2.0,
            "temperature_sensor": "sensor.kitchen_temperature",
            "temperature_sensor_rate": "sensor.kitchen_temperature_rate",
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
                    "CAL_FORECAST_TIMESPAN": 2.0,
                },
                "rooms": _temperature_component_rooms(),
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
