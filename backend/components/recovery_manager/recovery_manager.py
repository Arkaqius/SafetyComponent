"""
Recovery Manager Module for Home Assistant Safety System

This module defines the RecoveryManager class, a central component of a safety management system designed to handle the recovery process from fault conditions. 
The RecoveryManager oversees executing recovery actions in response to detected faults, playing a pivotal role in maintaining the operational integrity and safety of the system.

Overview: The RecoveryManager is built with flexibility in mind, enabling it to manage a wide array of fault conditions through customizable recovery actions. 
Each recovery action is encapsulated as a callable function, which can be dynamically invoked by the RecoveryManager along with relevant context or parameters necessary for addressing specific faults.

Key Features:

Dynamic Recovery Action Execution: Allows for the invocation of any callable as a recovery action, offering the flexibility to implement a variety of recovery strategies tailored to specific fault scenarios.
Context-Aware Fault Mitigation: Supports passing additional information to recovery actions, enabling context-aware processing and more effective fault mitigation strategies.
Simplified Fault Recovery Interface: Provides a straightforward method (recovery) for triggering recovery actions, simplifying the integration of the RecoveryManager into larger safety management systems.
Integration with Fault Tagging: Uses the faulttag feature to uniquely identify fault instances during recovery actions. This ensures that notifications, recovery, and fault tracking are handled consistently 
across the system, preventing confusion and ensuring coherent management of fault states.
Usage: The RecoveryManager is intended to be used within larger safety management or fault handling systems where specific recovery actions are defined for various types of faults. By encapsulating recovery 
logic within callable functions and associating them with particular fault conditions, system designers can create a comprehensive fault recovery framework capable of addressing a broad spectrum of operational anomalies.

This module's approach to fault recovery empowers developers to construct robust and adaptable safety mechanisms, enhancing the resilience and reliability of automated systems. The faulttag feature helps uniquely identify each fault scenario, aiding in efficient fault resolution and ensuring accurate system state tracking throughout the recovery process.
"""

import secrets
import time
from datetime import datetime, timezone
from math import ceil
from typing import Any, Callable, Mapping, Optional

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
from components.core.degradation import DegradationRegistry
from components.core.fault_state_policy import FaultCategory
from components.core.localization import Localizer
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.types_common import (
    Fault,
    FaultState,
    RecoveryAction,
    RecoveryActionState,
    RecoveryResult,
    SMState,
    Symptom,
)
from components.faults_manager.fault_manager import FaultManager
from components.notification_manager.notification_manager import NotificationManager
from components.recovery_manager.policy import RecoveryPolicyEvaluator
from components.recovery_manager.schema import RecoveryTiming
from components.recovery_manager.state_store import (
    InMemoryRecoveryStateStore,
    RecoveryStateStore,
)


_TOGGLE_SERVICE_DOMAINS = frozenset(
    {"fan", "input_boolean", "light", "siren", "switch"}
)
_COVER_OPEN_VALUES = frozenset({"on", "open", "opened"})
_COVER_CLOSE_VALUES = frozenset({"off", "close", "closed"})
_MAX_RECENT_OUTCOMES = 100
_EXECUTION_POLICIES = frozenset({"manual", "automatic", "user_confirmed"})
_COMPLETION_CONDITIONS = frozenset({"entity_state", "opening_closed", "owner_clear", "operator_report", "advisory"})


class ComponentRecoveryError(RuntimeError):
    """A component-owned recovery policy failed, not the shared dispatcher."""


class RecoveryManager:
    """
    Manages the recovery processes for faults within the safety management system.

    This class is responsible for executing recovery actions associated with faults. It acts upon
    the specified recovery actions by invoking callable functions designed to mitigate or resolve
    the conditions leading to the activation of faults. The RecoveryManager plays a critical role
    in the system's ability to respond to and recover from fault conditions, thereby maintaining
    operational integrity and safety.

    The RecoveryManager is designed to be flexible, allowing recovery actions to be defined as
    callable functions with associated additional information, facilitating customized recovery
    strategies for different fault scenarios.
    """

    def __init__(
        self,
        hass_app: hass.Hass,
        fm: FaultManager,
        recovery_actions: dict,
        common_entities: CommonEntities,
        nm: NotificationManager,
        mqtt_entities: MqttEntityManager,
        state_store: RecoveryStateStore | None = None,
        degradation: DegradationRegistry | None = None,
        diagnostics_observer: Callable[..., None] | None = None,
        recovery_observer: Callable[[str, bool], None] | None = None,
        command_observer: Callable[[str, str, bool, str], None] | None = None,
        timing: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Initializes the RecoveryManager with the necessary application context and recovery configuration.

        The constructor sets up the RecoveryManager by assigning the Home Assistant application context and
        a dictionary that contains configuration details for various recovery actions. This configuration
        dictionary is expected to map fault identifiers or types to specific callable functions that
        represent the recovery actions for those faults.

        Args:
            hass_app (hass.Hass): The Home Assistant application context, providing access to system-wide
                functionality and enabling the RecoveryManager to interact with other components and entities
                within the Home Assistant environment.
            fm (FaultManager): The FaultManager instance for managing fault conditions.
            recovery_actions (dict): A dictionary mapping fault names to their corresponding recovery actions.
            common_entities (CommonEntities): An instance containing common entities required for recovery actions.
            nm (NotificationManager): The NotificationManager instance for managing notifications related to recovery actions.

        This setup allows the RecoveryManager to dynamically execute the appropriate recovery actions
        based on the faults detected within the system, promoting a flexible and responsive fault management
        framework.
        """
        self.hass_app: hass.Hass = hass_app
        self.recovery_actions: dict[str, RecoveryAction] = recovery_actions
        self.common_entities: CommonEntities = common_entities
        self.fm: FaultManager = fm
        self.nm: NotificationManager = nm
        self.mqtt_entities = mqtt_entities
        self.state_store = state_store or InMemoryRecoveryStateStore()
        self.degradation = degradation
        self.diagnostics_observer = diagnostics_observer
        self.recovery_observer = recovery_observer
        self.command_observer = command_observer
        self.timing = RecoveryTiming.model_validate(dict(timing or {}))
        self._command_failures: dict[tuple[str, str], str] = {}
        self._command_postconditions: dict[tuple[str, str], dict[str, str]] = {}
        self._command_failure_handles: dict[tuple[str, str], list[Any]] = {}
        self._state_restored = False
        self._storage_available = True
        self._saving_state = False
        self._pending_recovery_confirmations: dict[str, dict[str, str]] = {}
        self._recovery_confirmation_handles: dict[str, list[Any]] = {}
        self._recovery_deadline_handles: dict[str, Any] = {}
        self._proposals: dict[str, dict[str, Any]] = {}
        self._recent_outcomes: list[dict[str, Any]] = []
        self._validation_reasons: dict[str, str] = {}
        self._policy_evaluators: list[RecoveryPolicyEvaluator] = []
        self._started = False

        self._init_all_rec_entities()

    def start(self) -> None:
        """Register the authenticated frontend confirmation event."""

        if self._started:
            return
        self._started = True
        listen_event = getattr(self.hass_app, "listen_event", None)
        if callable(listen_event):
            listen_event(
                self.handle_recovery_confirmation,
                "safety_recovery_confirm",
            )
            listen_event(self.handle_manual_work_report, "safety_recovery_report")
        self._restore_state()
        self.invalidate_restricted_proposals()

    def invalidate_restricted_proposals(self) -> None:
        """Withdraw pending actuator confirmations whose dependencies are unsafe."""

        if self.degradation is None:
            return
        for symptom_id, proposal in tuple(self._proposals.items()):
            if proposal.get("status") != RecoveryActionState.AWAITING_CONFIRMATION.name:
                continue
            if self.degradation.recovery_allowed(
                symptom_id, evidence_source=str(proposal.get("source", ""))
            ):
                continue
            self.hass_app.log(
                f"Withdrawing restricted recovery proposal for {symptom_id}",
                level="WARNING",
            )
            self._recovery_clear_by_name(symptom_id)

    def stop(self) -> None:
        """Persist active proposals during controlled shutdown."""

        for key in tuple(self._command_failure_handles):
            self._cancel_command_failure_watch(key)
        self._persist_state()

    def _persist_state(self) -> bool:
        """Persist only the allowlisted proposal lifecycle state."""

        if self._saving_state:
            return False
        self._saving_state = True
        try:
            self.state_store.save(
                {
                    "version": 1,
                    "recent_outcomes": self._recent_outcomes,
                    "proposals": [
                        {
                            **self._public_proposal(record),
                            "action_name": record.get("action_name"),
                            "fault_tag": record.get("fault_tag"),
                            "expected_postconditions": record.get(
                                "expected_postconditions", {}
                            ),
                            "actuator_targets": record.get("actuator_targets", {}),
                            "report_user_id": record.get("report_user_id", ""),
                            "outcome_recorded": record.get("outcome_recorded", False),
                        }
                        for record in self._proposals.values()
                    ],
                    "command_failures": [
                        {
                            "symptom_id": symptom_id,
                            "entity_id": entity_id,
                            "detail": detail,
                            "postconditions": self._command_postconditions.get(
                                (symptom_id, entity_id), {}
                            ),
                        }
                        for (symptom_id, entity_id), detail in sorted(self._command_failures.items())
                    ],
                }
            )
        except Exception as exc:
            self._storage_available = False
            if self.diagnostics_observer is not None:
                self.diagnostics_observer("persistence", True, detail="recovery_state", operation="save")
            self.hass_app.log(f"Unable to persist recovery state: {exc}", level="ERROR")
            return False
        else:
            self._storage_available = True
            if self.diagnostics_observer is not None:
                self.diagnostics_observer("persistence", False, detail="recovery_state", operation="save")
            return True
        finally:
            self._saving_state = False

    def _restore_state(self) -> None:
        """Restore visible active state without replaying actuator commands."""

        self._state_restored = False
        try:
            snapshot = self.state_store.load()
        except Exception as exc:
            self._storage_available = False
            if self.diagnostics_observer is not None:
                self.diagnostics_observer("persistence", True, detail="recovery_state", operation="load")
            self.hass_app.log(
                f"Unable to restore recovery state: {exc}", level="ERROR"
            )
            return
        raw_outcomes = snapshot.get("recent_outcomes", [])
        if not isinstance(raw_outcomes, list) or len(raw_outcomes) > _MAX_RECENT_OUTCOMES:
            self.hass_app.log("Invalid recovery outcome state", level="ERROR")
            if self.diagnostics_observer is not None:
                self.diagnostics_observer("persistence", True, detail="recovery_state", operation="load")
            return
        restored_outcomes = []
        for raw in raw_outcomes:
            if not isinstance(raw, dict) or not all(
                isinstance(raw.get(key), str)
                for key in ("proposal_id", "action_name", "outcome", "recorded_at")
            ):
                self.hass_app.log("Invalid recovery outcome record", level="ERROR")
                if self.diagnostics_observer is not None:
                    self.diagnostics_observer("persistence", True, detail="recovery_state", operation="load")
                return
            restored_outcomes.append(self._outcome_record(raw))
        self._recent_outcomes = restored_outcomes
        raw_failures = snapshot.get("command_failures", [])
        if not isinstance(raw_failures, list) or any(
            not isinstance(item, dict)
            or not all(item.get(key) for key in ("symptom_id", "entity_id", "detail"))
            or not isinstance(item.get("postconditions", {}), dict)
            or any(
                not isinstance(entity, str) or not isinstance(value, str)
                for entity, value in item.get("postconditions", {}).items()
            )
            for item in raw_failures
        ):
            if self.diagnostics_observer is not None:
                self.diagnostics_observer(
                    "persistence", True, detail="recovery_state", operation="load"
                )
            self.hass_app.log("Invalid recovery command failure state", level="ERROR")
            return
        self._command_failures = {
            (str(item["symptom_id"]), str(item["entity_id"])): str(item["detail"])
            for item in raw_failures
        }
        self._command_postconditions = {
            (str(item["symptom_id"]), str(item["entity_id"])): dict(
                item.get("postconditions", {})
            )
            for item in raw_failures
        }
        for raw in snapshot.get("proposals", []):
            if not isinstance(raw, dict):
                continue
            proposal_id = str(raw.get("proposal_id", ""))
            recovery = self.recovery_actions.get(proposal_id)
            if recovery is None:
                continue
            record = dict(raw)
            record.setdefault("completion_condition", "entity_state")
            record.setdefault("expected_result", "")
            record.setdefault("purpose", "hazard_mitigation")
            record.setdefault("source", "")
            record.setdefault("actuator_entity_id", "")
            record.setdefault("manual_report_allowed", False)
            record["report_token"] = (
                secrets.token_urlsafe(24)
                if record.get("manual_report_allowed") and not record.get("reported_at")
                else ""
            )
            if record.get("status") == RecoveryActionState.EXECUTING.name:
                record["status"] = RecoveryActionState.FAILED.name
                record["confirmation_token"] = ""
                actuator = str(record.get("actuator_entity_id", ""))
                if actuator:
                    key = (proposal_id, actuator)
                    self._command_failures.setdefault(
                        key, "postcondition_unverified_after_restart"
                    )
                    expected = record.get("expected_postconditions", {})
                    if isinstance(expected, dict) and expected:
                        self._command_postconditions.setdefault(
                            key, {
                                str(source): str(state)
                                for source, state in expected.items()
                            },
                        )
            elif (
                record.get("execution_policy") == "user_confirmed"
                and record.get("status") == RecoveryActionState.AWAITING_CONFIRMATION.name
            ):
                record["confirmation_token"] = secrets.token_urlsafe(24)
                record.setdefault("expires_at", time.time() + 120)
            self._proposals[proposal_id] = record
        for recovery in {action.name: action for action in self.recovery_actions.values()}.values():
            self._set_rec_entity(recovery)
        self._state_restored = True
        if self.diagnostics_observer is not None:
            self.diagnostics_observer("persistence", False, detail="recovery_state", operation="load")

    def failed_recovery_commands(self) -> dict[tuple[str, str], str] | None:
        """Return outstanding command/postcondition failures for D-fault restore."""

        return dict(self._command_failures) if self._state_restored else None

    def _record_command_outcome(
        self, symptom_id: str, entity_id: str, failed: bool, detail: str
    ) -> None:
        """Persist a scoped failure before publishing its diagnostic outcome."""

        key = (symptom_id, entity_id)
        if failed:
            self._command_failures[key] = detail
            proposal = self._proposals.get(symptom_id, {})
            expected = proposal.get("expected_postconditions", {})
            if isinstance(expected, dict) and expected:
                self._command_postconditions[key] = {
                    str(source): str(state) for source, state in expected.items()
                }
        elif key in self._command_failures:
            del self._command_failures[key]
            self._command_postconditions.pop(key, None)
            self._cancel_command_failure_watch(key)
        else:
            return
        try:
            self._persist_state()
        finally:
            if self.command_observer is not None:
                self.command_observer(symptom_id, entity_id, failed, detail)
            if failed:
                self._watch_command_failure(key)

    def resume_command_postconditions(self) -> None:
        """Resume passive repair observation after restart without replaying actions."""

        for key in tuple(self._command_failures):
            self._watch_command_failure(key)
        for symptom_name, proposal in tuple(self._proposals.items()):
            symptom = self.fm.symptoms.get(symptom_name)
            if symptom is None:
                continue
            if proposal.get("status") == RecoveryActionState.AWAITING_CONFIRMATION.name:
                if self._proposal_expired(proposal):
                    self._mark_recovery_timed_out(symptom_name)
                else:
                    self._schedule_recovery_deadline(
                        symptom_name, max(1, ceil(float(proposal["expires_at"]) - time.time()))
                    )
            elif proposal.get("execution_policy") == "manual" and proposal.get("expires_at") is not None and proposal.get("status") == RecoveryActionState.TO_PERFORM.name:
                if self._proposal_expired(proposal):
                    self._mark_recovery_timed_out(symptom_name)
                else:
                    self._schedule_recovery_deadline(symptom_name, max(1, ceil(float(proposal["expires_at"]) - time.time())))
            if (
                proposal.get("execution_policy") == "manual"
                and proposal.get("completion_condition") in {"opening_closed", "entity_state"}
                and proposal.get("status") == RecoveryActionState.TO_PERFORM.name
                and symptom_name not in self._pending_recovery_confirmations
            ):
                self._listen_to_changes(symptom, proposal["expected_postconditions"], {})

    def _watch_command_failure(self, key: tuple[str, str]) -> None:
        expected = self._command_postconditions.get(key, {})
        if not expected or key in self._command_failure_handles:
            return
        handles: list[Any] = []
        self._command_failure_handles[key] = handles
        for source, value in expected.items():
            handles.append(self.hass_app.listen_state(
                self._command_failure_postcondition_changed,
                source,
                new=value,
                failure_symptom_id=key[0],
                failure_actuator=key[1],
            ))
        if self._failure_postconditions_met(key):
            self._record_command_outcome(
                key[0], key[1], False, "postcondition_confirmed"
            )

    def _command_failure_postcondition_changed(
        self, _: Any, __: Any, ___: Any, ____: Any, **kwargs: Any
    ) -> None:
        key = (str(kwargs["failure_symptom_id"]), str(kwargs["failure_actuator"]))
        if key in self._command_failures and self._failure_postconditions_met(key):
            self._record_command_outcome(
                key[0], key[1], False, "postcondition_confirmed"
            )

    def _failure_postconditions_met(self, key: tuple[str, str]) -> bool:
        expected = self._command_postconditions.get(key, {})
        if not expected:
            return False
        try:
            return all(
                str(self.hass_app.get_state(source)) == value
                for source, value in expected.items()
            )
        except Exception as exc:
            self.hass_app.log(
                f"Unable to verify recovery postcondition: {exc}",
                level="WARNING",
            )
            return False

    def _cancel_command_failure_watch(self, key: tuple[str, str]) -> None:
        for handle in self._command_failure_handles.pop(key, []):
            try:
                self.hass_app.cancel_listen_state(handle)
            except Exception as exc:
                self.hass_app.log(
                    f"Unable to cancel recovery command listener: {exc}",
                    level="WARNING",
                )

    def register_policy_evaluator(
        self, evaluator: RecoveryPolicyEvaluator
    ) -> None:
        """Register a non-actuating policy check for proposed recovery results."""

        self._policy_evaluators.append(evaluator)

    def _init_all_rec_entities(self) -> None:
        for _, recovery_actions in self.recovery_actions.items():
            self._set_rec_entity(recovery_actions)

    def _isRecoveryConflict(self, symptom: Symptom) -> bool:
        """
        Determines if there is a conflict between the given symptom's recovery actions and existing faults.

        This method checks whether executing the recovery actions for a given symptom would
        conflict with any existing faults. It considers the priority of the faults and matching
        recovery actions to ensure that the recovery process does not introduce new issues.

        Args:
            symptom (symptom): The symptom object representing the fault to check for conflicts.

        Returns:
            bool: True if a conflict exists, False otherwise.
        """
        matching_actions: list[str] = self._get_matching_actions(symptom)

        if matching_actions:
            rec_fault: Fault | None = self.fm.found_mapped_fault(
                symptom.name, symptom.sm_name
            )
            if rec_fault:
                rec_fault_prio: int = rec_fault.level
                conflict_status: bool = self._check_conflict_with_matching_actions(
                    matching_actions, rec_fault_prio, symptom
                )
                self.hass_app.log(
                    f"Conflict status for {symptom} is {conflict_status}", level="DEBUG"
                )
                return conflict_status

        return False

    def _get_matching_actions(self, symptom: Symptom) -> list[str]:
        """
        Retrieves a list of recovery action names that match the given symptom.

        This method searches for and returns the names of recovery actions that correspond
        to the given symptom. It is used to identify potential conflicts or applicable
        recovery strategies based on the symptom's characteristics.

        Args:
            symptom (symptom): The symptom object representing the fault to match.

        Returns:
            list[str]: A list of matching recovery action names.
        """
        return [
            name
            for name, action in self.recovery_actions.items()
            if action.name in self.recovery_actions[symptom.name].name
        ]

    def _check_conflict_with_matching_actions(
        self, matching_actions: list[str], rec_fault_prio: int, symptom: Symptom
    ) -> bool:
        """
        Checks for conflicts between the given symptom's recovery actions and existing faults based on priorities.

        This method evaluates whether the recovery actions for a given symptom would conflict with
        other existing faults by comparing their priorities. It ensures that higher-priority faults
        are not adversely affected by the recovery actions for lower-priority faults.

        Args:
            matching_actions (list[str]): A list of matching recovery action names.
            rec_fault_prio (int): The priority of the recovery fault.
            symptom (Symptom): The symptom object representing the fault to check for conflicts.

        Returns:
            bool: True if a conflict exists, False otherwise.
        """
        for found_symptom_name in matching_actions:
            # Skip the current symptom to avoid self-comparison
            if found_symptom_name == symptom.name:
                continue

            found_symptom: Symptom = self.fm.symptoms[found_symptom_name]
            if found_symptom:
                found_fault: Fault | None = self.fm.found_mapped_fault(
                    found_symptom.name, found_symptom.sm_name
                )
                if found_fault and found_fault.level < rec_fault_prio and (
                    found_symptom.state == FaultState.SET
                    or (found_fault.evaluation.active is True and found_fault.evaluation.latched is True)
                ):
                    return True

        return False

    def _perform_recovery(
        self,
        symptom: Symptom,
        notifications: list,
        entities_changes: dict[str, str],
        fault_tag: str,
    ) -> dict[str, str]:
        """
        Executes the recovery actions for the given symptom, including notifications and entity changes.

        This method performs the actual recovery process for a given symptom by executing the
        associated recovery actions. It handles sending notifications and making necessary changes
        to system entities to resolve the fault condition.

        Args:
            symptom (Symptom): The symptom object representing the fault to recover from.
            notifications (list): A list of notifications to send as part of the recovery process.
            entities_changes (dict[str, str]): A dictionary mapping entity names to their new values as part of the recovery process.

        Returns:
            dict[str, str]: Actuator commands accepted by Home Assistant.
        """
        executed_changes: dict[str, str] = {}
        rec: RecoveryAction | None = self._find_recovery(symptom.name)
        if rec:
            rec.current_status = RecoveryActionState.TO_PERFORM
            self._set_rec_entity(rec)
            for entity, value in entities_changes.items():
                try:
                    self._execute_entity_action(entity, value)
                    executed_changes[entity] = value
                except Exception as err:
                    self.hass_app.log(
                        f"Exception during setting {entity} to {value} value. {err}",
                        level="ERROR",
                    )
                    self._record_command_outcome(
                        symptom.name, entity, True, f"command_failed: {type(err).__name__}"
                    )
            for notification in notifications:
                fault: Fault | None = self.fm.found_mapped_fault(
                    symptom.name, symptom.sm_name
                )
                if fault:
                    self.nm._add_recovery_action(notification, fault_tag)
        else:
            self.hass_app.log(
                f"Recovery action for {symptom.name} was not found!", level="ERROR"
            )
        return executed_changes

    def _find_recovery(self, symptom_name: str) -> RecoveryAction | None:
        """
        Finds and returns the recovery action associated with the given symptom name.

        This method searches for and retrieves the recovery action that corresponds to the
        specified symptom name. It is used to locate the appropriate recovery strategy
        for a given fault condition.

        Args:
            symptom_name (str): The name of the symptom to find the recovery action for.

        Returns:
            RecoveryAction | None: The recovery action associated with the symptom name, or None if not found.
        """
        for name, rec in self.recovery_actions.items():
            if name == symptom_name:
                return rec
        return None

    def _set_rec_entity(self, recovery: RecoveryAction) -> None:
        """
        Sets the state of the recovery entity in the Home Assistant context.

        This method updates the state of the specified recovery entity in the Home Assistant
        system. It is used to reflect the current status of the recovery process for monitoring
        and tracking purposes.

        Args:
            recovery (RecoveryAction): The recovery action to set the state for.
        """
        sensor_name = f"sensor.recovery_{recovery.name}"
        sensor_name = MqttEntityManager.canonical_entity_id(
            sensor_name, expected_domain="sensor"
        )
        localizer = getattr(self.hass_app, "localizer", None)
        if not isinstance(localizer, Localizer):
            localizer = Localizer()
        proposals = [
            self._public_proposal(record)
            for record in self._proposals.values()
            if record.get("action_name") == recovery.name
        ]
        for proposal in proposals:
            owner = self.fm.symptoms.get(str(proposal.get("proposal_id", "")))
            if (
                proposal.get("execution_policy") == "manual"
                and proposal.get("status") == RecoveryActionState.TO_PERFORM.name
                and proposal.get("completion_condition") != "advisory"
                and owner is not None and owner.state == FaultState.NOT_TESTED
            ):
                # Retain historical instructions and passive observation without claiming applicability.
                proposal.update(status=RecoveryActionState.DO_NOT_PERFORM.name,
                                manual_report_allowed=False,
                                blocked_reason=localizer.text("recovery.blocked_owner_unverified"),
                                blocked_reason_code="owner_unverified")
                proposal.pop("report_token", None)
                proposal.pop("confirmation_token", None)
        recent_outcomes = [
            {key: value for key, value in record.items() if key != "report_user_id"} for record in reversed(self._recent_outcomes)
            if record.get("action_name") == recovery.name
        ][:3]
        state_priority = {
            RecoveryActionState.FAILED.name: 0,
            RecoveryActionState.TIMED_OUT.name: 1,
            RecoveryActionState.EXECUTING.name: 2,
            RecoveryActionState.AWAITING_CONFIRMATION.name: 3,
            RecoveryActionState.TO_PERFORM.name: 4,
            RecoveryActionState.CONFIRMED.name: 5,
        }
        if proposals:
            state_name = min(
                (str(proposal["status"]) for proposal in proposals),
                key=lambda status: state_priority.get(status, 99),
            )
            recovery.current_status = RecoveryActionState[state_name]
        else:
            recovery.current_status = RecoveryActionState.DO_NOT_PERFORM
        sensor_value: str = recovery.current_status.name
        localizer = getattr(self.hass_app, "localizer", None)
        if not isinstance(localizer, Localizer):
            localizer = Localizer()
        description = (
            str(proposals[0].get("instruction", ""))
            if len(proposals) == 1
            else localizer.text("recovery.active_count", count=len(proposals))
            if proposals
            else localizer.text("recovery.no_action")
        )
        self.mqtt_entities.register_sensor(
            sensor_name,
            str(recovery.params.get("friendly_name", f"Recovery {recovery.name}")),
            attributes={
                "description": description,
                "area_id": recovery.params.get("area_id"),
                "area_name": recovery.params.get("location"),
                "proposals": proposals,
                "recent_outcomes": recent_outcomes,
                "blocked_reason": recovery.params.get("blocked_reason", ""),
            },
            icon="mdi:lifebuoy",
            entity_category="diagnostic",
        )
        self.mqtt_entities.publish_sensor_state(sensor_name, sensor_value)

    @staticmethod
    def _public_proposal(record: dict[str, Any]) -> dict[str, Any]:
        """Return the allowlisted MQTT/frontend representation of a proposal."""

        allowed = (
            "proposal_id",
            "confirmation_token",
            "instruction",
            "execution_policy",
            "status",
            "reason",
            "source",
            "valid_until",
            "expires_at",
            "area_id",
            "area_name",
            "postcondition_entity_id",
            "actuator_entity_id",
            "fault_id",
            "proposal_instance_id",
            "completion_condition",
            "expected_result",
            "purpose",
            "manual_report_allowed",
            "report_token",
            "report_status",
            "reported_at",
            "report_source",
            "blocked_reason",
            "blocked_reason_code",
            "evidence_at",
            "evidence_source",
            "consent_timeout_seconds",
            "effect_timeout_seconds",
        )
        return {key: record.get(key) for key in allowed if record.get(key) not in (None, "")}

    def _execute_entity_action(self, entity: str, value: str) -> None:
        """Execute a supported recovery action through a native HA service."""
        service = self._resolve_entity_action(entity, value)
        response = self.hass_app.call_service(service, entity_id=entity)
        if isinstance(response, Mapping) and response.get("success") is False:
            raise RuntimeError(
                f"Home Assistant service {service} rejected {entity}: {response}"
            )

    @staticmethod
    def _resolve_entity_action(entity: str, value: str) -> str:
        """Resolve a constrained entity/value pair to a Home Assistant service."""
        if not isinstance(entity, str) or entity.count(".") != 1:
            raise ValueError(f"Invalid recovery entity_id: {entity!r}")
        domain, object_id = entity.split(".", 1)
        if not domain or not object_id:
            raise ValueError(f"Invalid recovery entity_id: {entity!r}")

        normalized_value = str(value).strip().lower()
        if domain == "cover":
            if normalized_value in _COVER_OPEN_VALUES:
                return "cover/open_cover"
            if normalized_value in _COVER_CLOSE_VALUES:
                return "cover/close_cover"
            raise ValueError(
                f"Unsupported cover target {value!r} for recovery entity {entity}"
            )

        if domain in _TOGGLE_SERVICE_DOMAINS:
            if normalized_value == "on":
                return f"{domain}/turn_on"
            if normalized_value == "off":
                return f"{domain}/turn_off"
            raise ValueError(
                f"Unsupported {domain} target {value!r} for recovery entity {entity}"
            )

        raise ValueError(
            f"Unsupported recovery domain {domain!r} for entity {entity}"
        )

    def _is_dry_test_failed(
        self, prefaul_name: str, entities_changes: dict[str, str]
    ) -> bool:
        """
        Runs a dry test to determine if the given entity changes will trigger new faults.

        This method performs a simulation (dry test) to check whether the proposed changes to
        system entities will cause new faults to be triggered. It ensures that recovery actions
        do not inadvertently introduce new issues.

        Args:
            prefaul_name (str): The name of the symptom to test.
            entities_changes (dict[str, str]): A dictionary mapping entity names to their new values to test.

        Returns:
            bool: True if the entity changes will trigger new faults, False otherwise.
        """
        for symptom_name, symptom_data in self.fm.get_all_symptom().items():
            if symptom_data.sm_state == SMState.ENABLED:
                owner = self.fm.found_mapped_fault(
                    symptom_name, symptom_data.sm_name
                )
                if owner is None or owner.category != FaultCategory.H:
                    continue
                # Force each sm to get state if possible
                sm_fcn = getattr(symptom_data.module, symptom_data.sm_name)
                isFaultTrigged = sm_fcn(
                    symptom_data.module.safety_mechanisms[symptom_data.name],
                    entities_changes,
                )
                if isFaultTrigged and symptom_name != prefaul_name:
                    return True
        return False

    def recovery(self, symptom: Symptom, fault_tag) -> None:
        """
        Executes the appropriate recovery action for the given symptom.

        Args:
            symptom (Symptom): The symptom object representing the fault to recover from.
        """
        self.hass_app.log(
            f"Starting recovery process for symptom: {symptom.name}", level="DEBUG"
        )

        if symptom.state == FaultState.CLEARED:
            self.hass_app.log(
                f"Symptom {symptom.name} is in CLEARED state. Handling cleared state.",
                level="DEBUG",
            )
            self._handle_cleared_state(symptom)
            return

        potential_recovery_action: RecoveryResult | None = (
            self._get_potential_recovery_action(symptom)
        )
        if not potential_recovery_action:
            self._recovery_clear_by_name(symptom.name, reason="no_current_action")
            return

        if not self._validate_recovery_action(symptom, potential_recovery_action):
            self._recovery_clear_by_name(
                symptom.name,
                reason=self._validation_reasons.get(symptom.name, "policy_rejected"),
            )
            self._publish_blocked_proposal(symptom, potential_recovery_action, fault_tag)
            return

        self.hass_app.log(
            f"Validation successful. Executing recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )
        self._execute_recovery(symptom, potential_recovery_action, fault_tag)
        self.hass_app.log(
            f"Recovery process completed for symptom: {symptom.name}", level="DEBUG"
        )

    def handle_fault_event(
        self,
        *,
        symptom: Symptom,
        fault_tag: str,
        fault_state: FaultState,
        fault_name: str | None = None,
        **_: object,
    ) -> None:
        """EventBus handler for fault events."""
        if fault_state == FaultState.SHADOWED:
            fault = self.fm.faults.get(fault_name) if fault_name else None
            if fault is None:
                self._recovery_clear(symptom)
            else:
                related_sms = set(fault.related_symptoms)
                for contributor in self.fm.symptoms.values():
                    if (
                        contributor.sm_name in related_sms
                        and contributor.state == FaultState.SET
                    ):
                        self._recovery_clear(contributor)
            return
        try:
            self.recovery(symptom, fault_tag)
        except ComponentRecoveryError:
            raise
        except Exception:
            if self.recovery_observer is not None:
                self.recovery_observer(symptom.name, True)
            raise
        if self.recovery_observer is not None:
            self.recovery_observer(symptom.name, False)

    def _handle_cleared_state(self, symptom: Symptom) -> None:
        """Handles the cleared state of a symptom by clearing recovery actions."""
        self.hass_app.log(
            f"Clearing recovery actions for symptom: {symptom.name}", level="DEBUG"
        )
        proposal = self._proposals.get(symptom.name)
        if proposal and (
            proposal.get("completion_condition") == "owner_clear"
            or self._all_recovery_postconditions_met(symptom.name)
        ):
            proposal["status"] = RecoveryActionState.CONFIRMED.name
            proposal["evidence_source"] = str(proposal.get("source") or "fault_owner")
            proposal["evidence_at"] = datetime.now(timezone.utc).isoformat()
        self._recovery_clear_by_name(symptom.name, reason="owner_cleared")

    def _get_potential_recovery_action(
        self, symptom: Symptom
    ) -> Optional[RecoveryResult]:
        """Retrieves the potential recovery action for a given symptom."""
        if symptom.name not in self.recovery_actions:
            self.hass_app.log(
                f"No recovery actions defined for symptom: {symptom.name}",
                level="DEBUG",
            )
            return None

        self.hass_app.log(
            f"Retrieving potential recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )
        potential_recovery_action: RecoveryAction = self.recovery_actions[symptom.name]
        try:
            potential_recovery_result: Optional[RecoveryResult] = (
                potential_recovery_action.rec_fun(
                    self.hass_app,
                    symptom,
                    self.common_entities,
                    **potential_recovery_action.params,
                )
            )
        except Exception as exc:
            raise ComponentRecoveryError(
                f"Component recovery policy failed for {symptom.name}"
            ) from exc

        if potential_recovery_result is not None and not any((
            potential_recovery_result.changed_sensors,
            potential_recovery_result.changed_actuators,
            potential_recovery_result.notifications,
            potential_recovery_result.instruction,
        )):
            potential_recovery_result = None

        if not potential_recovery_result:
            self.hass_app.log(
                f"No changes determined for recovery of symptom: {symptom.name}",
                level="DEBUG",
            )
        else:
            self.hass_app.log(
                f"Potential recovery result obtained for symptom: {symptom.name}",
                level="DEBUG",
            )

        return potential_recovery_result

    def _validate_recovery_action(
        self, symptom: Symptom, recovery_result: RecoveryResult
    ) -> bool:
        """Validates if the recovery action can be safely executed without conflicts."""
        self.hass_app.log(
            f"Validating potential recovery action for symptom: {symptom.name}",
            level="DEBUG",
        )

        self._validation_reasons.pop(symptom.name, None)
        contract_reason = self._execution_contract_reason(recovery_result)
        if contract_reason:
            self._validation_reasons[symptom.name] = contract_reason
            return False
        if self._indoor_hazard_conflict(recovery_result):
            self._validation_reasons[symptom.name] = "indoor_hazard_conflict"
            return False
        if (
            self.degradation is not None
            and recovery_result.changed_actuators
            and not self.degradation.recovery_allowed(
                symptom.name, evidence_source=recovery_result.source
            )
        ):
            self.hass_app.log(
                f"Recovery action for {symptom.name} is restricted by diagnostic coverage",
                level="WARNING",
            )
            self._validation_reasons[symptom.name] = "diagnostic_restriction"
            return False

        for evaluator in self._policy_evaluators:
            decision = evaluator.evaluate_recovery_policy(recovery_result)
            if not decision.allowed:
                self.hass_app.log(
                    f"Recovery action for symptom {symptom.name} was inhibited by policy: "
                    f"{decision.reason or 'unspecified reason'}",
                    level="WARNING",
                )
                self._validation_reasons[symptom.name] = decision.reason or "policy_rejected"
                return False

        if recovery_result.changed_sensors and self._is_dry_test_failed(
            symptom.name, recovery_result.changed_sensors
        ):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} will trigger another fault. Aborting recovery.",
                level="DEBUG",
            )
            self._validation_reasons[symptom.name] = "conflicting_postcondition"
            return False

        if recovery_result.completion_condition not in {"owner_clear", "operator_report", "advisory"} and self._isRecoveryConflict(symptom):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} conflicts with existing faults. Aborting recovery.",
                level="DEBUG",
            )
            self._validation_reasons[symptom.name] = "conflicting_action"
            return False

        self.hass_app.log(
            f"Recovery action for symptom {symptom.name} validated successfully.",
            level="DEBUG",
        )
        return True

    def _indoor_hazard_conflict(self, result: RecoveryResult) -> bool:
        """Block opening/comfort outputs while smoke, gas or CO safety is unresolved."""

        changes = {**result.changed_sensors, **result.changed_actuators}
        exposure_change = any(
            str(value).lower() in {"on", "open", "opened"}
            for value in changes.values()
        )
        if not exposure_change:
            return False
        for fault in self.fm.faults.values():
            if fault.name not in {
                "InternalSmokeDetected", "InternalFlammableGasDetected", "InternalCarbonMonoxideDetected"
            }:
                continue
            evaluation = fault.evaluation
            if evaluation.active or evaluation.status.value in {"NOT_EVALUATED", "UNEVALUABLE", "PENDING_FAILURE", "PENDING_RECOVERY"}:
                return True
        return False

    def _stage_timeouts(self, result: RecoveryResult) -> tuple[int, int, int | None]:
        """Preserve legacy per-action overrides while separating lifecycle budgets."""

        legacy = result.confirmation_timeout_seconds if result.confirmation_timeout_seconds != 120 else None
        values = RecoveryTiming.model_validate({
            "consent_timeout_seconds": (result.consent_timeout_seconds if result.consent_timeout_seconds is not None
                                        else legacy if legacy is not None else self.timing.consent_timeout_seconds),
            "effect_timeout_seconds": (result.effect_timeout_seconds if result.effect_timeout_seconds is not None
                                       else legacy if legacy is not None else self.timing.effect_timeout_seconds),
            "manual_task_timeout_seconds": (
                result.manual_task_timeout_seconds if result.manual_task_timeout_seconds is not None
                else self.timing.manual_task_timeout_seconds
            ),
        })
        return values.consent_timeout_seconds, values.effect_timeout_seconds, values.manual_task_timeout_seconds

    def _publish_blocked_proposal(self, symptom: Symptom, result: RecoveryResult, fault_tag: str) -> None:
        """Expose an ineligible action's reason without leaving an executable token."""

        reason = self._validation_reasons.get(symptom.name, "policy_rejected")
        recovery = self.recovery_actions.get(symptom.name)
        if recovery is None:
            return
        localizer = getattr(self.hass_app, "localizer", None)
        if not isinstance(localizer, Localizer):
            localizer = Localizer()
        recovery.params["blocked_reason"] = localizer.text(f"recovery.blocked_{reason}")
        if not self._execution_contract_reason(result):
            proposal = self._create_proposal(symptom, result, fault_tag)
            proposal.update(status=RecoveryActionState.DO_NOT_PERFORM.name,
                            confirmation_token="", report_token="", manual_report_allowed=False,
                            blocked_reason=recovery.params["blocked_reason"], blocked_reason_code=reason)
            self._proposals[symptom.name] = proposal
        self._set_rec_entity(recovery)
        self._persist_state()

    @staticmethod
    def _execution_contract_reason(result: RecoveryResult) -> str:
        """Reject unsupported policies and manual commands at the shared boundary."""

        if result.execution_policy not in _EXECUTION_POLICIES:
            return "unsupported_execution_policy"
        if result.completion_condition not in _COMPLETION_CONDITIONS:
            return "unsupported_completion_condition"
        if result.execution_policy == "manual" and result.changed_actuators:
            return "manual_actuator_forbidden"
        if result.completion_condition in {"operator_report", "advisory"} and (
            result.execution_policy != "manual" or result.changed_actuators or result.changed_sensors
            or (result.completion_condition == "operator_report" and not result.manual_report_allowed)
            or (result.completion_condition == "advisory" and result.manual_report_allowed)
        ):
            return "invalid_manual_completion"
        if result.manual_report_allowed and result.execution_policy != "manual":
            return "invalid_manual_completion"
        if result.completion_condition == "owner_clear" and (
            result.execution_policy != "manual" or result.changed_actuators or result.changed_sensors
        ):
            return "invalid_owner_completion"
        if result.completion_condition == "opening_closed" and (
            result.execution_policy != "manual"
            or len(result.changed_sensors) != 1
            or set(result.changed_sensors.values()) != {"off"}
        ):
            return "invalid_opening_completion"
        return ""

    def _execute_recovery(
        self, symptom: Symptom, recovery_result: RecoveryResult, fault_tag: str
    ) -> None:
        """Executes the recovery action for a given symptom."""
        if self._execution_contract_reason(recovery_result):
            raise ValueError("Invalid recovery execution contract")
        self.hass_app.log(
            f"Executing recovery for symptom: {symptom.name}", level="DEBUG"
        )
        proposal = self._create_proposal(symptom, recovery_result, fault_tag)
        existing = self._proposals.get(symptom.name)
        if existing and not existing.get("blocked_reason") and all(
            existing.get(key) == proposal.get(key)
            for key in ("fault_tag", "execution_policy", "completion_condition",
                        "expected_postconditions", "actuator_entity_id", "purpose", "source", "manual_report_allowed")
        ) and (
            existing.get("actuator_targets") == proposal["actuator_targets"]
            or ("actuator_targets" not in existing and existing.get("status") == RecoveryActionState.FAILED.name)
        ):
            # Context refresh must not repeat a command or extend its deadline.
            for key in ("instruction", "reason", "source", "valid_until", "expected_result"):
                existing[key] = proposal[key]
            self.nm.upsert_recovery_guidance(symptom.name, proposal["instruction"], fault_tag)
            self._set_rec_entity(self.recovery_actions[symptom.name])
            self._persist_state()
            return
        if existing:
            self._recovery_clear_by_name(symptom.name, reason="superseded")
        self._proposals[symptom.name] = proposal
        recovery = self.recovery_actions[symptom.name]
        recovery.params.pop("blocked_reason", None)
        if proposal["instruction"]:
            self.nm.upsert_recovery_guidance(symptom.name, proposal["instruction"], fault_tag)

        if recovery_result.execution_policy == "user_confirmed":
            proposal["status"] = RecoveryActionState.AWAITING_CONFIRMATION.name
            self._set_rec_entity(recovery)
            self._persist_state()
            self._schedule_recovery_deadline(
                symptom.name,
                int(proposal["consent_timeout_seconds"]),
            )
            self.hass_app.log(
                f"Recovery {symptom.name} awaits explicit frontend confirmation",
                level="INFO",
            )
            return

        if recovery_result.changed_actuators:
            proposal["status"] = RecoveryActionState.EXECUTING.name
            if not self._persist_state():
                self._proposals.pop(symptom.name, None)
                self._validation_reasons[symptom.name] = "diagnostic_restriction"
                self._publish_blocked_proposal(symptom, recovery_result, fault_tag)
                return
        executed_actuator_changes = self._perform_recovery(
            symptom,
            [],
            recovery_result.changed_actuators,
            fault_tag,
        )
        command_failed = any(
            (symptom.name, entity) in self._command_failures
            for entity in recovery_result.changed_actuators
        )
        proposal["status"] = (
            RecoveryActionState.FAILED.name if command_failed else
            RecoveryActionState.EXECUTING.name if executed_actuator_changes else
            RecoveryActionState.TO_PERFORM.name
        )
        self._set_rec_entity(recovery)
        self._persist_state()
        self.hass_app.log(
            f"Recovery performed for symptom: {symptom.name}. Setting up listeners for changes.",
            level="DEBUG",
        )
        if recovery_result.completion_condition in {"entity_state", "opening_closed"}:
            self._listen_to_changes(
                symptom,
                recovery_result.changed_sensors,
                recovery_result.changed_actuators,
            )
        if (
            symptom.name in self._proposals
            and proposal["status"] == RecoveryActionState.EXECUTING.name
        ):
            self._schedule_recovery_deadline(
                symptom.name, int(proposal["effect_timeout_seconds"])
            )
        elif (
            symptom.name in self._proposals
            and proposal["execution_policy"] == "manual"
            and proposal["expires_at"] is not None
        ):
            self._schedule_recovery_deadline(symptom.name, max(1, ceil(proposal["expires_at"] - time.time())))
        self.hass_app.log(f"Listeners set for symptom: {symptom.name}", level="DEBUG")

    def _create_proposal(
        self,
        symptom: Symptom,
        recovery_result: RecoveryResult,
        fault_tag: str,
    ) -> dict[str, Any]:
        """Create an allowlisted, replay-resistant recovery proposal record."""

        recovery = self.recovery_actions[symptom.name]
        consent, effect, manual = self._stage_timeouts(recovery_result)
        now = time.time()
        sensor_entity = next(iter(recovery_result.changed_sensors), "")
        actuator_entity = next(iter(recovery_result.changed_actuators), "")
        fault = self.fm.found_mapped_fault(symptom.name, symptom.sm_name)
        return {
            "proposal_id": symptom.name,
            "confirmation_token": (
                secrets.token_urlsafe(24)
                if recovery_result.execution_policy == "user_confirmed"
                else ""
            ),
            "action_name": recovery.name,
            "fault_id": fault.name if fault and isinstance(fault.name, str) else "",
            "proposal_instance_id": secrets.token_hex(12),
            "completion_condition": recovery_result.completion_condition,
            "expected_result": recovery_result.expected_result,
            "purpose": recovery_result.purpose,
            "manual_report_allowed": recovery_result.manual_report_allowed,
            "report_token": secrets.token_urlsafe(24) if recovery_result.manual_report_allowed else "",
            "report_status": "",
            "effect_timeout_seconds": effect,
            "consent_timeout_seconds": consent,
            "instruction": recovery_result.instruction
            or " ".join(recovery_result.notifications),
            "execution_policy": recovery_result.execution_policy,
            "status": RecoveryActionState.TO_PERFORM.name,
            "reason": recovery_result.reason,
            "source": recovery_result.source,
            "valid_until": recovery_result.valid_until,
            "expires_at": (now + consent if recovery_result.execution_policy == "user_confirmed" else
                           now + effect if recovery_result.execution_policy == "automatic" else
                           now + manual if manual is not None and recovery_result.completion_condition != "advisory" else None),
            "area_id": recovery.params.get("area_id"),
            "area_name": recovery.params.get("location"),
            "postcondition_entity_id": sensor_entity,
            "actuator_entity_id": actuator_entity,
            "actuator_targets": dict(recovery_result.changed_actuators),
            "expected_postconditions": (
                dict(recovery_result.changed_sensors)
                or self._actuator_postconditions(recovery_result.changed_actuators)
            ),
            "fault_tag": fault_tag,
        }

    def handle_manual_work_report(self, event_name: str, data: Mapping[str, Any], **_: Any) -> None:
        """Accept current one-time work reports with HA-provided actor and server time."""

        del event_name
        proposal_id = str(data.get("proposal_id", ""))
        proposal = self._proposals.get(proposal_id)
        metadata = data.get("metadata", {})
        context = metadata.get("context", {}) if isinstance(metadata, Mapping) else {}
        actor = context.get("user_id") if isinstance(context, Mapping) else None
        allowed = {"proposal_id", "proposal_instance_id", "report_token", "metadata"}
        token = data.get("report_token")
        if (
            set(data) - allowed or not isinstance(actor, str) or not actor or len(actor) > 128
            or proposal is None or proposal.get("manual_report_allowed") is not True
            or proposal.get("execution_policy") != "manual"
            or proposal.get("status") != RecoveryActionState.TO_PERFORM.name
            or proposal.get("blocked_reason") or proposal.get("reported_at")
            or not self._storage_available
            or data.get("proposal_instance_id") != proposal.get("proposal_instance_id")
            or not isinstance(token, str) or not token
            or not secrets.compare_digest(token, str(proposal.get("report_token", "")))
        ):
            self.hass_app.log(f"Rejected unauthenticated, stale or replayed recovery report for {proposal_id!r}", level="WARNING")
            return
        if self._proposal_expired(proposal):
            self._mark_recovery_timed_out(proposal_id)
            return
        symptom = self.fm.symptoms.get(proposal_id)
        result = self._get_potential_recovery_action(symptom) if symptom and symptom.state == FaultState.SET else None
        fault = self.fm.found_mapped_fault(symptom.name, symptom.sm_name) if symptom else None
        evaluation = getattr(fault, "evaluation", None)
        if (
            result is None or not result.manual_report_allowed or not self._validate_recovery_action(symptom, result)
            or result.completion_condition != proposal.get("completion_condition")
            or result.changed_sensors != proposal.get("expected_postconditions", {})
            or result.changed_actuators
            or (evaluation is not None and bool(evaluation.shadowed_by))
        ):
            self._recovery_clear_by_name(proposal_id, reason="report_ineligible")
            return
        previous = dict(proposal)
        previous_outcomes = list(self._recent_outcomes)
        proposal.update(report_token="", report_user_id=actor,
                        reported_at=datetime.now(timezone.utc).isoformat(), report_source="operator")
        if result.completion_condition == "operator_report":
            proposal.update(status=RecoveryActionState.CONFIRMED.name, report_status="completed",
                            evidence_source="operator_report", evidence_at=proposal["reported_at"])
            self._record_final_outcome(proposal, "completed", "operator_report")
        else:
            proposal["report_status"] = "awaiting_evidence"
        if not self._persist_state():
            self._proposals[proposal_id] = previous
            self._recent_outcomes = previous_outcomes
        elif result.completion_condition == "operator_report":
            self._cancel_recovery_deadline(proposal_id)
            self.nm.remove_recovery_guidance(proposal_id, str(proposal.get("fault_tag", "")))
        self._set_rec_entity(self.recovery_actions[proposal_id])

    def handle_recovery_confirmation(
        self,
        event_name: str,
        data: Mapping[str, Any],
        **_: Any,
    ) -> None:
        """Authorize one current gate-closing proposal from the SafetyHome UI."""

        del event_name
        proposal_id = str(data.get("proposal_id", ""))
        token = str(data.get("confirmation_token", ""))
        proposal = self._proposals.get(proposal_id)
        if (
            proposal is None
            or proposal.get("status")
            != RecoveryActionState.AWAITING_CONFIRMATION.name
            or not secrets.compare_digest(
                token, str(proposal.get("confirmation_token", ""))
            )
        ):
            self.hass_app.log(
                f"Rejected invalid or replayed recovery confirmation for {proposal_id!r}",
                level="WARNING",
            )
            return
        if self._proposal_expired(proposal):
            self._mark_recovery_timed_out(proposal_id)
            return

        self._cancel_recovery_deadline(proposal_id)

        symptom = self.fm.symptoms.get(proposal_id)
        if symptom is None or symptom.state != FaultState.SET:
            self.hass_app.log(
                f"Rejected stale recovery confirmation for {proposal_id!r}",
                level="WARNING",
            )
            self._recovery_clear_by_name(proposal_id)
            return
        recovery_result = self._get_potential_recovery_action(symptom)
        if (
            recovery_result is None
            or recovery_result.execution_policy != "user_confirmed"
            or not recovery_result.changed_actuators
            or not self._validate_recovery_action(symptom, recovery_result)
        ):
            self.hass_app.log(
                f"Recovery {proposal_id!r} no longer passes execution policy",
                level="WARNING",
            )
            self._recovery_clear_by_name(proposal_id, reason="confirmation_ineligible")
            return

        expected_actuator = str(proposal.get("actuator_entity_id", ""))
        current_postconditions = (
            dict(recovery_result.changed_sensors)
            or self._actuator_postconditions(recovery_result.changed_actuators)
        )
        if (
            set(recovery_result.changed_actuators) != {expected_actuator}
            or dict(recovery_result.changed_actuators) != proposal.get("actuator_targets")
            or current_postconditions != proposal.get("expected_postconditions")
        ):
            self.hass_app.log(
                f"Recovery actuator changed for {proposal_id!r}; confirmation rejected",
                level="ERROR",
            )
            self._recovery_clear_by_name(proposal_id, reason="superseded")
            return

        proposal["status"] = RecoveryActionState.EXECUTING.name
        proposal["expires_at"] = time.time() + int(proposal.get("effect_timeout_seconds", self.timing.effect_timeout_seconds))
        if not self._persist_state():
            proposal.update(status=RecoveryActionState.FAILED.name, confirmation_token="",
                            blocked_reason=Localizer().text("recovery.blocked_diagnostic_restriction"))
            self._set_rec_entity(self.recovery_actions[proposal_id])
            return
        executed = self._perform_recovery(
            symptom,
            [],
            recovery_result.changed_actuators,
            str(proposal["fault_tag"]),
        )
        if set(executed) != {expected_actuator}:
            proposal["status"] = RecoveryActionState.FAILED.name
            proposal["confirmation_token"] = ""
            self._set_rec_entity(self.recovery_actions[proposal_id])
            self._persist_state()
            self._listen_to_changes(
                symptom, recovery_result.changed_sensors,
                recovery_result.changed_actuators,
            )
            return
        proposal["status"] = RecoveryActionState.EXECUTING.name
        proposal["confirmation_token"] = ""
        self._set_rec_entity(self.recovery_actions[proposal_id])
        self._persist_state()
        self._listen_to_changes(
            symptom,
            recovery_result.changed_sensors,
            executed,
        )
        if proposal_id in self._proposals:
            self._schedule_recovery_deadline(
                proposal_id,
                int(proposal.get("effect_timeout_seconds", self.timing.effect_timeout_seconds)),
            )

    def _schedule_recovery_deadline(
        self, symptom_name: str, timeout_seconds: int
    ) -> None:
        """Replace the active proposal deadline timer."""

        self._cancel_recovery_deadline(symptom_name)
        run_in = getattr(self.hass_app, "run_in", None)
        if callable(run_in):
            self._recovery_deadline_handles[symptom_name] = run_in(
                self._recovery_deadline_reached,
                timeout_seconds,
                symptom_name=symptom_name,
            )

    def _cancel_recovery_deadline(self, symptom_name: str) -> None:
        handle = self._recovery_deadline_handles.pop(symptom_name, None)
        if handle is None:
            return
        cancel_timer = getattr(self.hass_app, "cancel_timer", None)
        if callable(cancel_timer):
            try:
                cancel_timer(handle)
            except Exception as exc:
                self.hass_app.log(
                    f"Failed to cancel recovery deadline: {exc}",
                    level="WARNING",
                )

    def _recovery_deadline_reached(self, **kwargs: Any) -> None:
        self._mark_recovery_timed_out(str(kwargs["symptom_name"]))

    def _mark_recovery_timed_out(self, symptom_name: str) -> None:
        proposal = self._proposals.get(symptom_name)
        if proposal is None or proposal.get("status") not in {
            RecoveryActionState.AWAITING_CONFIRMATION.name,
            RecoveryActionState.EXECUTING.name,
            RecoveryActionState.TO_PERFORM.name,
        }:
            return
        was_executing = proposal.get("status") == RecoveryActionState.EXECUTING.name
        proposal["status"] = RecoveryActionState.TIMED_OUT.name
        proposal["confirmation_token"] = ""
        proposal["report_token"] = ""
        recovery = self.recovery_actions.get(symptom_name)
        if recovery is not None:
            self._set_rec_entity(recovery)
        self._persist_state()
        actuator = str(proposal.get("actuator_entity_id", ""))
        if was_executing and actuator:
            self._record_command_outcome(
                symptom_name, actuator, True, "postcondition_timeout"
            )
        self.hass_app.log(
            f"Recovery deadline missed for {symptom_name}", level="ERROR"
        )

    @staticmethod
    def _proposal_expired(proposal: Mapping[str, Any]) -> bool:
        """Apply both the UI confirmation deadline and provider validity."""

        expires_at = proposal.get("expires_at")
        if expires_at is not None and time.time() > float(expires_at):
            return True
        valid_until = str(proposal.get("valid_until", "")).strip()
        if not valid_until:
            return False
        try:
            parsed = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > parsed.astimezone(timezone.utc)

    def _recovery_clear(self, symptom: Symptom) -> None:
        """
        Clears the recovery action for the given symptom.

        This method clears the internal register and updates the system state to indicate that
        the recovery action for the specified symptom has been completed and should no longer
        be performed.

        Args:
            symptom (symptom): The symptom object representing the fault to clear the recovery action for.
        """
        self._recovery_clear_by_name(symptom.name)

    def _recovery_clear_by_name(self, symptom_name: str, *, reason: str = "withdrawn") -> None:
        """Withdraw one proposal and all guidance/timers it owns."""

        if symptom_name in self.recovery_actions:
            self._cancel_recovery_confirmation_listeners(symptom_name)
            self._pending_recovery_confirmations.pop(symptom_name, None)
            self._cancel_recovery_deadline(symptom_name)
            proposal = self._proposals.pop(symptom_name, None)
            if proposal is not None:
                outcome = {
                    RecoveryActionState.CONFIRMED.name: "completed",
                    RecoveryActionState.FAILED.name: "failed",
                    RecoveryActionState.TIMED_OUT.name: "timed_out",
                }.get(str(proposal.get("status")), "withdrawn")
                self._record_final_outcome(proposal, outcome, reason)
                self.nm.remove_recovery_guidance(
                    symptom_name, str(proposal.get("fault_tag", ""))
                )
            # Clear internal register
            self.recovery_actions[symptom_name].current_status = (
                RecoveryActionState.DO_NOT_PERFORM
            )
            # Set HA entity
            self._set_rec_entity(self.recovery_actions[symptom_name])
            self._persist_state()

    def _record_final_outcome(self, proposal: dict[str, Any], outcome: str, reason: str) -> None:
        """Record each incident's result once; keep authenticated attribution private."""

        if proposal.get("outcome_recorded"):
            return
        self._recent_outcomes.append(self._outcome_record({
            **proposal, "outcome": outcome, "outcome_reason": reason,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }))
        self._recent_outcomes = self._recent_outcomes[-_MAX_RECENT_OUTCOMES:]
        proposal["outcome_recorded"] = True

    @classmethod
    def _outcome_record(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        """Keep a bounded, token-free completion/withdrawal record."""

        fields = cls._public_proposal(dict(record))
        fields.pop("confirmation_token", None)
        fields.pop("report_token", None)
        for key in ("action_name", "outcome", "outcome_reason", "recorded_at", "report_user_id"):
            if key in record:
                fields[key] = record[key]
        return {
            key: value[:1024] if isinstance(value, str) else value
            for key, value in fields.items()
            if value is None or isinstance(value, (str, int, float, bool))
        }

    def _listen_to_changes(
        self,
        symptom: Symptom,
        sensor_changes: dict[str, str],
        actuator_changes: dict[str, str],
    ) -> None:
        """
        Sets up listeners for state changes in the specified entities to monitor recovery action completion.

        This method establishes listeners on the specified entities to detect when the state changes
        as part of the recovery process. It ensures that the system can respond to and track the completion
        of recovery actions.

        Args:
            symptom (symptom): The symptom object representing the fault being recovered from.
            sensor_changes (dict[str, str]): Physical postconditions to monitor.
            actuator_changes (dict[str, str]): Successfully requested actuators,
                used only when no dedicated postcondition sensor exists.
        """
        expected_changes = dict(sensor_changes)
        if not expected_changes:
            expected_changes = self._actuator_postconditions(actuator_changes)

        if not expected_changes:
            self.hass_app.log(
                f"No observable postcondition for recovery {symptom.name}.",
                level="WARNING",
            )
            return

        self._cancel_recovery_confirmation_listeners(symptom.name)
        self._pending_recovery_confirmations[symptom.name] = {
            entity_id: str(expected_state)
            for entity_id, expected_state in expected_changes.items()
        }
        handles: list[Any] = []
        self._recovery_confirmation_handles[symptom.name] = handles
        for entity_id, expected_state in expected_changes.items():
            options = {} if self._proposals.get(symptom.name, {}).get("completion_condition") == "opening_closed" else {"new": str(expected_state)}
            handle = self.hass_app.listen_state(
                self._recovery_performed,
                entity_id,
                **options,
                symptom_name=symptom.name,
                confirmation_entity=entity_id,
                expected_state=str(expected_state),
            )
            handles.append(handle)

        if self._all_recovery_postconditions_met(symptom.name):
            self._confirm_command_postcondition(symptom.name)
            proposal = self._proposals.get(symptom.name)
            if proposal is not None:
                proposal["status"] = RecoveryActionState.CONFIRMED.name
                self._set_rec_entity(self.recovery_actions[symptom.name])
            self._recovery_clear(symptom)

    def _cancel_recovery_confirmation_listeners(self, symptom_name: str) -> None:
        """Cancel state listeners left by a completed or superseded recovery."""
        handles = self._recovery_confirmation_handles.pop(symptom_name, [])
        cancel_listener = getattr(self.hass_app, "cancel_listen_state", None)
        if cancel_listener is None:
            return
        for handle in handles:
            try:
                cancel_listener(handle)
            except Exception as exc:
                self.hass_app.log(
                    f"Failed to cancel recovery listener: {exc}",
                    level="WARNING",
                )

    @staticmethod
    def _actuator_postconditions(
        actuator_changes: dict[str, str],
    ) -> dict[str, str]:
        """Translate actuator commands into observable fallback states."""
        expected_states: dict[str, str] = {}
        for entity_id, value in actuator_changes.items():
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            normalized_value = str(value).strip().lower()
            if domain == "cover":
                if normalized_value in _COVER_OPEN_VALUES:
                    expected_states[entity_id] = "open"
                elif normalized_value in _COVER_CLOSE_VALUES:
                    expected_states[entity_id] = "closed"
            elif domain in _TOGGLE_SERVICE_DOMAINS and normalized_value in {
                "on",
                "off",
            }:
                expected_states[entity_id] = normalized_value
        return expected_states

    def _recovery_performed(
        self, _: Any, __: Any, ___: Any, new: Any, **cb_args: Any
    ) -> None:
        """
        Callback function invoked when a recovery action is performed.

        This method is called when a state change is detected in one of the monitored entities,
        indicating that a recovery action has been performed. It clears the recovery action for
        the corresponding symptom.

        Args:
            _ (Any): Placeholder for the first callback argument (not used).
            __ (Any): Placeholder for the second callback argument (not used).
            ___ (Any): Placeholder for the third callback argument (not used).
            ____ (Any): Placeholder for the fourth callback argument (not used).
            **cb_args (Any): AppDaemon callback arguments, including the stable
                symptom name and expected confirmation state.
        """
        symptom_name = str(cb_args["symptom_name"])
        symptom = self.fm.symptoms.get(symptom_name)
        if symptom is None:
            self.hass_app.log(
                f"Ignoring recovery confirmation for unknown symptom {symptom_name}",
                level="WARNING",
            )
            return
        expected_state = cb_args["expected_state"]
        if not self._postcondition_matches(symptom.name, new, expected_state):
            return

        expected_changes = self._pending_recovery_confirmations.get(symptom.name)
        if expected_changes is None:
            return
        confirmation_entity = cb_args["confirmation_entity"]
        if expected_changes.get(confirmation_entity) != expected_state:
            return

        if self._all_recovery_postconditions_met(symptom.name):
            self._confirm_command_postcondition(symptom.name)
            proposal = self._proposals.get(symptom.name)
            if proposal is not None:
                proposal["status"] = RecoveryActionState.CONFIRMED.name
                self._set_rec_entity(self.recovery_actions[symptom.name])
            self._recovery_clear(symptom)

    def _all_recovery_postconditions_met(self, symptom_name: str) -> bool:
        """Return whether all current recovery postconditions are satisfied."""
        expected_changes = self._pending_recovery_confirmations.get(symptom_name)
        if not expected_changes:
            return False
        proposal = self._proposals.get(symptom_name, {})
        if self.degradation is not None and not self.degradation.recovery_allowed(
            symptom_name, evidence_source=str(proposal.get("source", ""))
        ):
            return False

        for entity_id, current_expected_state in expected_changes.items():
            current_state = self.hass_app.get_state(entity_id)
            if not self._postcondition_matches(symptom_name, current_state, current_expected_state):
                return False
        return True

    def _postcondition_matches(self, symptom_name: str, value: Any, expected: str) -> bool:
        """Accept the owning door profile's closed aliases without accepting unknown."""

        if self._proposals.get(symptom_name, {}).get("completion_condition") == "opening_closed":
            return str(value).strip().lower() in {"off", "closed", "false", "0"}
        return str(value) == expected

    def _confirm_command_postcondition(self, symptom_name: str) -> None:
        """Clear a command-path failure only after observed physical evidence."""

        proposal = self._proposals.get(symptom_name)
        if proposal is None:
            return
        proposal["evidence_source"] = ", ".join(proposal.get("expected_postconditions", {}))
        proposal["evidence_at"] = datetime.now(timezone.utc).isoformat()
        actuator = str(proposal.get("actuator_entity_id", ""))
        if actuator:
            self._record_command_outcome(
                symptom_name, actuator, False, "postcondition_confirmed"
            )
