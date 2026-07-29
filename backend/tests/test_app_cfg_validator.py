import copy

import pytest

from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
    _collect_entity_ids,
    _validate_entity_existence,
)
from components.safetycomponents.temperature.schema import COMPONENT_NAME as TEMP_COMPONENT_NAME
from components.safetycomponents.safety_doors.schema import (
    COMPONENT_NAME as SAFETY_DOORS_COMPONENT_NAME,
)


def test_validate_app_cfg_normalizes_temperature_component(app_config_valid):
    validated = AppCfgValidator.validate(app_config_valid)

    temperature_cfg = validated["user_config"]["safety_components"]["TemperatureComponent"]
    assert isinstance(temperature_cfg, list)
    assert {"Office", "Kitchen"} == {list(room.keys())[0] for room in temperature_cfg}

    office_cfg = next(room["Office"] for room in temperature_cfg if "Office" in room)
    assert office_cfg["CAL_LOW_TEMP_THRESHOLD"] == 18.0
    assert office_cfg["CAL_FORECAST_TIMESPAN"] == 2.0


def test_validate_app_cfg_rejects_configuration_without_enabled_components(
    app_config_valid,
):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["components_enabled"]["TemperatureComponent"] = False

    with pytest.raises(
        AppCfgValidationError,
        match="must enable at least one component",
    ):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_applies_safe_mqtt_defaults(app_config_valid):
    validated = AppCfgValidator.validate(app_config_valid)

    mqtt_config = validated["user_config"]["mqtt"]
    assert mqtt_config["retain_discovery"] is True
    assert mqtt_config["retain_state"] is False
    assert mqtt_config["availability_topic"] == "safety_component/status"
    assert mqtt_config["heartbeat_seconds"] == 60
    assert mqtt_config["expire_after"] == 180


def test_validate_app_cfg_normalizes_safety_doors_component(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["components_enabled"][SAFETY_DOORS_COMPONENT_NAME] = True
    cfg["user_config"]["safety_components"][SAFETY_DOORS_COMPONENT_NAME] = {
        "defaults": {"timeout_seconds": 120},
        "doors": {
            "GarageGate": {
                "entity_id": "binary_sensor.garage_gate",
            },
            "EntranceDoor": {
                "entity_id": "binary_sensor.entrance_door",
                "timeout_seconds": 30,
            },
        },
    }

    validated = AppCfgValidator.validate(cfg)
    doors = validated["user_config"]["safety_components"][
        SAFETY_DOORS_COMPONENT_NAME
    ]

    assert doors == [
        {
            "GarageGate": {
                "entity_id": "binary_sensor.garage_gate",
                "timeout_seconds": 120,
            }
        },
        {
            "EntranceDoor": {
                "entity_id": "binary_sensor.entrance_door",
                "timeout_seconds": 30,
            }
        },
    ]


def test_validate_app_cfg_rejects_safety_doors_without_entries(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["components_enabled"][SAFETY_DOORS_COMPONENT_NAME] = True
    cfg["user_config"]["safety_components"][SAFETY_DOORS_COMPONENT_NAME] = {
        "doors": {}
    }

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


@pytest.mark.parametrize(
    "mqtt_config",
    [
        {"qos": 4},
        {"retain_discovery": False},
        {"base_topic": "safety/#"},
        {"retain_state": "false"},
        {"heartbeat_seconds": 0, "expire_after": 180},
    ],
)
def test_validate_app_cfg_rejects_invalid_mqtt_settings(
    app_config_valid, mqtt_config
):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["mqtt"] = mqtt_config

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_requires_thresholds(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    component_cfg = cfg["user_config"]["safety_components"]["TemperatureComponent"]
    component_cfg["defaults"] = None
    component_cfg["rooms"]["Office"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Office"].pop("CAL_FORECAST_TIMESPAN")

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_rejects_non_cover_temperature_actuator(
    app_config_valid,
):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["safety_components"]["TemperatureComponent"]["rooms"][
        "Office"
    ]["actuator"] = "switch.window_relay"

    with pytest.raises(AppCfgValidationError, match="cover entity"):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_rejects_removed_dashboard_notification_config(
    app_config_valid,
):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["notification"][
        "dashboard_1_entity"
    ] = "sensor.safety_dashboard_emergency"

    with pytest.raises(AppCfgValidationError, match="Unknown keys.*dashboard_1_entity"):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_uses_defaults_when_room_thresholds_missing(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    component_cfg = cfg["user_config"]["safety_components"]["TemperatureComponent"]
    defaults = component_cfg["defaults"]
    component_cfg["rooms"]["Office"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Office"].pop("CAL_HIGH_TEMP_THRESHOLD")
    component_cfg["rooms"]["Office"].pop("CAL_FORECAST_TIMESPAN")
    component_cfg["rooms"]["Kitchen"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Kitchen"].pop("CAL_HIGH_TEMP_THRESHOLD")
    component_cfg["rooms"]["Kitchen"].pop("CAL_FORECAST_TIMESPAN")

    validated = AppCfgValidator.validate(cfg)

    temperature_cfg = validated["user_config"]["safety_components"]["TemperatureComponent"]
    office_cfg = next(room["Office"] for room in temperature_cfg if "Office" in room)
    kitchen_cfg = next(room["Kitchen"] for room in temperature_cfg if "Kitchen" in room)

    assert office_cfg["CAL_LOW_TEMP_THRESHOLD"] == defaults["CAL_LOW_TEMP_THRESHOLD"]
    assert office_cfg["CAL_HIGH_TEMP_THRESHOLD"] == defaults["CAL_HIGH_TEMP_THRESHOLD"]
    assert office_cfg["CAL_FORECAST_TIMESPAN"] == defaults["CAL_FORECAST_TIMESPAN"]
    assert kitchen_cfg["CAL_LOW_TEMP_THRESHOLD"] == defaults["CAL_LOW_TEMP_THRESHOLD"]
    assert (
        kitchen_cfg["CAL_HIGH_TEMP_THRESHOLD"]
        == defaults["CAL_HIGH_TEMP_THRESHOLD"]
    )
    assert kitchen_cfg["CAL_FORECAST_TIMESPAN"] == defaults["CAL_FORECAST_TIMESPAN"]


def test_validate_app_cfg_rejects_unknown_keys_when_strict(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["app_config"]["unknown_key"] = 1
    cfg["user_config"]["unknown_key"] = "bad"

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_allows_unknown_keys_when_not_strict(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["app_config"]["strict_validation"] = False
    cfg["app_config"]["unknown_key"] = 1
    cfg["user_config"]["unknown_key"] = "ok"

    AppCfgValidator.validate(cfg)


def test_validate_app_cfg_rejects_invalid_entity_id_syntax(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["common_entities"]["outside_temp"] = "badentity"

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_rejects_missing_entities_when_enabled(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["app_config"]["validation"]["validate_entity_existence"] = True

    class DummyHass:
        def get_state(self, *_args, **_kwargs):
            return None

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg, hass=DummyHass())


def test_validate_app_cfg_rejects_unsupported_config_version(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["app_config"]["config_version"] = 99

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_requires_user_config(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg.pop("user_config")

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_warns_when_no_hass_and_validate_existence(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["app_config"]["validation"]["validate_entity_existence"] = True
    messages = []

    def log_no_level(message):
        messages.append(message)

    AppCfgValidator.validate(cfg, log=log_no_level)
    assert any("validate_entity_existence" in msg for msg in messages)


def test_collect_entity_ids_skips_invalid_room_entries():
    runtime_cfg = {
        "user_config": {
            "common_entities": {},
            "notification": {},
            "safety_components": {
                TEMP_COMPONENT_NAME: [
                    "invalid",
                    {"RoomA": "not-a-dict"},
                    {"RoomB": {"temperature_sensor": "sensor.test"}},
                ]
            },
        }
    }
    entity_ids = _collect_entity_ids(runtime_cfg)
    assert ("user_config.safety_components.TemperatureComponent.RoomB.temperature_sensor", "sensor.test") in entity_ids


def test_validate_entity_existence_handles_exception():
    class BoomHass:
        def get_state(self, _entity_id):
            raise RuntimeError("boom")

    missing = _validate_entity_existence(BoomHass(), [("path", "sensor.bad")])
    assert "sensor.bad" in missing[0]


def test_validate_app_cfg_keeps_unknown_component_config(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["components_enabled"]["CustomComponent"] = True
    cfg["user_config"]["safety_components"]["CustomComponent"] = {"custom": True}

    validated = AppCfgValidator.validate(cfg)
    assert validated["user_config"]["safety_components"]["CustomComponent"] == {
        "custom": True
    }
