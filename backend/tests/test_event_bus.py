from components.core.event_bus import EventBus


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
