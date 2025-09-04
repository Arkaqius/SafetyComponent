import pytest
# mypy: ignore-errors

@pytest.fixture(scope="module")
def app_config_valid():
    return {
        "module": "SafetyFunctions",
        "class": "SafetyFunctions",
        "log_level": "DEBUG",
        "app_config": {
            "faults": {
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
        },
        "user_config": {
            "notification": {"light_entity": "light.warning_light"},
            "common_entities": {"outside_temp": "sensor.dom_temperature"},
            "safety_components": {
                "TemperatureComponent": [
                    {
                        "Office": {
                            "CAL_LOW_TEMP_THRESHOLD": 18.0,
                            "CAL_FORECAST_TIMESPAN": 2.0,  # hours # app cfg
                            "temperature_sensor": "sensor.office_temperature",
                            "temperature_sensor_rate": "sensor.office_temperature_rate",  # sampling_rate = 1min
                            "window_sensor": "sensor.office_window_contact_contact",
                        },
                        "Kitchen": {
                            "CAL_LOW_TEMP_THRESHOLD": 18.0,
                            "CAL_FORECAST_TIMESPAN": 2.0,  # hours # app cfg
                            "temperature_sensor": "sensor.kitchen_temperature",
                            "temperature_sensor_rate": "sensor.kitchen_temperature_rate",  # sampling_rate = 1min
                            "window_sensor": "sensor.kitchen_window_contact_contact",
                        },
                    }
                ]
            },
        },
    }


@pytest.fixture(scope="module")
def app_config_2_faults_to_single_symptom():
    return {
        "SafetyFunctions": {
            "module": "SafetyFunctions",
            "class": "SafetyFunctions",
            "log_level": "DEBUG",
            "app_config": {
                "faults": {
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
            },
            "user_config": {
                "notification": {"light_entity": "light.warning_light"},
                "common_entities": {"outside_temp": "sensor.dom_temperature"},
                "safety_components": {
                    "TemperatureComponent": {
                        "Office": {
                            "CAL_LOW_TEMP_THRESHOLD": 18.0,
                            "CAL_FORECAST_TIMESPAN": 2.0,  # hours # app cfg
                            "temperature_sensor": "sensor.office_temperature",
                            "temperature_sensor_rate": "sensor.office_temperature_rate",  # sampling_rate = 1min
                            "window_sensor": "sensor.office_window_contact_contact",
                        }
                    }
                },
            },
        }
    }


@pytest.fixture(scope="module")
def app_config_fault_withou_smc():
    return {
        "SafetyFunctions": {
            "module": "SafetyFunctions",
            "class": "SafetyFunctions",
            "log_level": "DEBUG",
            "app_config": {
                "faults": {
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
            },
            "user_config": {
                "notification": {"light_entity": "light.warning_light"},
                "common_entities": {"outside_temp": "sensor.dom_temperature"},
                "safety_components": {
                    "TemperatureComponent": {
                        "Office": {
                            "CAL_LOW_TEMP_THRESHOLD": 18.0,
                            "CAL_FORECAST_TIMESPAN": 2.0,  # hours # app cfg
                            "temperature_sensor": "sensor.office_temperature",
                            "temperature_sensor_rate": "sensor.office_temperature_rate",  # sampling_rate = 1min
                            "window_sensor": "sensor.office_window_contact_contact",
                        }
                    }
                },
            },
        }
    }
