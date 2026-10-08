"""Exercise retained migration with an in-memory broker and finite clock."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import migrate_mqtt_retained as migration_module
from migrate_mqtt_retained import RetainedMigration, create_client


class FakeBrokerClient:
    """Model broker replay, live deliveries, PUBACK, and deletion denial."""

    def __init__(self, clock):
        self.clock = clock
        self.retained = {
            "safety_component/state/health": b"running",
            "safety_component/attributes/health": b'{"fault":"active"}',
        }
        self.published = []
        self.subscriptions = []
        self.disconnected = False
        self.deny_delete = False
        self.granted_qos = [1, 1]
        self.network_result = 0
        self.puback = True

    def connect(self, host, port, keepalive):
        self.on_connect(self, None, {}, 0)
        return 0

    def subscribe(self, topics):
        self.subscriptions.append(topics)
        self.on_subscribe(self, None, 1, self.granted_qos)
        for topic, payload in self.retained.items():
            self.on_message(
                self, None, SimpleNamespace(topic=topic, payload=payload, retain=True)
            )
        self.on_message(self, None, SimpleNamespace(
            topic="safety_component/state/live_only", payload=b"ok", retain=False,
        ))
        return 0, 1

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        if not self.deny_delete:
            self.retained.pop(topic, None)
        return SimpleNamespace(rc=0, is_published=lambda: self.puback)

    def loop(self, timeout):
        self.clock[0] += timeout
        return self.network_result

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def broker(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(migration_module.time, "monotonic", lambda: clock[0])
    return FakeBrokerClient(clock)


def test_audit_never_publishes_and_disconnects(broker):
    original = set(broker.retained)
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    assert migration.run("local-test", 1883) == original
    assert broker.published == []
    assert broker.subscriptions == [[
        ("safety_component/state/+", 1), ("safety_component/attributes/+", 1),
    ]]
    assert broker.disconnected


def test_empty_migration_is_a_noop_and_custom_prefix_is_isolated(broker):
    broker.retained["safety_component_dev/state/health"] = b"running"
    original_production = {
        topic: payload for topic, payload in broker.retained.items()
        if not topic.startswith("safety_component_dev/")
    }
    migration = RetainedMigration(broker, "safety_component_dev", 1, 1)
    assert migration.run("local-test", 1883, apply=True) == set()
    assert broker.retained == original_production
    assert broker.published == [
        ("safety_component_dev/state/health", "", 1, True),
    ]
    broker.published.clear()
    assert migration.run("local-test", 1883, apply=True) == set()
    assert broker.published == []


def test_apply_removes_only_observed_owned_retained_topics_and_verifies(broker):
    unrelated = {
        "safety_component/status": b"online",
        "homeassistant/sensor/health/config": b"{}",
        "zigbee2mqtt/state/device": b"ok",
        "safety_component/state/health/nested": b"ok",
        "safety_component/state/invalid#": b"ok",
    }
    broker.retained.update(unrelated)
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    assert migration.run("local-test", 1883, apply=True) == set()
    assert broker.retained == unrelated
    assert broker.published == [
        ("safety_component/attributes/health", "", 1, True),
        ("safety_component/state/health", "", 1, True),
    ]
    assert len(broker.subscriptions) == 2
    assert broker.disconnected


def test_acknowledged_deletion_without_broker_removal_fails_verification(broker):
    broker.deny_delete = True
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    with pytest.raises(RuntimeError, match="remain after migration"):
        migration.run("local-test", 1883, apply=True)
    assert broker.disconnected


@pytest.mark.parametrize("failure", ["subscription", "network", "puback"])
def test_failed_operations_never_report_migration_success(broker, failure):
    if failure == "subscription":
        broker.granted_qos = [1, 128]
    elif failure == "network":
        broker.network_result = 1
    else:
        broker.puback = False
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    with pytest.raises((RuntimeError, TimeoutError)):
        migration.run("local-test", 1883, apply=True)
    if failure != "puback":
        assert broker.published == []
    assert broker.disconnected


@pytest.mark.parametrize("base_topic", ["", "/", "unsafe/#", "unsafe/+", "a//b", "a\x00b"])
def test_invalid_scope_is_rejected_before_broker_connection(broker, base_topic):
    with pytest.raises(ValueError):
        RetainedMigration(broker, base_topic, 1, 1)
    assert not broker.subscriptions


@pytest.mark.parametrize("scan_seconds, timeout", [(0, 1), (61, 1), (1, 0), (1, 61)])
def test_session_work_has_finite_time_limits(broker, scan_seconds, timeout):
    with pytest.raises(ValueError):
        RetainedMigration(broker, "safety_component", scan_seconds, timeout)


def test_diagnostic_client_has_unique_clean_authenticated_sessions(monkeypatch):
    import paho.mqtt.client as mqtt

    factory = Mock()
    monkeypatch.setattr(mqtt, "Client", factory)
    first = create_client("diagnostic-user", "test-password", tls=True)
    create_client("diagnostic-user", None, tls=False)
    first.username_pw_set.assert_any_call("diagnostic-user", "test-password")
    first.tls_set.assert_called_once()
    calls = factory.call_args_list
    assert calls[0].kwargs["client_id"] != calls[1].kwargs["client_id"]
    for call in calls:
        assert call.kwargs["clean_session"] is True
        assert call.kwargs["reconnect_on_failure"] is False
        assert call.kwargs["protocol"] == mqtt.MQTTv311


@pytest.mark.parametrize("operation", ["connection", "subscription", "publish"])
def test_immediate_mqtt_operation_failures_disconnect(broker, operation):
    if operation == "connection":
        broker.connect = lambda *args, **kwargs: 1
    elif operation == "subscription":
        broker.subscribe = lambda *args, **kwargs: (1, 1)
    else:
        broker.publish = lambda *args, **kwargs: SimpleNamespace(rc=1)
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    with pytest.raises(RuntimeError, match="failed"):
        migration.run("local-test", 1883, apply=True)
    assert broker.disconnected


def test_connection_rejection_and_unexpected_disconnect_fail(broker):
    migration = RetainedMigration(broker, "safety_component", 1, 1)
    migration._on_connect(broker, None, {}, 5)
    with pytest.raises(RuntimeError, match="rejected"):
        migration._loop(0.2)
    migration._on_disconnect(broker, None, 1)
    with pytest.raises(RuntimeError, match="disconnected"):
        migration._loop(0.2)


@pytest.mark.parametrize("apply, exit_code", [(False, 2), (True, 0)])
def test_cli_defaults_to_audit_and_requires_apply_for_deletion(
    broker, monkeypatch, apply, exit_code,
):
    monkeypatch.setenv("MQTT_USERNAME", "test-user")
    monkeypatch.setenv("MQTT_PASSWORD", "test-password")
    monkeypatch.setattr(migration_module, "create_client", lambda *args, **kwargs: broker)
    argv = ["migration", "--host", "local-test", "--scan-seconds", "1"]
    if apply:
        argv.append("--apply")
    monkeypatch.setattr(sys, "argv", argv)
    assert migration_module.main() == exit_code
    assert bool(broker.published) is apply
    assert broker.disconnected


def test_cli_requires_username_before_any_connection(monkeypatch):
    monkeypatch.delenv("MQTT_USERNAME", raising=False)
    client_factory = Mock()
    monkeypatch.setattr(migration_module, "create_client", client_factory)
    monkeypatch.setattr(sys, "argv", ["migration", "--host", "local-test"])
    with pytest.raises(SystemExit) as error:
        migration_module.main()
    assert error.value.code == 2
    client_factory.assert_not_called()


def test_cli_returns_failure_when_broker_denies_cleanup(broker, monkeypatch, capsys):
    broker.deny_delete = True
    monkeypatch.setenv("MQTT_USERNAME", "test-user")
    monkeypatch.setattr(migration_module, "create_client", lambda *args, **kwargs: broker)
    monkeypatch.setattr(sys, "argv", ["migration", "--host", "local-test", "--apply"])
    with pytest.raises(SystemExit) as error:
        migration_module.main()
    assert error.value.code == 1
    assert "remain after migration" in capsys.readouterr().err
    assert broker.disconnected
