import copy

import pytest

from shared.app_cfg_validator import AppCfgValidationError, AppCfgValidator


def test_validate_app_cfg_normalizes_temperature_component(app_config_valid):
    validated = AppCfgValidator.validate(app_config_valid)

    temperature_cfg = validated["user_config"]["safety_components"]["TemperatureComponent"]
    assert isinstance(temperature_cfg, list)
    assert {"Office", "Kitchen"} == {list(room.keys())[0] for room in temperature_cfg}

    office_cfg = next(room["Office"] for room in temperature_cfg if "Office" in room)
    assert office_cfg["CAL_LOW_TEMP_THRESHOLD"] == 18.0
    assert office_cfg["CAL_FORECAST_TIMESPAN"] == 2.0


def test_validate_app_cfg_filters_disabled_components(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    cfg["user_config"]["components_enabled"]["TemperatureComponent"] = False

    validated = AppCfgValidator.validate(cfg)

    assert "TemperatureComponent" not in validated["user_config"]["safety_components"]


def test_validate_app_cfg_requires_thresholds(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    component_cfg = cfg["user_config"]["safety_components"]["TemperatureComponent"]
    component_cfg["defaults"] = None
    component_cfg["rooms"]["Office"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Office"].pop("CAL_FORECAST_TIMESPAN")

    with pytest.raises(AppCfgValidationError):
        AppCfgValidator.validate(cfg)


def test_validate_app_cfg_uses_defaults_when_room_thresholds_missing(app_config_valid):
    cfg = copy.deepcopy(app_config_valid)
    component_cfg = cfg["user_config"]["safety_components"]["TemperatureComponent"]
    defaults = component_cfg["defaults"]
    component_cfg["rooms"]["Office"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Office"].pop("CAL_FORECAST_TIMESPAN")
    component_cfg["rooms"]["Kitchen"].pop("CAL_LOW_TEMP_THRESHOLD")
    component_cfg["rooms"]["Kitchen"].pop("CAL_FORECAST_TIMESPAN")

    validated = AppCfgValidator.validate(cfg)

    temperature_cfg = validated["user_config"]["safety_components"]["TemperatureComponent"]
    office_cfg = next(room["Office"] for room in temperature_cfg if "Office" in room)
    kitchen_cfg = next(room["Kitchen"] for room in temperature_cfg if "Kitchen" in room)

    assert office_cfg["CAL_LOW_TEMP_THRESHOLD"] == defaults["CAL_LOW_TEMP_THRESHOLD"]
    assert office_cfg["CAL_FORECAST_TIMESPAN"] == defaults["CAL_FORECAST_TIMESPAN"]
    assert kitchen_cfg["CAL_LOW_TEMP_THRESHOLD"] == defaults["CAL_LOW_TEMP_THRESHOLD"]
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
