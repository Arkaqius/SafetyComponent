import pytest

from components.faults_manager.schema import validate_faults_config
from components.notification_manager.schema import validate_notification_config


def test_faults_schema_rejects_invalid_entry():
    with pytest.raises(ValueError):
        validate_faults_config({"FaultA": {"name": "bad", "level": 0, "related_sms": []}})


def test_notification_schema_rejects_invalid_entry():
    with pytest.raises(ValueError):
        validate_notification_config({"light_entity": 123})
