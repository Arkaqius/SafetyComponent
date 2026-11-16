"""Latest electrical policy and generation fences at actual broker handoff."""

from unittest.mock import Mock

from components.core.service_dispatcher import Lane, ProcessLeaseRegistry, ResourceSpec, ServiceDispatcher
from components.notification_manager.local_annunciator import LocalAnnunciator
from safety_lifecycle_support import CallbackServiceAdapter, LifecycleHass


def build_output():
    app, transport = LifecycleHass(), CallbackServiceAdapter()
    app.call_service = transport.call_service
    app.get_state = Mock(return_value={"state": "off", "attributes": {}})
    resources = [
        ResourceSpec("light.fixture", Lane.LOCAL, frozenset({"light/turn_on", "light/turn_off"})),
        ResourceSpec("alarm_control_panel.fixture", Lane.LOCAL, frozenset({"alarm_control_panel/alarm_trigger"})),
    ]
    broker = ServiceDispatcher(app, resources, clock=app.clock, registry=ProcessLeaseRegistry())
    broker.start()
    observed = Mock()
    output = LocalAnnunciator(app, {"light_entity": "light.fixture", "alarm_entity": "alarm_control_panel.fixture"},
                              observed, dispatcher=broker)
    return output, broker, app, transport, observed


def test_gas_inhibition_after_admission_denies_all_unsent_electrical_commands() -> None:
    output, broker, _, transport, observed = build_output()
    output.activate(1, "gas")
    assert not transport.calls
    output.inhibit_switching("active_or_unresolved_flammable_gas")
    broker.tick()
    assert not transport.calls
    assert not observed.called
    assert output.snapshot()["switching_inhibited"]
    output.clear("gas")
    broker.tick()
    assert not transport.calls and output.snapshot()["switching_inhibited"]


def test_latest_activation_supersedes_unsent_light_restore_and_targets_are_independent() -> None:
    output, broker, _, transport, observed = build_output()
    output.activate(2, "first")
    output.clear("first")
    output.activate(1, "second")
    broker.tick()
    assert {service for service, _ in transport.calls} == {"light/turn_on", "alarm_control_panel/alarm_trigger"}
    assert not observed.called
    transport.complete(0, {"success": True})
    broker.tick()
    assert observed.call_args.args[1] is False
    # The other resource remains held; no duplicate trigger is admitted.
    output.activate(1, "second")
    broker.tick()
    assert len(transport.calls) == 2


def test_stop_does_not_send_off_and_restart_cannot_replay_unsent_old_commands() -> None:
    output, broker, _, transport, observed = build_output()
    output.activate(1, "first")
    output.stop()
    output.start()
    broker.tick()
    assert not transport.calls and not observed.called
    assert output.snapshot()["active_levels"] == {"first": 1}


def test_unresolved_call_is_unknown_and_no_replacement_bypasses_quarantine() -> None:
    output, broker, app, transport, observed = build_output()
    output.activate(2, "first")
    broker.tick()
    app.clock.advance(30)
    broker.tick()
    assert observed.call_args.args[1] is True
    assert output.snapshot()["outputs"]["light.fixture"]["deadline_missed"]
    output.clear("first")
    broker.tick()
    assert len(transport.calls) == 1 and broker.registry.quarantined_count == 1
    transport.complete(0, None)
    broker.tick()
    assert transport.calls[-1][0] == "light/turn_off"


def test_stop_fences_late_completion_without_forgetting_restriction() -> None:
    output, broker, _, transport, observed = build_output()
    output.activate(2, "first")
    broker.tick()
    output.inhibit_switching("fixture restriction")
    output.stop()
    output.start()
    transport.complete(0, {"success": True})
    broker.tick()
    assert not observed.called and output.snapshot()["switching_inhibited"]
    assert len(transport.calls) == 1


def test_clear_before_handoff_cancels_queued_siren_without_a_reset_command() -> None:
    output, broker, _, transport, _ = build_output()
    output.activate(1, "first")
    output.clear("first")
    broker.tick()
    assert all(service != "alarm_control_panel/alarm_trigger" for service, _ in transport.calls)
    assert all("alarm_control_panel" not in service for service, _ in transport.calls)
