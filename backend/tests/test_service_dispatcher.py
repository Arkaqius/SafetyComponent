"""Bounded broker regressions with deterministic clocks and no household calls."""

import pytest

from components.core.service_dispatcher import (
    Admission, CompletionStatus, Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher,
)
from safety_lifecycle_support import CallbackServiceAdapter, LifecycleHass


def dispatcher(names=("notify/fixture",), *, registry=None):
    app, adapter = LifecycleHass(), CallbackServiceAdapter()
    app.call_service = adapter.call_service
    broker = ServiceDispatcher(
        app, [ResourceSpec(name, Lane.MOBILE, frozenset({name})) for name in names],
        clock=app.clock, registry=registry or ProcessLeaseRegistry(),
    )
    broker.start()
    return broker, app, adapter


def intent(broker, *, resource="notify/fixture", revision=1, tag="alarm", deadline=30, payload=None):
    return broker.make_intent(
        resource=resource, service=resource, payload=payload or {"message": "Fixture"},
        tag=tag, revision=revision, deadline_at=deadline,
    )


def test_lease_precedes_immediate_callback_and_owner_alone_applies_completion():
    broker, _, adapter = dispatcher()
    adapter.mode, adapter.result = "immediate", {"success": True, "result": None}
    completed = []
    assert broker.enqueue(intent(broker), on_complete=completed.append) == Admission.QUEUED
    broker.tick()
    assert broker.registry.lease_count == 1
    assert not completed
    broker.tick()
    assert completed[0].status == CompletionStatus.ACCEPTED
    assert broker.registry.lease_count == 0


@pytest.mark.parametrize("response", [None, {}, {"success": 1}, {"success": "true"}, {"success": False}])
def test_only_explicit_boolean_success_can_be_accepted(response):
    broker, _, adapter = dispatcher()
    adapter.mode, adapter.result = "immediate", response
    completed = []
    broker.enqueue(intent(broker), on_complete=completed.append)
    broker.tick()
    broker.tick()
    assert completed[0].status != CompletionStatus.ACCEPTED


def test_stalled_resource_does_not_block_healthy_target_or_release_on_timeout():
    broker, app, adapter = dispatcher(("notify/stalled", "notify/healthy"))
    completed = []
    broker.enqueue(intent(broker, resource="notify/stalled"), on_complete=completed.append)
    broker.enqueue(intent(broker, resource="notify/healthy"), on_complete=completed.append)
    broker.tick()
    adapter.complete(1, {"success": True})
    broker.tick()
    assert len(completed) == 1 and completed[0].resource == "notify/healthy"
    app.clock.advance(31)
    broker.tick()
    assert broker.registry.lease_count == 1
    assert broker.registry.quarantined_count == 1
    assert broker.deadline_misses == 1
    broker.enqueue(intent(broker, resource="notify/stalled", revision=2, deadline=100))
    broker.enqueue(intent(broker, resource="notify/healthy", revision=2, deadline=100))
    broker.tick()
    assert [service for service, _ in adapter.calls] == ["notify/stalled", "notify/healthy", "notify/healthy"]


def test_process_credits_include_queued_completions_and_reserve_independent_lanes():
    app, adapter, registry = LifecycleHass(), CallbackServiceAdapter(), ProcessLeaseRegistry()
    app.call_service = adapter.call_service
    adapter.mode, adapter.result = "immediate", {"success": True}
    specs = [ResourceSpec(f"notify/p{n}", Lane.MOBILE, frozenset({f"notify/p{n}"})) for n in range(61)]
    specs += [ResourceSpec("mqtt", Lane.MQTT, frozenset({"mqtt/publish"})),
              ResourceSpec("light.fixture", Lane.LOCAL, frozenset({"light/turn_on"})),
              ResourceSpec("alarm.fixture", Lane.LOCAL, frozenset({"alarm/trigger"})),
              ResourceSpec("cover.fixture", Lane.RECOVERY, frozenset({"cover/close_cover"}))]
    broker = ServiceDispatcher(app, specs, clock=app.clock, registry=registry)
    broker.start()
    for spec in specs:
        broker.enqueue(broker.make_intent(resource=spec.key, service=next(iter(spec.services)),
                                         payload={}, tag="fixture", revision=1, deadline_at=30))
    broker.tick()
    assert registry.lease_count == registry.completion_count == 64
    assert len(adapter.calls) == 64
    assert sum(service.startswith("notify/") for service, _ in adapter.calls) == 60
    assert "mqtt/publish" in [service for service, _ in adapter.calls]
    broker.tick()
    assert registry.lease_count == 1
    assert len(adapter.calls) == 65


def test_queue_payload_and_resource_limits_reject_without_false_delivery():
    broker, _, _ = dispatcher()
    assert broker.enqueue(intent(broker, resource="notify/not-allowed")) == Admission.REJECTED
    assert broker.enqueue(intent(broker, payload={"message": "x" * 65536})) == Admission.REJECTED
    for index in range(1024):
        assert broker.enqueue(intent(broker, tag=f"tag{index}")) == Admission.QUEUED
    assert broker.enqueue(intent(broker, tag="overflow")) == Admission.OVERLOADED
    assert broker.pending_count == 1024


def test_reload_does_not_replace_unresolved_lease_and_old_result_cannot_update_new_owner():
    registry = ProcessLeaseRegistry()
    old, _, adapter = dispatcher(registry=registry)
    old_result, new_result = [], []
    old.enqueue(intent(old), on_complete=old_result.append)
    old.tick()
    old.stop()
    new, _, new_adapter = dispatcher(registry=registry)
    new_adapter.mode, new_adapter.result = "immediate", {"success": True}
    new.enqueue(intent(new), on_complete=new_result.append)
    new.tick()
    assert not new_adapter.calls and registry.lease_count == 1
    adapter.complete(0, {"success": True})
    new.tick()
    new.tick()
    assert not old_result
    assert len(new_result) == 1
    assert registry.lease_count == 0


def test_duplicate_completion_and_superseded_clear_do_not_overtake_new_set():
    broker, _, adapter = dispatcher()
    adapter.mode, adapter.result = "duplicate", {"success": True}
    completed = []
    broker.enqueue(intent(broker, revision=1, payload={"message": "clear_notification"}), on_complete=completed.append)
    broker.enqueue(intent(broker, revision=2, payload={"message": "ALARM"}), on_complete=completed.append)
    broker.tick()
    broker.tick()
    assert len(completed) == len(adapter.calls) == 1
    assert adapter.calls[0][1]["message"] == "ALARM"


def test_coalescing_keeps_absolute_deadline_and_rechecks_authorization_at_dispatch():
    broker, app, adapter = dispatcher()
    completed = []
    broker.enqueue(intent(broker, deadline=10), on_complete=completed.append)
    app.clock.advance(2)
    broker.enqueue(intent(broker, revision=2, deadline=100), on_complete=completed.append)
    app.clock.advance(9)
    broker.tick()
    assert completed[0].status == CompletionStatus.DEADLINE_MISSED
    assert not adapter.calls
    broker.enqueue(intent(broker, revision=3, deadline=100), before_dispatch=lambda _: False,
                   on_complete=completed.append)
    broker.tick()
    assert completed[-1].status == CompletionStatus.CANCELLED
    assert not adapter.calls


def test_dispatch_gate_can_stop_owner_without_dispatch_or_key_error():
    broker, _, adapter = dispatcher()

    def stop(_):
        broker.stop()
        return True

    broker.enqueue(intent(broker), before_dispatch=stop)
    broker.tick()
    assert not adapter.calls
    assert not broker.pending_count


def test_dispatch_gate_cannot_submit_old_clear_after_new_set_is_queued():
    broker, _, adapter = dispatcher()

    def supersede(_):
        broker.enqueue(intent(broker, revision=2, payload={"message": "ALARM"}))
        return True

    broker.enqueue(intent(broker, payload={"message": "clear_notification"}), before_dispatch=supersede)
    broker.tick()
    assert not adapter.calls
    broker.tick()
    assert adapter.calls[0][1]["message"] == "ALARM"


def test_malformed_numbers_payload_and_completion_never_become_acceptance():
    from dataclasses import replace

    broker, _, adapter = dispatcher()
    current = intent(broker)
    for malformed in (
        replace(current, deadline_at=float("nan")), replace(current, revision=True),
        replace(current, payload_json='{"value": NaN}'),
        replace(current, deadline_at="wrong"),
    ):
        assert broker.enqueue(malformed) == Admission.REJECTED
    completed = []
    adapter.mode, adapter.result = "immediate", {"success": False, "error": "ą" * 10000}
    broker.enqueue(current, on_complete=completed.append)
    broker.tick()
    broker.tick()
    assert len(completed[0].error.encode("utf-8")) <= 512


def test_rapid_completions_reuse_only_owner_drained_credits():
    broker, _, adapter = dispatcher()
    adapter.mode, adapter.result = "immediate", {"success": True}
    completed = []
    for revision in range(1, 1001):
        broker.enqueue(intent(broker, revision=revision), on_complete=completed.append)
        broker.tick()
        assert broker.registry.lease_count == broker.registry.completion_count == 1
    broker.tick()
    # Superseded results may release credit but cannot acknowledge newer content.
    assert len(completed) == 1
    assert len(adapter.calls) == 1000


def test_repeated_reloads_retain_unresolved_resources_with_fixed_credit_limit():
    registry = ProcessLeaseRegistry()
    for number in range(70):
        resource = f"notify/retired{number}"
        broker, _, _ = dispatcher((resource,), registry=registry)
        broker.enqueue(intent(broker, resource=resource))
        broker.tick()
        broker.stop()
        assert registry.lease_count <= 60
    assert registry.lease_count == 60


def test_process_registry_identity_survives_module_reload():
    import importlib
    from components.core import service_dispatcher

    before = service_dispatcher.get_process_registry()
    importlib.reload(service_dispatcher)
    assert service_dispatcher.get_process_registry() is before


def test_total_pending_byte_limit_is_independent_of_record_count() -> None:
    broker, _, adapter = dispatcher()
    admitted = 0
    for index in range(100):
        result = broker.enqueue(intent(broker, tag=f"large{index}", payload={"message": "x" * 60000}))
        if result == Admission.OVERLOADED:
            break
        assert result == Admission.QUEUED
        admitted += 1
    assert 1 < admitted < 100
    assert broker.pending_count == admitted
    assert not adapter.calls


def test_completion_normalization_error_still_uses_its_reserved_mailbox_slot() -> None:
    class BrokenResult(dict):
        def get(self, *_args, **_kwargs):
            raise RuntimeError("malformed completion mapping")

    broker, _, adapter = dispatcher()
    received = []
    broker.enqueue(intent(broker), on_complete=received.append)
    broker.tick()
    adapter.complete(0, BrokenResult())
    assert broker.registry.completion_count == 1
    broker.tick()
    assert received[0].status == CompletionStatus.UNKNOWN
    assert broker.registry.lease_count == 0


def test_exact_deadline_reports_unknown_without_releasing_lease_and_late_acceptance_keeps_miss() -> None:
    broker, app, adapter = dispatcher()
    received, expired = [], []
    broker.enqueue(intent(broker, deadline=10), on_complete=received.append, on_deadline=expired.append)
    broker.tick()
    app.clock.advance(10)
    broker.tick()
    assert len(expired) == 1 and expired[0].deadline_missed
    assert broker.registry.lease_count == 1
    assert not received
    app.clock.advance(1)
    adapter.complete(0, {"success": True})
    broker.tick()
    assert received[0].status == CompletionStatus.ACCEPTED
    assert received[0].deadline_missed
    assert broker.deadline_misses == 1


def test_already_issued_clear_cannot_acknowledge_a_newer_alarm() -> None:
    broker, _, adapter = dispatcher()
    received = []
    broker.enqueue(intent(broker, payload={"message": "clear_notification"}), on_complete=received.append)
    broker.tick()
    broker.enqueue(intent(broker, revision=2, payload={"message": "ALARM"}), on_complete=received.append)
    adapter.complete(0, {"success": True})
    broker.tick()
    assert not received
    adapter.complete(1, {"success": True})
    broker.tick()
    assert len(received) == 1 and received[0].revision == 2


def test_request_payload_is_copied_and_one_completion_observer_cannot_block_others() -> None:
    broker, _, adapter = dispatcher(("notify/a", "notify/b"))
    adapter.mode, adapter.result = "immediate", {"success": True}
    payload = {"message": "Fixture", "data": {"tag": "original"}}
    first = intent(broker, resource="notify/a", payload=payload)
    payload["data"]["tag"] = "mutated"
    assert first.payload["data"]["tag"] == "original"

    def failed_observer(_):
        raise RuntimeError("observer failed")

    received = []
    broker.enqueue(first, on_complete=failed_observer)
    broker.enqueue(intent(broker, resource="notify/b"), on_complete=received.append)
    broker.tick()
    broker.tick()
    assert len(received) == broker.completion_failures == 1
    assert broker.registry.lease_count == 0


@pytest.mark.parametrize("delay_at", ["policy", "acquire"])
def test_absolute_deadline_is_rechecked_after_policy_and_credit_acquisition(delay_at) -> None:
    broker, app, adapter = dispatcher()
    if delay_at == "acquire":
        class DelayedRegistry(ProcessLeaseRegistry):
            def acquire(self, request, lane):
                accepted = super().acquire(request, lane)
                if accepted:
                    app.clock.advance(11)
                return accepted
        broker.registry = DelayedRegistry()

    def authorization(_):
        if delay_at == "policy":
            app.clock.advance(11)
        return True

    received = []
    broker.enqueue(intent(broker, deadline=10), before_dispatch=authorization, on_complete=received.append)
    broker.tick()
    assert not adapter.calls
    assert broker.registry.lease_count == 0
    assert received[0].status == CompletionStatus.DEADLINE_MISSED
    assert broker.deadline_misses == 1


def test_proven_unsent_release_cannot_cancel_an_already_handed_off_call() -> None:
    broker, _, adapter = dispatcher()
    request = intent(broker)
    broker.enqueue(request)
    broker.tick()
    broker.registry.release_unsent(request.operation_id)
    assert broker.registry.lease_count == 1
    adapter.complete(0, {"success": True})
    broker.tick()
    assert broker.registry.lease_count == 0


def test_completion_observer_restart_cannot_dispatch_new_generation_from_old_tick() -> None:
    broker, _, adapter = dispatcher()
    adapter.mode, adapter.result = "immediate", {"success": True}

    def restart(_):
        broker.stop()
        broker.start()
        broker.enqueue(intent(broker, revision=2, payload={"message": "new generation"}))

    broker.enqueue(intent(broker), on_complete=restart)
    broker.tick()
    broker.tick()
    assert len(adapter.calls) == 1
    broker.tick()
    assert len(adapter.calls) == 2
