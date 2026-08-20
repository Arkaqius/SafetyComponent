"""Validation tests for the notification delivery configuration contract."""

from __future__ import annotations

import pytest

from components.notification_manager.schema import validate_notification_config


def test_defaults_use_explicit_all_phones_and_hakit_url() -> None:
    config = validate_notification_config({})

    assert config["mobile"]["services"] == ["notify/all_phones"]
    assert config["mobile"]["default_url"] == ("https://ha.kojbito.org/5c36e1c9_hakit")
    assert set(config["mobile"]["profiles"]) == {1, 2, 3}


def test_ambiguous_notify_service_is_rejected() -> None:
    with pytest.raises(ValueError, match="notify/notify is ambiguous"):
        validate_notification_config({"mobile": {"services": ["notify/notify"]}})


def test_dot_notation_service_is_rejected() -> None:
    with pytest.raises(ValueError, match="domain/service format"):
        validate_notification_config(
            {"mobile": {"services": ["notify.mobile_app_phone"]}}
        )


def test_legacy_local_bindings_are_normalized_without_leaking_to_runtime_root() -> None:
    config = validate_notification_config(
        {"light_entity": "light.warning", "alarm_entity": "alarm_control_panel.home"}
    )

    assert config["local"] == {
        "light_entity": "light.warning",
        "alarm_entity": "alarm_control_panel.home",
    }
    assert "light_entity" not in config
    assert "alarm_entity" not in config


def test_strict_validation_rejects_unknown_notification_keys() -> None:
    with pytest.raises(ValueError, match="Unknown keys.*phone_notify_service"):
        validate_notification_config(
            {"phone_notify_service": "notify/all_phones"},
            strict_validation=True,
        )


def test_critical_sound_requires_critical_interruption_profile() -> None:
    config = validate_notification_config({})
    config["mobile"]["profiles"][1]["ios_critical_sound"] = True

    with pytest.raises(ValueError, match="requires ios_interruption_level=critical"):
        validate_notification_config(config)


def test_retry_max_delay_cannot_be_shorter_than_base_delay() -> None:
    with pytest.raises(ValueError, match="max_delay_seconds"):
        validate_notification_config(
            {"retry": {"base_delay_seconds": 10, "max_delay_seconds": 5}}
        )
