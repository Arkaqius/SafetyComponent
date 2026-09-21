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
from typing import Any, Mapping, Optional

import appdaemon.plugins.hass.hassapi as hass  # type: ignore

from components.core.common_entities import CommonEntities
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
from components.recovery_manager.state_store import (
    InMemoryRecoveryStateStore,
    RecoveryStateStore,
)


_TOGGLE_SERVICE_DOMAINS = frozenset(
    {"fan", "input_boolean", "light", "siren", "switch"}
)
_COVER_OPEN_VALUES = frozenset({"on", "open", "opened"})
_COVER_CLOSE_VALUES = frozenset({"off", "close", "closed"})


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
        self._pending_recovery_confirmations: dict[str, dict[str, str]] = {}
        self._recovery_confirmation_handles: dict[str, list[Any]] = {}
        self._recovery_deadline_handles: dict[str, Any] = {}
        self._proposals: dict[str, dict[str, Any]] = {}
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
        self._restore_state()

    def stop(self) -> None:
        """Persist active proposals during controlled shutdown."""

        self._persist_state()

    def _persist_state(self) -> None:
        """Persist only the allowlisted proposal lifecycle state."""

        self.state_store.save(
            {
                "version": 1,
                "proposals": [
                    {
                        **self._public_proposal(record),
                        "action_name": record.get("action_name"),
                        "fault_tag": record.get("fault_tag"),
                    }
                    for record in self._proposals.values()
                ],
            }
        )

    def _restore_state(self) -> None:
        """Restore visible active state without replaying actuator commands."""

        try:
            snapshot = self.state_store.load()
        except Exception as exc:
            self.hass_app.log(
                f"Unable to restore recovery state: {exc}", level="ERROR"
            )
            return
        for raw in snapshot.get("proposals", []):
            if not isinstance(raw, dict):
                continue
            proposal_id = str(raw.get("proposal_id", ""))
            recovery = self.recovery_actions.get(proposal_id)
            if recovery is None:
                continue
            record = dict(raw)
            if record.get("execution_policy") == "user_confirmed":
                record["status"] = RecoveryActionState.AWAITING_CONFIRMATION.name
                record["confirmation_token"] = secrets.token_urlsafe(24)
                record["expires_at"] = time.time() + 120
            elif record.get("status") == RecoveryActionState.EXECUTING.name:
                record["status"] = RecoveryActionState.TO_PERFORM.name
            self._proposals[proposal_id] = record
            self._set_rec_entity(recovery)

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
                if found_fault and found_fault.level < rec_fault_prio:
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
        proposals = [
            self._public_proposal(record)
            for record in self._proposals.values()
            if record.get("action_name") == recovery.name
        ]
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
        description = (
            str(proposals[0].get("instruction", ""))
            if len(proposals) == 1
            else f"{len(proposals)} aktywne zalecenia."
            if proposals
            else f"Recovery status for {recovery.name}."
        )
        self.mqtt_entities.register_sensor(
            sensor_name,
            str(recovery.params.get("friendly_name", f"Recovery {recovery.name}")),
            attributes={
                "description": description,
                "area_id": recovery.params.get("area_id"),
                "area_name": recovery.params.get("location"),
                "proposals": proposals,
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
            return

        if not self._validate_recovery_action(symptom, potential_recovery_action):
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
        **_: object,
    ) -> None:
        """EventBus handler for fault events."""
        if fault_state == FaultState.SHADOWED:
            self._recovery_clear(symptom)
            return
        self.recovery(symptom, fault_tag)

    def _handle_cleared_state(self, symptom: Symptom) -> None:
        """Handles the cleared state of a symptom by clearing recovery actions."""
        self.hass_app.log(
            f"Clearing recovery actions for symptom: {symptom.name}", level="DEBUG"
        )
        self._recovery_clear(symptom)

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
        potential_recovery_result: Optional[RecoveryResult] = (
            potential_recovery_action.rec_fun(
                self.hass_app,
                symptom,
                self.common_entities,
                **potential_recovery_action.params,
            )
        )

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

        for evaluator in self._policy_evaluators:
            decision = evaluator.evaluate_recovery_policy(recovery_result)
            if not decision.allowed:
                self.hass_app.log(
                    f"Recovery action for symptom {symptom.name} was inhibited by policy: "
                    f"{decision.reason or 'unspecified reason'}",
                    level="WARNING",
                )
                return False

        if self._is_dry_test_failed(symptom.name, recovery_result.changed_sensors):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} will trigger another fault. Aborting recovery.",
                level="DEBUG",
            )
            return False

        if self._isRecoveryConflict(symptom):
            self.hass_app.log(
                f"Recovery action for symptom {symptom.name} conflicts with existing faults. Aborting recovery.",
                level="DEBUG",
            )
            return False

        self.hass_app.log(
            f"Recovery action for symptom {symptom.name} validated successfully.",
            level="DEBUG",
        )
        return True

    def _execute_recovery(
        self, symptom: Symptom, recovery_result: RecoveryResult, fault_tag: str
    ) -> None:
        """Executes the recovery action for a given symptom."""
        self.hass_app.log(
            f"Executing recovery for symptom: {symptom.name}", level="DEBUG"
        )
        proposal = self._create_proposal(symptom, recovery_result, fault_tag)
        self._proposals[symptom.name] = proposal
        recovery = self.recovery_actions[symptom.name]
        for notification in recovery_result.notifications:
            self.nm.upsert_recovery_guidance(
                symptom.name, notification, fault_tag
            )

        if recovery_result.execution_policy == "user_confirmed":
            proposal["status"] = RecoveryActionState.AWAITING_CONFIRMATION.name
            self._set_rec_entity(recovery)
            self._persist_state()
            self._schedule_recovery_deadline(
                symptom.name,
                int(recovery_result.confirmation_timeout_seconds),
            )
            self.hass_app.log(
                f"Recovery {symptom.name} awaits explicit frontend confirmation",
                level="INFO",
            )
            return

        executed_actuator_changes = self._perform_recovery(
            symptom,
            [],
            recovery_result.changed_actuators,
            fault_tag,
        )
        proposal["status"] = (
            RecoveryActionState.EXECUTING.name
            if executed_actuator_changes
            else RecoveryActionState.TO_PERFORM.name
        )
        self._set_rec_entity(recovery)
        self._persist_state()
        self.hass_app.log(
            f"Recovery performed for symptom: {symptom.name}. Setting up listeners for changes.",
            level="DEBUG",
        )
        self._listen_to_changes(
            symptom,
            recovery_result.changed_sensors,
            executed_actuator_changes,
        )
        self.hass_app.log(f"Listeners set for symptom: {symptom.name}", level="DEBUG")

    def _create_proposal(
        self,
        symptom: Symptom,
        recovery_result: RecoveryResult,
        fault_tag: str,
    ) -> dict[str, Any]:
        """Create an allowlisted, replay-resistant recovery proposal record."""

        recovery = self.recovery_actions[symptom.name]
        timeout = max(15, int(recovery_result.confirmation_timeout_seconds))
        now = time.time()
        sensor_entity = next(iter(recovery_result.changed_sensors), "")
        actuator_entity = next(iter(recovery_result.changed_actuators), "")
        return {
            "proposal_id": symptom.name,
            "confirmation_token": (
                secrets.token_urlsafe(24)
                if recovery_result.execution_policy == "user_confirmed"
                else ""
            ),
            "action_name": recovery.name,
            "instruction": recovery_result.instruction
            or " ".join(recovery_result.notifications),
            "execution_policy": recovery_result.execution_policy,
            "status": RecoveryActionState.TO_PERFORM.name,
            "reason": recovery_result.reason,
            "source": recovery_result.source,
            "valid_until": recovery_result.valid_until,
            "expires_at": now + timeout,
            "area_id": recovery.params.get("area_id"),
            "area_name": recovery.params.get("location"),
            "postcondition_entity_id": sensor_entity,
            "actuator_entity_id": actuator_entity,
            "fault_tag": fault_tag,
        }

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
            return

        expected_actuator = str(proposal.get("actuator_entity_id", ""))
        if set(recovery_result.changed_actuators) != {expected_actuator}:
            self.hass_app.log(
                f"Recovery actuator changed for {proposal_id!r}; confirmation rejected",
                level="ERROR",
            )
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
                int(recovery_result.confirmation_timeout_seconds),
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
        }:
            return
        proposal["status"] = RecoveryActionState.TIMED_OUT.name
        proposal["confirmation_token"] = ""
        recovery = self.recovery_actions.get(symptom_name)
        if recovery is not None:
            self._set_rec_entity(recovery)
        self._persist_state()
        self.hass_app.log(
            f"Recovery deadline missed for {symptom_name}", level="ERROR"
        )

    @staticmethod
    def _proposal_expired(proposal: Mapping[str, Any]) -> bool:
        """Apply both the UI confirmation deadline and provider validity."""

        if time.time() > float(proposal["expires_at"]):
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

    def _recovery_clear_by_name(self, symptom_name: str) -> None:
        """Withdraw one proposal and all guidance/timers it owns."""

        if symptom_name in self.recovery_actions:
            self._cancel_recovery_confirmation_listeners(symptom_name)
            self._pending_recovery_confirmations.pop(symptom_name, None)
            self._cancel_recovery_deadline(symptom_name)
            proposal = self._proposals.pop(symptom_name, None)
            if proposal is not None:
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
            handle = self.hass_app.listen_state(
                self._recovery_performed,
                entity_id,
                new=str(expected_state),
                symptom_name=symptom.name,
                confirmation_entity=entity_id,
                expected_state=str(expected_state),
            )
            handles.append(handle)

        if self._all_recovery_postconditions_met(symptom.name):
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
        if str(new) != expected_state:
            return

        expected_changes = self._pending_recovery_confirmations.get(symptom.name)
        if expected_changes is None:
            return
        confirmation_entity = cb_args["confirmation_entity"]
        if expected_changes.get(confirmation_entity) != expected_state:
            return

        if self._all_recovery_postconditions_met(symptom.name):
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

        for entity_id, current_expected_state in expected_changes.items():
            current_state = self.hass_app.get_state(entity_id)
            if str(current_state) != current_expected_state:
                return False
        return True
