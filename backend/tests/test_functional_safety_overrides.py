"""Installation overrides must preserve effective safety-policy invariants."""

from pathlib import Path

import pytest
import yaml

from build_app_config import compile_config
from configuration_model import FunctionalSafetyOverrides
from user_config_api import UserConfigStore

BACKEND = Path(__file__).resolve().parents[1]


def candidate(tmp_path: Path, overrides: dict) -> Path:
    """Create a fictional candidate, leaving packaged sources unchanged."""
    document = yaml.safe_load((BACKEND / "config/user_config.example.yml").read_text(encoding="utf-8"))
    document["user_config"]["installation"]["component_settings"]["functional_safety"] = overrides
    path = tmp_path / "user_config.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def compile_policy(path: Path) -> dict:
    """Return the policy actually consumed by backend monitors."""
    return compile_config(user_path=path, home_assistant_config={"latitude": 50, "longitude": 20})["SafetyFunctions"]["app_config"]["calibration"]["functional_safety"]


def test_defaults_nulls_and_effective_override(tmp_path: Path) -> None:
    packaged = yaml.safe_load((BACKEND / "config/system_config.yml").read_text(encoding="utf-8"))["calibration"]["functional_safety"]
    assert compile_policy(candidate(tmp_path, {})) == packaged
    assert compile_policy(candidate(tmp_path, {"battery_low_percent": None})) == packaged
    effective = compile_policy(candidate(tmp_path, {"battery_low_percent": 20, "backup_max_age_hours": 72, "notification_test_interval_days": 14, "cpu_recovery_percent": 0}))
    assert effective == {**packaged, "battery_low_percent": 20, "backup_max_age_hours": 72, "notification_test_interval_days": 14, "cpu_recovery_percent": 0}


@pytest.mark.parametrize("overrides", [
    {"disk_low_free_mib": 3000}, {"memory_low_available_mib": 400},
    {"memory_high_psi_percent": 4}, {"cpu_high_percent": 60},
    {"host_temperature_high_c": 65},
])
def test_partial_overrides_checked_against_inherited_recovery(tmp_path: Path, overrides: dict) -> None:
    with pytest.raises(ValueError, match="recovery"):
        compile_policy(candidate(tmp_path, overrides))


@pytest.mark.parametrize("key", ["memory_fault_level", "evaluation_interval_seconds", "resource_stale_after_seconds", "periodic_test_state_file", "battery_stale_after_seconds"])
def test_technical_fields_cannot_be_overridden(key: str) -> None:
    with pytest.raises(ValueError):
        FunctionalSafetyOverrides.model_validate({key: 99})


@pytest.mark.parametrize("overrides", [
    {"battery_low_percent": 100}, {"cpu_qualification_seconds": 0},
    {"notification_test_interval_days": 1.5}, {"detector_test_interval_days": 181},
    {"backup_max_age_hours": float("inf")}, {"memory_recovery_available_mib": float("nan")},
    {"battery_low_percent": True}, {"notification_test_interval_days": "30"},
])
def test_invalid_numeric_overrides_rejected(overrides: dict) -> None:
    with pytest.raises(ValueError):
        FunctionalSafetyOverrides.model_validate(overrides)


def test_gui_save_and_import_validate_merge_before_persisting(tmp_path: Path) -> None:
    path = candidate(tmp_path, {})
    store = UserConfigStore(user_path=path, system_path=BACKEND / "config/system_config.yml", home_assistant_config_provider=lambda: {"latitude": 50, "longitude": 20})
    before = path.read_bytes()
    read = store.read()
    source = read["user_config"]
    source["installation"]["component_settings"]["functional_safety"] = {"disk_low_free_mib": 3000}
    with pytest.raises(ValueError, match="recovery"):
        store.save(source, read["revision"])
    with pytest.raises(ValueError, match="recovery"):
        store.import_yaml(yaml.safe_dump({"user_config": source}))
    assert path.read_bytes() == before
    source["installation"]["component_settings"]["functional_safety"] = {"disk_low_free_mib": 500}
    saved = store.save(source, read["revision"])
    assert saved["restart_required"]
    assert compile_policy(path)["disk_low_free_mib"] == 500


def test_changed_test_interval_reuses_completion_without_new_pass() -> None:
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    from components.core.periodic_test_monitor import PeriodicTestMonitor
    from components.notification_manager.state_store import InMemoryNotificationStateStore

    completed = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    store = InMemoryNotificationStateStore({"version": 1, "records": {"notification_delivery": {"completed_at": completed, "outcome": "passed", "source": "operator_attestation"}}})
    before = store.load()
    for interval, expected in ((30, "overdue"), (60, "current")):
        hass, mqtt = Mock(), Mock()
        hass.localizer = None
        monitor = PeriodicTestMonitor(hass, mqtt, {"notification_delivery": True}, intervals={"notification_delivery": interval}, state_store=store)
        monitor.start()
        attrs = mqtt.publish_sensor_state.call_args.kwargs["attributes"]
        assert attrs["tests"][0]["status"] == expected
        assert attrs["tests"][0]["last_test_at"] == completed
        assert store.load() == before
        hass.call_service.assert_not_called()
