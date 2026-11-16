from components.core.event_bus import EventBus
from components.core.lifecycle import LifecycleScope


def test_event_bus_orders_by_priority_and_registration():
    bus = EventBus()
    calls = []

    def handler(name, **_):
        calls.append(name)

    bus.subscribe("evt", lambda **kw: handler("second", **kw), priority=1)
    bus.subscribe("evt", lambda **kw: handler("first", **kw), priority=0)
    bus.subscribe("evt", lambda **kw: handler("third", **kw), priority=1)

    bus.publish("evt", payload=True)

    assert calls == ["first", "second", "third"]


def test_duplicate_registration_has_one_cancellable_identity():
    bus, calls = EventBus(), []
    def handler(**_):
        calls.append("once")
    first = bus.subscribe("evt", handler)
    second = bus.subscribe("evt", handler)
    assert first is second
    bus.publish("evt")
    first.cancel()
    first.cancel()
    bus.publish("evt")
    assert calls == ["once"]


def test_scope_stop_unsubscribes_and_fences_queued_handler():
    bus, calls = EventBus(), []
    scope = LifecycleScope("fixture", enabled=True)
    token = bus.subscribe("evt", lambda **_: calls.append(1), scope=scope)
    assert not token.active
    scope.start()
    bus.publish("evt")
    scope.stop()
    bus.publish("evt")
    assert calls == [1]
    assert not token.active


def test_unsubscription_during_publish_prevents_cancelled_handler():
    bus, calls = EventBus(), []
    bus.subscribe("evt", lambda **_: second.cancel())
    second = bus.subscribe("evt", lambda **_: calls.append(1))
    bus.publish("evt")
    assert not calls


def test_prerequisite_failure_still_propagates():
    import pytest

    bus, calls = EventBus(), []

    def fail():
        raise ValueError("prerequisite")

    bus.subscribe("evt", fail)
    bus.subscribe("evt", lambda: calls.append(1))
    with pytest.raises(ValueError, match="prerequisite"):
        bus.publish("evt")
    assert not calls


def test_public_unsubscribe_survives_scope_disable_and_restart():
    bus, calls = EventBus(), []
    scope = LifecycleScope("fixture", enabled=True)
    token = bus.subscribe("evt", lambda **_: calls.append(1), scope=scope)
    scope.start()
    token.cancel()
    scope.set_enabled(False)
    scope.set_enabled(True)
    scope.stop()
    scope.start()
    scope.set_enabled(True)
    bus.publish("evt")
    assert not calls
    assert scope.handle_count == 0
