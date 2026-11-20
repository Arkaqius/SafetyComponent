"""
This module integrates various safety functions into the Home Assistant environment, focusing on the management of safety-related components, fault conditions, and recovery processes. It defines the `SafetyFunctions` class, which serves as the main entry point for initializing and managing the safety mechanisms within Home Assistant.

Features and Components:
- **Safety Mechanisms**: Supports the implementation of domain-specific safety mechanisms, such as temperature monitoring through the `TemperatureComponent`.
- **Fault and symptom Management**: Utilizes `FaultManager` to handle fault and symptom conditions, allowing for systematic detection, notification, and recovery from potential safety issues.
- **Notifications**: Leverages `NotificationManager` for sending alerts or messages in response to safety events or fault conditions.
- **Recovery Actions**: Incorporates `RecoveryManager` to define and execute recovery actions for mitigating detected fault conditions.
- **Configuration Parsing**: Employs configuration parsing (via `cfg_pr`) to initialize safety mechanisms, fault conditions, and recovery actions based on predefined settings.

Key Functionalities:
- **Initialization**: On initialization, the module sets up safety mechanisms, fault conditions, symptom conditions, and recovery managers according to configurations specified in Home Assistant's app configuration.
- **Safety Mechanism Registration**: Registers the `FaultManager` with each safety mechanism component, ensuring integrated fault and recovery management.
- **State Monitoring and Management**: Monitors the state of various components and updates Home Assistant's state machine with the health status of the safety app.

Usage:
The `SafetyFunctions` class is designed to be used as an AppDaemon app within Home Assistant. It requires configuration settings for symptoms, faults, notifications, and any domain-specific safety mechanisms to be provided in the AppDaemon app's YAML configuration file.

Example Configuration (YAML):
```yaml
SafetyFunctions:
  module: safety_functions_module
  class: SafetyFunctions
  symptoms: {...}
  faults: {...}
  notification: {...}

This module exemplifies a holistic approach to safety management within Home Assistant,
offering a framework for the development and integration of comprehensive safety features.

Note:

- Ensure that all required configurations are provided and correctly formatted.
- The module is designed for extensibility, allowing for the integration of additional safety mechanisms as needed.

"""

from datetime import datetime, timezone
from typing import Any, Dict, Mapping
from urllib.parse import urlparse
from uuid import uuid4

import appdaemon.plugins.hass.hassapi as hass
from pydantic import ValidationError

from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)
from components.core.battery_fault_catalog import (
    BatteryFaultCatalog,
    reconcile_battery_faults,
)
from components.core.common_entities import CommonEntities
from components.core.degradation import (
    DegradationRegistry,
    RestrictionEffect,
    compile_runtime_bindings,
)
from components.core.event_bus import EventBus
from components.core.detector_test_monitor import DetectorTestMonitor
from components.core.periodic_test_monitor import PeriodicTestMonitor
from components.core.evaluation_progress import EvaluationProgress
from components.core.functional_safety_diagnostics import (
    JsonFunctionalSafetyDiagnosticsStore,
)
from components.core.functional_safety_monitor import FunctionalSafetyMonitor
from components.external_apis.home_assistant_state import HomeAssistantStateProvider
from components.external_apis.home_assistant_state_reader import HomeAssistantStateReader
from components.external_apis.stable_releases import StableReleaseProvider
from components.core.derivative_monitor import DerivativeMonitor
from components.core.localization import LocalizationSettings
from components.core.lifecycle import CancellationKind, LifecycleScope
from components.core.mqtt_entity_manager import MqttEntityManager
from components.core.service_dispatcher import Lane, ResourceSpec, ServiceDispatcher
from components.core.self_diagnostics import SelfDiagnosticsComponent
from components.core.sqlite_state_store import SqliteStateDatabase, state_database_path
from components.core.startup_grace import StartupGrace
from components.external_apis import (
    ExternalApiRuntime,
    HttpJsonClient,
    get_registered_api_components,
)
from components.external_apis.core.selection_state import AppliedSourceSelection
from components.safetycomponents.external_hazard.assertion_store import (
    AssertionRecord,
    RealAssertionStore,
)
from components.safetycomponents.internal_environmental_hazard.state_store import (
    INDOOR_FAULTS, MAX_BYTES as INDOOR_MAX_BYTES, IndoorStateOwner, InMemoryInternalEnvironmentStateStore, decode_checkpoint, current_launch_id,
)
from components.faults_manager import cfg_parser as cfg_pr
from components.faults_manager.fault_manager import FaultManager, SYSTEM_STATE_BY_FAULT_LEVEL
from components.faults_manager.evidence import FaultEvidenceJournal
from components.faults_manager.evidence_store import (
    InMemoryFaultEvidenceStore,
)
from components.notification_manager.notification_manager import NotificationManager
from components.notification_manager.mobile_push_provider import MobilePushProvider
from components.notification_manager.local_annunciator import LocalAnnunciator
from components.notification_manager.state_store import (
    InMemoryNotificationStateStore,
)
from components.recovery_manager.recovery_manager import RecoveryManager
from components.recovery_manager.state_store import (
    InMemoryRecoveryStateStore,
)
from components.safetyhome_api import SafetyHomeApiGateway
from components.safety_routines.runtime import SafetyRoutineRuntime
from components.safetycomponents.core.safety_component import (
    get_registered_components,
)
import components.safetycomponents.temperature.temperature_component  # noqa: F401 - component registration
import components.safetycomponents.heating.heating_system_monitor_component  # noqa: F401 - component registration
import components.safetycomponents.safety_doors.safety_doors_component  # noqa: F401 - component registration
import components.safetycomponents.external_hazard.external_hazard_component  # noqa: F401 - component registration
import components.safetycomponents.entity_monitor.entity_monitor_component  # noqa: F401 - component registration
import components.safetycomponents.internal_environmental_hazard.internal_environmental_hazard_monitor_component  # noqa: F401 - component registration
from components.core.types_common import RecoveryAction, SMState, Symptom


class SafetyFunctions(hass.Hass):
    """
    Main class for managing safety functions in the Home Assistant environment.
    """

    def initialize(self) -> None:
        """
        Initialize the SafetyFunctions app and its components.
        This method sets up safety mechanisms, fault conditions, recovery actions, and health state.
        """
        # Disable all the no-member violations in this function
        # pylint: disable=attribute-defined-outside-init
        self._coverage_reevaluation_enabled = False
        self.runtime_id = uuid4().hex
        self._root_scope = LifecycleScope("SafetyFunctions", runtime_id=self.runtime_id, enabled=True)
        self._root_scope.start()
        if not self._initialize_mqtt():
            self.stop_app(self.name)
            return

        # Invalidate retained applied truth before validation can fail or polling starts.
        selection_entity = self.mqtt_entities.register_sensor(
            "sensor.external_source_selection",
            self.localizer.text("entity.external_source_selection"),
            icon="mdi:format-list-checks", entity_category="diagnostic",
        )
        self.mqtt_entities.publish_sensor_state(
            selection_entity, "unknown",
            attributes={"schema_version": 1, "runtime_id": self.runtime_id},
        )

        try:
            self.runtime_config: Dict[str, Any] = AppCfgValidator.validate(
                self.args, hass=self, log=self.log
            )
        except AppCfgValidationError as exc:
            self.log(f"Invalid app configuration: {exc}", level="ERROR")
            self._set_internal_entity(
                "sensor.safety_app_health",
                "invalid_cfg",
                attributes={"configuration_error": str(exc)},
            )
            self._start_mqtt_reporting()
            return

        # Prepare shared runtime state and event infrastructure.
        self.sm_modules: dict = {}
        self.api_modules: dict = {}
        self.symptoms: dict[str, Symptom] = {}
        self.recovery_actions: dict[str, RecoveryAction] = {}
        inactive_fault_names: set[str] = set()
        self.derivative_monitor = DerivativeMonitor(self, self.mqtt_entities)
        self.event_bus = EventBus()

        # Extract the validated configuration sections used at runtime.
        self.fault_dict: dict = self.runtime_config["app_config"]["faults"]
        self.safety_components_cfg: dict = self.runtime_config["user_config"][
            "safety_components"
        ]
        self.notification_cfg: dict = self.runtime_config["user_config"]["notification"]
        self.common_entities_cfg: dict = self.runtime_config["user_config"][
            "common_entities"
        ]
        self.api_components_cfg: dict = self.runtime_config["user_config"].get(
            "api_components", {}
        )
        self.site_cfg: dict = self.runtime_config["user_config"].get("site", {})
        self.external_sources = self.runtime_config["user_config"]["external_sources"]
        self.applied_source_selection = AppliedSourceSelection(
            self.mqtt_entities,
            runtime_id=self.runtime_id,
            component_enabled="ExternalHazardComponent" in self.safety_components_cfg,
            selections=self.external_sources,
            provider_definitions=get_registered_api_components(),
            localizer=self.localizer,
        )
        self.applied_source_selection.publish()
        self.state_database = SqliteStateDatabase(
            state_database_path(
                self.runtime_config["app_config"]["fault_evidence"]["state_file"]
            )
        )
        indoor_policy = self.runtime_config["app_config"]["indoor_state_policy"]
        indoor_store = self.__dict__.get("_indoor_state_store")
        if indoor_store is None:
            indoor_store = (self.state_database.store("internal_environment_state", indoor_policy["state_file"], max_bytes=INDOOR_MAX_BYTES)
                            if indoor_policy["enabled"] else InMemoryInternalEnvironmentStateStore())
        # Only an explicitly supplied reviewed bootstrap receipt can prove a
        # virgin installation. Never derive that proof from file absence.
        receipt = self.__dict__.get("_indoor_initial_checkpoint")
        reviewed_launch: str | None = None
        prior_records: dict[str, Any] = {}
        journal_uncertain = False
        try:
            evidence_policy = self.runtime_config["app_config"]["fault_evidence"]
            prior_journal = (self.state_database.store("fault_evidence_state", evidence_policy["state_file"],
                max_bytes=evidence_policy["max_total_bytes"]).load() if evidence_policy["enabled"] else {})
            prior_records = prior_journal.get("records", {})
            if not isinstance(prior_records, dict):
                raise ValueError("Invalid prior journal records")
            conflict = any(key in prior_records for key in INDOOR_FAULTS.values())
            if receipt is not None:
                if not conflict and not indoor_store.load():
                    indoor_store.save(decode_checkpoint(receipt).model_dump(mode="json"))
                    reviewed_launch = current_launch_id()
        except Exception as exc:
            journal_uncertain = True
            self.log(f"Unable to reconcile indoor bootstrap history: {type(exc).__name__}", level="ERROR")
        self.indoor_state_owner = IndoorStateOwner(indoor_store,
            writer=self.__dict__.get("_snapshot_writers", {}).get("internal_environment_state"),
            launch_receipt=reviewed_launch or self.__dict__.get("_indoor_launch_receipt"))
        known_faults = {item.fault_id for item in self.indoor_state_owner.records.values() if item.kind == "known"}
        if journal_uncertain or any(fault_id in prior_records and fault_id not in known_faults for fault_id in INDOOR_FAULTS.values()):
            self.indoor_state_owner.history_unknown = self.indoor_state_owner.gas_history_unknown = True
        self.indoor_state_owner.establish_session()
        self._root_scope.declare("indoor:durability", CancellationKind.TIMER,
            lambda cb: self.run_every(cb, "now", 1), self._drain_indoor_owner, self.cancel_timer)

        # Create access to installation-wide Home Assistant entities.
        self.common_entities: CommonEntities = CommonEntities(
            self, self.common_entities_cfg
        )

        try:
            self._attach_entity_monitor_dependencies()
        except ValueError as exc:
            self.log(f"Invalid app configuration: {exc}", level="ERROR")
            self._set_internal_entity(
                "sensor.safety_app_health",
                "invalid_cfg",
                attributes={"configuration_error": str(exc)},
            )
            self._start_mqtt_reporting()
            return

        # Instantiate provider adapters without starting network activity.
        for component_name, component_cls in get_registered_api_components().items():
            provider_cfg = self.api_components_cfg.get(component_name)
            if not isinstance(provider_cfg, dict) or not provider_cfg.get(
                "enabled", True
            ):
                continue
            http_client = None
            if component_cls.transport_kind == "http":
                provider_host = urlparse(str(provider_cfg["base_url"])).hostname
                if not provider_host:
                    raise ValueError(f"Invalid provider base URL for {component_name}")
                http_client = HttpJsonClient(allowed_hosts={provider_host})
            self.api_modules[component_name] = component_cls(
                provider_config=provider_cfg,
                site_config=self.site_cfg,
                http_client=http_client,
                parameters=provider_cfg["parameters"],
            )

        self.provider_definitions = {
            name: type(adapter) for name, adapter in self.api_modules.items()
            if adapter.data_kind == "live"
        }

        state_provider = HomeAssistantStateProvider.from_environment()
        self.ha_state_reader: HomeAssistantStateReader | None = (
            HomeAssistantStateReader(state_provider)
            if state_provider is not None
            else None
        )

        # Instantiate configured components and collect their runtime contracts.
        for component_name, component_cls in get_registered_components().items():
            if component_name in self.safety_components_cfg:
                component_instance = component_cls(
                    self,
                    self.common_entities,
                    self.event_bus,
                    self.mqtt_entities,
                )
                self.sm_modules[component_name] = component_instance
                if component_name == "EntityMonitorComponent":
                    component_instance.state_reader = self.ha_state_reader

                component_cfg = self.safety_components_cfg[component_name]
                if component_name == "ExternalHazardComponent":
                    component_instance.configure_runtime(
                        runtime_id=self.runtime_id, selections=self.external_sources
                    )
                symptoms_data, recovery_data = component_instance.get_symptoms_data(
                    self.sm_modules, component_cfg
                )

                self.symptoms.update(symptoms_data)
                self.recovery_actions.update(recovery_data)
                inactive_fault_names.update(
                    component_instance.get_inactive_fault_names()
                )
                fault_definitions = getattr(
                    component_instance, "get_fault_definitions", None
                )
                if callable(fault_definitions):
                    for fault_name, fault_config in fault_definitions().items():
                        if fault_name in self.fault_dict:
                            raise ValueError(
                                f"Duplicate fault definition: {fault_name}"
                            )
                        self.fault_dict[fault_name] = fault_config

        persistence_stores = {
            "notification_state",
            "recovery_state",
            "fault_evidence_state",
            "safety_routines",
            "external_hazard_assertions",
            "internal_environment_state",
        }
        indoor_monitor = self.sm_modules.get("InternalEnvironmentalHazardMonitorComponent")
        if indoor_monitor is not None:
            persistence_stores.add("internal_environment_state")
        else:
            self.mqtt_entities.register_sensor("sensor.internal_environment_summary", "Internal environment monitoring",
                state="active_hazard" if any(item.alarm_active for item in self.indoor_state_owner.records.values()) else "degraded",
                attributes=self.indoor_state_owner.projection({}, monitoring_enabled=False, localize=self.localizer.text), icon="mdi:home-alert", entity_category="diagnostic")
        if "HeatingSystemMonitorComponent" in self.sm_modules:
            persistence_stores.add("heating_monitor_state")
        functional_policy = self.runtime_config["app_config"]["calibration"].get(
            "functional_safety"
        )
        if functional_policy:
            persistence_stores.add("periodic_test_state")
            persistence_stores.add("battery_fault_catalog")
            detector_cfg = self.safety_components_cfg.get(
                "InternalEnvironmentalHazardMonitorComponent", {}
            )
            if detector_cfg.get("detectors"):
                persistence_stores.add("detector_test_state")
        self.self_diagnostics = SelfDiagnosticsComponent(
            self,
            self.common_entities,
            self.event_bus,
            self.mqtt_entities,
            {name: adapter for name, adapter in self.api_modules.items() if adapter.data_kind == "live"},
            persistence_stores=frozenset(persistence_stores),
            local_outputs_enabled=any(
                self.notification_cfg["local"].get(key)
                for key in ("light_entity", "alarm_entity")
            ),
            provider_definitions=self.provider_definitions,
        )
        self.sm_modules[self.self_diagnostics.component_name] = self.self_diagnostics
        diagnostic_symptoms, _ = self.self_diagnostics.get_symptoms_data(
            self.sm_modules, {}
        )
        if indoor_monitor is not None:
            self.self_diagnostics.record_app_cause(
                "persistence", indoor_monitor._persistence_error is not None,
                detail="internal_environment_state", operation="load",
            )
        self.symptoms.update(diagnostic_symptoms)
        for fault_name, fault_config in self.self_diagnostics.get_fault_definitions().items():
            if fault_name in self.fault_dict:
                if fault_name != "ExternalDataUnavailable":
                    raise ValueError(f"Duplicate fault definition: {fault_name}")
                existing = self.fault_dict[fault_name]
                if existing.get("level") != 3 or existing.get("category") != "D":
                    raise ValueError("ExternalDataUnavailable must remain a D/L3 fault")
                fault_config = {
                    **existing,
                    **fault_config,
                    "related_sms": list(dict.fromkeys([
                        *existing.get("related_sms", []),
                        *fault_config["related_sms"],
                    ])),
                }
            self.fault_dict[fault_name] = fault_config

        self.functional_safety_monitor = None
        self.detector_test_monitor = None
        self.periodic_test_monitor = None
        if functional_policy:
            detector_cfg = self.safety_components_cfg.get(
                "InternalEnvironmentalHazardMonitorComponent", {}
            )
            detector_names = {
                key: value.get("friendly_name", key)
                for key, value in detector_cfg.get("detectors", {}).items()
                if value.get("enabled", True)
            }
            self.functional_safety_monitor = FunctionalSafetyMonitor(
                self,
                self.event_bus,
                self.mqtt_entities,
                self.runtime_config["user_config"].get("functional_safety", {}),
                functional_policy,
                wan_entity=self.notification_cfg.get("wan_entity"),
                detector_names=detector_names,
                state_provider=state_provider,
                state_reader=self.ha_state_reader,
                stable_release_provider=StableReleaseProvider() if state_provider else None,
                diagnostics_store=JsonFunctionalSafetyDiagnosticsStore(),
            )
            self.sm_modules[self.functional_safety_monitor.component_name] = (
                self.functional_safety_monitor
            )
            symptoms, recoveries = self.functional_safety_monitor.get_symptoms_data(
                self.sm_modules, {}
            )
            self.symptoms.update(symptoms)
            self.recovery_actions.update(recoveries)
            self.fault_dict.update(self.functional_safety_monitor.get_fault_definitions())

        hazard_targets = {
            symptom_id
            for symptom_id, symptom in self.symptoms.items()
            if any(
                fault_config.get("category", "H") == "H"
                and (
                    symptom_id in fault_config.get("related_symptom_ids", ())
                    if fault_config.get("related_symptom_ids")
                    else symptom.sm_name in fault_config.get("related_sms", ())
                )
                for fault_config in self.fault_dict.values()
            )
        }
        self.symptoms.update(self.self_diagnostics.add_targeted_causes(
            hazard_targets, hazard_targets.intersection(self.recovery_actions)
        ))
        self.recovery_actions.update(self.self_diagnostics.get_recovery_actions())

        evidence_cfg = self.runtime_config["app_config"]["fault_evidence"]
        evidence_store = (self.state_database.store("fault_evidence_state", evidence_cfg["state_file"],
                          max_bytes=evidence_cfg["max_total_bytes"]) if evidence_cfg["enabled"] else InMemoryFaultEvidenceStore())
        self.fault_evidence = FaultEvidenceJournal(evidence_store,
            max_records=evidence_cfg["max_records"], max_frame_bytes=evidence_cfg["max_frame_bytes"],
            max_total_bytes=evidence_cfg["max_total_bytes"], log=self.log,
            diagnostics_observer=self.self_diagnostics.record_app_cause,
            schedule_flush=lambda callback, delay: self.run_in(lambda **_: callback(), delay))
        retained_indoor_faults = {record.fault_id for record in self.indoor_state_owner.records.values() if record.alarm_active and record.fault_id}
        retained_indoor_faults.update(fault_id for fault_id in INDOOR_FAULTS.values()
                                     if (self.fault_evidence.get(fault_id) or {}).get("active"))
        if any(item.alarm_active and item.hazard is None for item in self.indoor_state_owner.records.values()):
            retained_indoor_faults.update(INDOOR_FAULTS.values())
        inactive_fault_names.difference_update(retained_indoor_faults)
        for fault_name in inactive_fault_names:
            if self.fault_dict.pop(fault_name, None) is not None:
                self.mqtt_entities.remove_sensor(
                    f"sensor.fault_{fault_name}", remove_legacy_topic=True
                )

        expected_intervals: dict[str, int | None] = {
            name: None for name in self.sm_modules
        }
        if "EntityMonitorComponent" in expected_intervals:
            monitor_cfg = self.safety_components_cfg["EntityMonitorComponent"]
            expected_intervals["EntityMonitorComponent"] = max(
                15, 3 * int(monitor_cfg["evaluation_interval_seconds"])
            )
        if "HeatingSystemMonitorComponent" in expected_intervals and self.safety_components_cfg["HeatingSystemMonitorComponent"].get("systems"):
            expected_intervals["HeatingSystemMonitorComponent"] = max(15, 3 * int(self.safety_components_cfg["HeatingSystemMonitorComponent"]["evaluation_interval_seconds"]))
        if self.functional_safety_monitor is not None:
            expected_intervals["FunctionalSafetyMonitor"] = max(
                15, 3 * int(functional_policy["evaluation_interval_seconds"])
            )
        self.evaluation_progress = EvaluationProgress(expected_intervals)

        # Build fault models from the validated fault configuration.
        self.faults = cfg_pr.get_faults(self.fault_dict)
        try:
            cfg_pr.validate_fault_routes(self.symptoms, self.faults)
        except ValueError as exc:
            self.log(f"Invalid fault routing: {exc}", level="ERROR")
            self._set_internal_entity(
                "sensor.safety_app_health",
                "invalid_cfg",
                attributes={"configuration_error": str(exc)},
            )
            self._start_mqtt_reporting()
            return

        retired_battery_faults: set[str] = set()
        if self.functional_safety_monitor is not None:
            try:
                retired_battery_faults = reconcile_battery_faults(
                    BatteryFaultCatalog(
                        functional_policy["battery_fault_catalog_file"],
                        state_store=self.state_database.store(
                            "battery_fault_catalog",
                            functional_policy["battery_fault_catalog_file"],
                            legacy_validator=BatteryFaultCatalog.validate_snapshot,
                        ),
                    ),
                    self.mqtt_entities,
                    current=self.functional_safety_monitor.get_battery_fault_names(),
                    explicitly_inactive=(
                        self.functional_safety_monitor.get_inactive_fault_names()
                    ),
                    inventory_complete=(
                        self.functional_safety_monitor.battery_inventory_complete()
                    ),
                )
            except (OSError, ValueError, RuntimeError) as exc:
                self.log(
                    f"Unable to reconcile battery fault catalog: {exc}",
                    level="ERROR",
                )
                self.self_diagnostics.record_app_cause(
                    "persistence", True, detail="battery_fault_catalog", operation="reconcile"
                )
            else:
                self.self_diagnostics.record_app_cause(
                    "persistence", False, detail="battery_fault_catalog", operation="reconcile"
                )

        # The former shared door fault has no owner in the per-door contract.
        # Retire retained MQTT discovery/state without publishing a false clear.
        self.mqtt_entities.remove_sensor(
            "sensor.fault_SafetyDoorOpenTimeout", remove_legacy_topic=True
        )
        for retired_fault in (
            "TemperatureMonitoringUnavailable",
            "SafetyDoorMonitoringUnavailable",
            "ExternalOpeningMonitoringUnavailable",
            "CommonInputUnavailable",
            "ExternalHazardDataUnavailable",
            "ExternalProviderUnavailableOpenMeteoWeather",
            "ExternalProviderUnavailableImgwWarnings",
            "ExternalProviderUnavailableOpenMeteoAirQuality",
        ):
            self.mqtt_entities.remove_sensor(
                f"sensor.fault_{retired_fault}", remove_legacy_topic=True
            )

        # Create the fault aggregation and lifecycle manager.
        self.fm: FaultManager = FaultManager(
            self,
            self.sm_modules,
            self.symptoms,
            self.faults,
            self.event_bus,
            self.mqtt_entities,
            evidence_journal=self.fault_evidence,
        )
        self._restore_external_assertions()
        self._restore_indoor_assertions()
        entity_monitor = self.sm_modules.get("EntityMonitorComponent")
        monitor_bindings = (
            entity_monitor.get_degradation_bindings()
            if entity_monitor is not None else ()
        )
        self.degradation = DegradationRegistry(
            self.symptoms,
            self.faults,
            compile_runtime_bindings(
                self.symptoms,
                monitor_bindings,
                faults=self.faults,
                recovery_symptoms=frozenset(self.recovery_actions),
                provider_definitions=self.provider_definitions,
            ),
            on_change=self._on_coverage_changed,
            isolate_invalid=True,
            provider_definitions=self.provider_definitions,
        )
        self.fm.restriction_provider = lambda symptom_id: tuple(
            f"{effect.value}:{cause}"
            for effect in RestrictionEffect
            for cause in self.degradation.causes_for(symptom_id, effect)
        )
        for source, error in self.degradation.binding_errors.items():
            self.log(f"Rejected degradation binding {source}: {error}", level="ERROR")

        persistence_cfg = self.notification_cfg["persistence"]
        self._configure_response_resources()
        notification_state_store = (
            self.state_database.store("notification_state", persistence_cfg["state_file"])
            if persistence_cfg["enabled"]
            else InMemoryNotificationStateStore()
        )

        # Create the localized user-notification lifecycle and transport manager.
        self.notify_man: NotificationManager = NotificationManager(
            self,
            self.notification_cfg,
            localizer=self.localizer,
            state_store=notification_state_store,
            mqtt_entities=self.mqtt_entities,
            diagnostics_observer=self.self_diagnostics.record_app_cause,
            mobile_provider=MobilePushProvider(self, self.notification_cfg["mobile"], dispatcher=self.service_dispatcher),
            local_annunciator=LocalAnnunciator(
                self, self.notification_cfg["local"], self.self_diagnostics.record_app_cause,
                dispatcher=self.service_dispatcher,
                restriction_provider=lambda: self.indoor_state_owner.gas_inhibited,
            ),
            snapshot_writer=self.__dict__.get("_snapshot_writers", {}).get("notification_state"),
        )
        for fault_name in retired_battery_faults:
            self.notify_man.retire_fault(self.fm._generate_fault_tag(fault_name))
        if self.indoor_state_owner.gas_inhibited:
            self.notify_man.inhibit_local_switching("active_or_unresolved_flammable_gas")
        for component in self.sm_modules.values():
            get_inhibitions = getattr(component, "get_output_inhibitions", None)
            if callable(get_inhibitions):
                for reason in get_inhibitions():
                    self.notify_man.inhibit_local_switching(str(reason))
        self.safetyhome_api = SafetyHomeApiGateway(
            self,
            lambda: tuple(self.notify_man.notification_history),
        )
        self.safety_routines = SafetyRoutineRuntime(
            self,
            self.runtime_config["user_config"].get("safety_routines", {}),
            self.state_database.store(
                "safety_routines",
                self.state_database.path.with_name("safety_routines_state.json"),
                max_bytes=8 * 1024 * 1024,
            ),
            self.runtime_config["user_config"].get("localization", {}),
            diagnostics_observer=self.self_diagnostics.record_app_cause,
        )

        # Create the recovery orchestration manager.
        recovery_persistence_cfg = (
            self.runtime_config["user_config"]
            .get("recovery", {})
            .get("persistence", {})
        )
        recovery_state_store = (
            self.state_database.store("recovery_state", recovery_persistence_cfg["state_file"])
            if recovery_persistence_cfg.get("enabled", False)
            else InMemoryRecoveryStateStore()
        )
        self.reco_man: RecoveryManager = RecoveryManager(
            self,
            self.fm,
            self.recovery_actions,
            self.common_entities,
            self.notify_man,
            self.mqtt_entities,
            restore_excluded_symptoms=frozenset(self._external_assertions) | frozenset(
                key for key, symptom in self.symptoms.items()
                if symptom.sm_name in {"sm_ext_weather_exposure", "sm_ext_outdoor_air_quality_exposure"}
            ),
            state_store=recovery_state_store,
            degradation=self.degradation,
            diagnostics_observer=self.self_diagnostics.record_app_cause,
            recovery_observer=self.self_diagnostics.record_recovery,
            command_observer=(
                entity_monitor.record_recovery_command
                if entity_monitor is not None else None
            ),
            timing=self.runtime_config["user_config"].get("recovery", {}).get("timing", {}),
            dispatcher=self.service_dispatcher,
            snapshot_writer=self.__dict__.get("_snapshot_writers", {}).get("recovery_state"),
        )
        for component in self.sm_modules.values():
            if callable(getattr(component, "evaluate_recovery_policy", None)):
                self.reco_man.register_policy_evaluator(component)

        # Wire symptom and fault events in deterministic priority order.
        diagnostic_symptoms = {
            symptom_id
            for symptom_id, symptom in self.symptoms.items()
            if (fault := self.fm.found_mapped_fault(symptom_id, symptom.sm_name)) is not None
            and fault.category.value == "D"
        }
        grace_seconds = int(
            self.runtime_config["app_config"]["calibration"]["entity_monitor"]["startup_grace_seconds"]
        )
        self.startup_grace = StartupGrace(self.event_bus, diagnostic_symptoms, grace_seconds)
        self.fm.evaluation_reporting_deferred = self.startup_grace.defers
        # Internal restrictions use current component-qualified evidence even
        # while operator diagnostic activation waits for startup to settle.
        self.event_bus.subscribe("symptom", self.degradation.observe, priority=-1)
        self.event_bus.subscribe("symptom_observed", self.degradation.observe_hazard)
        self.event_bus.subscribe(
            "evaluation_unavailable", self.degradation.mark_unavailable, priority=-1
        )
        self.event_bus.subscribe("qualified_symptom", self.fm.handle_symptom_event, priority=0)
        self.event_bus.subscribe("qualified_evaluation_pending", self.fm.mark_evaluation_pending, priority=0)
        self.event_bus.subscribe(
            "qualified_evaluation_unavailable", self.fm.mark_evaluation_unavailable, priority=0
        )
        self.event_bus.subscribe(
            "fault", self.notify_man.handle_fault_event, priority=0, isolated=True, scope=self._root_scope
        )
        self.event_bus.subscribe("fault", self.reco_man.handle_fault_event, priority=1,
                                 isolated=True, scope=self._root_scope)

        # Publish system and fault entities before mechanisms begin evaluation.
        self.register_entities()
        self.notify_man.start()
        self.safetyhome_api.start()
        self.safety_routines.start()
        self.reco_man.start()
        if entity_monitor is not None:
            entity_monitor.initialize_recovery_commands(
                self.reco_man.failed_recovery_commands()
            )

        # Initialize state listeners and timers for every safety mechanism.
        self.fm.init_safety_mechanisms()
        external_component = self.sm_modules.get("ExternalHazardComponent")
        if external_component is not None:
            external_component.assertion_observer = self._checkpoint_external_assertion
            external_component.restore_assertions({
                key: value.context for key, value in self._external_assertions.items()
            })

        # Core dispatch is ready before the first H evaluation can propose recovery.
        self.self_diagnostics.record_app_cause("startup", False)
        for symptom_id in hazard_targets.intersection(self.recovery_actions):
            self.self_diagnostics.record_recovery(symptom_id, False)
        for symptom_id, symptom in self.symptoms.items():
            if symptom.module is self.self_diagnostics:
                self.fm.enable_sm(symptom_id, SMState.ENABLED)

        # Enable configured symptoms after all managers and listeners exist.
        self.fm.enable_all_symptoms()
        self.reco_man.resume_command_postconditions()

        if self.functional_safety_monitor is not None:
            self.functional_safety_monitor.start()
            self.periodic_test_monitor = PeriodicTestMonitor(
                self, self.mqtt_entities,
                self.runtime_config["user_config"].get("functional_safety", {}).get("periodic_tests", {"notification_delivery": True}),
                intervals={"notification_delivery": functional_policy["notification_test_interval_days"], "backup_restore": functional_policy["backup_restore_test_interval_days"]},
                state_store=self.state_database.store(
                    "periodic_test_state", functional_policy["periodic_test_state_file"]
                ),
                status_observer=self.functional_safety_monitor.observe_periodic_test,
                diagnostics_observer=self.self_diagnostics.record_app_cause,
            )
            self.periodic_test_monitor.start()
            detector_cfg = self.safety_components_cfg.get(
                "InternalEnvironmentalHazardMonitorComponent", {}
            )
            detectors = detector_cfg.get("detectors", {})
            if detectors:
                test_store = self.state_database.store(
                    "detector_test_state", functional_policy["detector_test_state_file"]
                )
                self.detector_test_monitor = DetectorTestMonitor(
                    self,
                    self.mqtt_entities,
                    detectors,
                    interval_days=functional_policy["detector_test_interval_days"],
                    state_store=test_store,
                    status_observer=self.functional_safety_monitor.observe_detector_test,
                    diagnostics_observer=self.self_diagnostics.record_app_cause,
                )
                self.detector_test_monitor.start()

        # Remote polling starts only after managers, listeners and entities exist.
        if self.ha_state_reader is not None:
            self.ha_state_reader.start(self)
        if self.api_modules:
            runtime_cls = getattr(self, "_external_api_runtime_cls", ExternalApiRuntime)
            self.external_api_runtime = runtime_cls(
                self,
                self.event_bus,
                self.api_modules,
            )
            external_component = self.sm_modules.get("ExternalHazardComponent")
            continuity_probe = getattr(self.external_api_runtime, "continuity_state", None)
            if external_component is not None and callable(continuity_probe):
                external_component.dispatch_continuity_probe = continuity_probe
            self.external_api_runtime.start()

        # Announce successful startup and begin MQTT heartbeat reporting.
        if grace_seconds:
            self._startup_grace_handle = self._owned_root_timeout(
                "startup_grace",
                self._finish_startup_grace, self.startup_grace.snapshot()["remaining_seconds"]
            )
        self._publish_evaluation_progress()
        self._owned_root_interval("evaluation_progress", self._publish_evaluation_progress, 15)
        self._set_internal_entity("sensor.safety_app_health", "running")
        self._start_mqtt_reporting()
        self._coverage_reevaluation_enabled = True
        self._on_coverage_changed()
        self.log("Safety app started successfully", level="DEBUG")

    def _attach_entity_monitor_dependencies(self) -> None:
        """Collect Group B declarations before safety components are created."""

        monitor_cfg = self.safety_components_cfg.get("EntityMonitorComponent")
        if not isinstance(monitor_cfg, dict):
            return
        failure_debounce = int(monitor_cfg["default_failure_debounce_seconds"])
        recovery_debounce = int(monitor_cfg["default_recovery_debounce_seconds"])
        component_overrides = monitor_cfg.get("component_overrides", {})
        if not isinstance(component_overrides, Mapping):
            raise ValueError("Entity Monitor component_overrides must be a mapping")
        dependencies: list[dict[str, Any]] = []
        for component_name, component_cls in get_registered_components().items():
            if component_name == "EntityMonitorComponent":
                continue
            component_cfg = self.safety_components_cfg.get(component_name)
            if component_cfg is None:
                continue
            for dependency in component_cls.get_entity_dependencies(component_cfg):
                dependencies.append(
                    self._calibrate_component_dependency(
                        dependency,
                        component_overrides,
                        failure_debounce,
                        recovery_debounce,
                    )
                )
        for key, entity_id in self.common_entities_cfg.items():
            temperature_entries = self.safety_components_cfg.get(
                "TemperatureComponent", []
            )
            recovery_targets = tuple(
                (symptom_id, "temperature_recovery", str(room), "recovery")
                for entry in temperature_entries
                for room in entry
                for symptom_id in (
                    f"RiskyTemperature{room}",
                    f"RiskyTemperature{room}ForeCast",
                )
            ) if key == "outside_temp" else ()
            checks = (
                {
                    "freshness": {
                        "timestamp_source": "last_reported",
                        "max_silence_seconds": 3600,
                    },
                    "finite_number": {"target": "state"},
                }
                if key == "outside_temp"
                else {}
            )
            dependencies.append(
                self._calibrate_component_dependency(
                    {
                        "key": "Common"
                        + "".join(part.capitalize() for part in str(key).split("_")),
                        "entity_id": entity_id,
                        "owner": "SafetyFunctions",
                        "fault_owner": "component",
                        "fault_name": "InputMonitoringUnavailable",
                        "purpose": f"Shared application entity: {key}",
                        "degradation_targets": recovery_targets,
                        "external_only": not recovery_targets,
                        "checks": checks,
                        "detection_budget_seconds": (
                            4020 if key == "outside_temp" else 30
                        ),
                        "failure_debounce_seconds": (
                            60 if key == "outside_temp" else failure_debounce
                        ),
                    },
                    component_overrides,
                    failure_debounce,
                    recovery_debounce,
                )
            )
        dependency_keys = {str(item["key"]) for item in dependencies}
        unknown_overrides = sorted(set(component_overrides) - dependency_keys)
        if unknown_overrides:
            raise ValueError(
                "Entity Monitor component_overrides reference unknown dependencies: "
                + ", ".join(unknown_overrides)
            )
        for dependency in dependencies:
            budget = dependency.get("detection_budget_seconds")
            if budget is None:
                continue
            dependency_failure_debounce = int(dependency["failure_debounce_seconds"])
            if dependency_failure_debounce > int(budget):
                raise ValueError(
                    f"{dependency['key']} availability debounce exceeds detection budget"
                )
            freshness = dependency.get("checks", {}).get("freshness")
            if freshness and (
                int(freshness["max_silence_seconds"]) + dependency_failure_debounce
                > int(budget)
            ):
                raise ValueError(
                    f"{dependency['key']} freshness and failure debounce "
                    "exceed detection budget"
                )
        monitor_cfg["component_entities"] = dependencies

    @staticmethod
    def _calibrate_component_dependency(
        dependency: Mapping[str, Any],
        overrides: Mapping[str, Any],
        default_failure_debounce: int,
        default_recovery_debounce: int,
    ) -> dict[str, Any]:
        """Apply the system calibration for one Group B dependency."""

        calibrated = {
            **dependency,
            "source": "component",
            "fault_owner": dependency.get("fault_owner", "component"),
            "failure_debounce_seconds": dependency.get(
                "failure_debounce_seconds", default_failure_debounce
            ),
            "recovery_debounce_seconds": dependency.get(
                "recovery_debounce_seconds", default_recovery_debounce
            ),
        }
        override = overrides.get(str(dependency["key"]), {})
        if not isinstance(override, Mapping):
            raise ValueError(
                f"Entity Monitor override for {dependency['key']} must be a mapping"
            )
        override_checks = override.get("checks")
        if override_checks is not None:
            if not isinstance(override_checks, Mapping):
                raise ValueError(
                    f"Entity Monitor checks override for {dependency['key']} "
                    "must be a mapping"
                )
            calibrated["checks"] = {
                **dict(calibrated.get("checks", {})),
                **dict(override_checks),
            }
        for key in (
            "failure_debounce_seconds",
            "recovery_debounce_seconds",
            "detection_budget_seconds",
        ):
            if key in override:
                calibrated[key] = override[key]
        report_timeout = override.get("report_timeout_seconds")
        freshness = calibrated.get("checks", {}).get("freshness")
        if report_timeout is not None:
            if not freshness or not freshness.get("timestamp_source"):
                raise ValueError(
                    f"{dependency['key']} report_timeout_seconds requires a trustworthy timestamp_source"
                )
            calibrated["checks"] = {
                **calibrated.get("checks", {}),
                "freshness": {**freshness, "max_silence_seconds": report_timeout},
            }
            freshness = calibrated["checks"]["freshness"]
        # Preserve the internal acquisition/evaluation allocation when only the
        # report age or qualification duration is changed by the installation.
        original_freshness = dependency.get("checks", {}).get("freshness")
        if (
            freshness and original_freshness
            and dependency.get("detection_budget_seconds") is not None
            and "detection_budget_seconds" not in override
        ):
            overhead = (
                int(dependency["detection_budget_seconds"])
                - int(original_freshness["max_silence_seconds"])
                - int(dependency.get("failure_debounce_seconds", default_failure_debounce))
            )
            calibrated["detection_budget_seconds"] = (
                int(freshness["max_silence_seconds"])
                + int(calibrated["failure_debounce_seconds"])
                + overhead
            )
        return calibrated

    def _initialize_mqtt(self) -> bool:
        """Validate MQTT settings and initialize discovery in an offline state."""
        try:
            if not isinstance(self.args, Mapping):
                raise ValueError("App configuration must be a mapping")
            user_config = self.args.get("user_config", {})
            app_config = self.args.get("app_config", {})
            if not isinstance(user_config, Mapping):
                raise ValueError("user_config must be a mapping")
            if not isinstance(app_config, Mapping):
                raise ValueError("app_config must be a mapping")
            raw_mqtt_cfg = user_config.get("mqtt", {})
            raw_localization_cfg = user_config.get("localization", {})
            if not isinstance(raw_mqtt_cfg, Mapping):
                raise ValueError("user_config.mqtt must be a mapping")
            if not isinstance(raw_localization_cfg, Mapping):
                raise ValueError("user_config.localization must be a mapping")
            strict_validation = bool(
                app_config.get("validation", {}).get("strict_validation", True)
            )
            localization = LocalizationSettings.model_validate(
                dict(raw_localization_cfg),
                context={"strict_validation": strict_validation},
            )

            self.service_dispatcher = ServiceDispatcher(
                self, [ResourceSpec("mqtt", Lane.MQTT, frozenset({"mqtt/publish"}))],
                runtime_id=getattr(self, "runtime_id", None),
                registry=self.__dict__.get("_service_registry"),
            )
            self.service_dispatcher.start()
            self.mqtt_entities = MqttEntityManager(
                self,
                raw_mqtt_cfg,
                strict_validation=strict_validation,
                localization=localization,
                dispatcher=self.service_dispatcher,
            )
            self.mqtt_entities.start()
            self.localizer = self.mqtt_entities.localizer
            self.mqtt_entities.publish_availability(False)
            self._register_health_entity()
            self._set_internal_entity("sensor.safety_app_health", "init")
        except (ValidationError, ValueError) as exc:
            self.log(f"Invalid MQTT configuration: {exc}", level="ERROR")
            return False
        except Exception as exc:
            self.log(f"Unable to initialize MQTT publishing: {exc}", level="ERROR")
            return False
        return True

    def _configure_response_resources(self) -> None:
        """Derive the finite service catalog from validated installation bindings."""
        resources = {
            service: ResourceSpec(service, Lane.MOBILE, frozenset({service}))
            for service in self.notification_cfg["mobile"]["services"]
        }
        local = self.notification_cfg["local"]
        light, alarm = local.get("light_entity"), local.get("alarm_entity")
        if light:
            resources[light] = ResourceSpec(light, Lane.LOCAL, frozenset({"light/turn_on", "light/turn_off"}))
        if alarm:
            resources[alarm] = ResourceSpec(alarm, Lane.LOCAL, frozenset({"alarm_control_panel/alarm_trigger"}))

        def visit(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if key in {"actuator", "actuator_entity_id"} and isinstance(item, str) and item:
                        services = frozenset({
                            RecoveryManager._resolve_entity_action(item, "on"),
                            RecoveryManager._resolve_entity_action(item, "off"),
                        })
                        if item in resources:
                            previous = resources[item]
                            resources[item] = ResourceSpec(item, previous.lane, previous.services | services)
                        else:
                            resources[item] = ResourceSpec(item, Lane.RECOVERY, services)
                    else:
                        visit(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)

        visit(self.safety_components_cfg)
        self.service_dispatcher.add_resources(list(resources.values()))

    def _start_mqtt_reporting(self) -> None:
        """Make MQTT entities available and keep their states fresh."""
        self.mqtt_entities.publish_availability(True)
        diagnostics = getattr(self, "self_diagnostics", None)
        if diagnostics is not None:
            projections = self.mqtt_entities.projections
            diagnostics.record_app_cause(
                "publication", bool(projections and projections.uncertain), detail="mqtt_heartbeat"
            )
        if self.mqtt_entities.settings.heartbeat_seconds > 0:
            self._owned_root_interval("mqtt_heartbeat", self._mqtt_heartbeat, 1)

    def _root_lifecycle(self) -> LifecycleScope:
        """Resolve the root registration owner, including isolated test startup."""
        scope = getattr(self, "_root_scope", None)
        if scope is None:
            scope = LifecycleScope("SafetyFunctions", enabled=True)
            scope.start()
            self._root_scope = scope
        return scope

    def _owned_root_interval(self, key: str, callback: Any, interval: float) -> None:
        """Own periodic application callbacks so termination cannot revive output."""
        self._root_lifecycle().declare(
            key, CancellationKind.TIMER,
            lambda cb: self.run_every(cb, "now", interval), callback, self.cancel_timer,
        )

    def _owned_root_timeout(self, channel: str, callback: Any, delay: float) -> Any:
        """Own one pending root callback per declared purpose."""
        return self._root_lifecycle().schedule(
            channel, lambda cb: self.run_in(cb, delay), callback, self.cancel_timer,
        )

    def _mqtt_heartbeat(self, **_: Any) -> None:
        """Refresh MQTT sensor states used by ``expire_after``."""
        try:
            self.mqtt_entities.publish_heartbeat_batch()
        except Exception as exc:
            self.log(f"MQTT heartbeat publication failed: {exc}", level="ERROR")
            diagnostics = getattr(self, "self_diagnostics", None)
            if diagnostics is not None:
                try:
                    diagnostics.record_app_cause(
                        "publication", True, detail="mqtt_heartbeat"
                    )
                except Exception as routing_error:
                    # The same broken MQTT path cannot carry this D transition.
                    self.log(
                        f"MQTT App Health routing unavailable: {routing_error}",
                        level="ERROR",
                    )
            return
        diagnostics = getattr(self, "self_diagnostics", None)
        if diagnostics is not None:
            projections = self.mqtt_entities.projections
            broker = self.service_dispatcher
            diagnostics.record_app_cause(
                "publication", bool(
                    projections and projections.uncertain or broker.service_failures.get("mqtt")
                    or broker.registry.resource_quarantined("mqtt")
                ), detail="mqtt_heartbeat"
            )

    def record_safety_evaluation(self, component: str, *, success: bool) -> None:
        """Accept evidence only after a component callback has completed."""

        progress = getattr(self, "evaluation_progress", None)
        if progress is not None:
            progress.record(component, success=success)

    def _publish_evaluation_progress(self, **_: Any) -> None:
        """Publish component progress without treating it as input quality."""

        self.startup_grace.finish()
        snapshot = self.evaluation_progress.snapshot()
        self.mqtt_entities.publish_sensor_state(
            "sensor.safety_evaluation_progress",
            snapshot["status"],
            attributes={
                "components": snapshot["components"],
                "startup": self.startup_grace.snapshot(),
                "meaning": "Completed evaluation only; input and delivery quality are separate",
            },
        )

    def _finish_startup_grace(self, **_: Any) -> None:
        """End startup qualification and refresh the frontend phase immediately."""
        self._publish_evaluation_progress()

    def terminate(self) -> None:
        """Publish offline availability during a clean AppDaemon shutdown."""
        self._coverage_reevaluation_enabled = False
        root_scope = getattr(self, "_root_scope", None)
        if root_scope is not None:
            root_scope.stop()
        # Fence every monitor before any component drains its durable owner state.
        # Service leases belong to the process broker, never to these input scopes.
        for component in getattr(self, "sm_modules", {}).values():
            scope = getattr(component, "scope", None)
            if isinstance(scope, LifecycleScope):
                scope.stop()
        routines = getattr(self, "safety_routines", None)
        if routines is not None:
            routines.stop()
        self._startup_grace_handle = self._coverage_reevaluation_handle = None
        state_reader = getattr(self, "ha_state_reader", None)
        if state_reader is not None:
            state_reader.stop()
        detector_monitor = getattr(self, "detector_test_monitor", None)
        periodic_monitor = getattr(self, "periodic_test_monitor", None)
        if periodic_monitor is not None:
            periodic_monitor.stop()
        if detector_monitor is not None:
            detector_monitor.stop()
        external_runtime = getattr(self, "external_api_runtime", None)
        if external_runtime is not None:
            try:
                external_runtime.stop()
            except Exception as exc:
                self.log(f"Unable to stop external API runtime: {exc}", level="ERROR")
        for component in getattr(self, "sm_modules", {}).values():
            stop = getattr(component, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception as exc:
                    self.log(
                        f"Unable to stop safety component {component.component_name}: {exc}",
                        level="ERROR",
                    )
        indoor_owner = getattr(self, "indoor_state_owner", None)
        if isinstance(indoor_owner, IndoorStateOwner):
            indoor_owner.stop()
        notification_manager = getattr(self, "notify_man", None)
        if notification_manager is not None:
            try:
                notification_manager.stop()
            except Exception as exc:
                self.log(
                    f"Unable to persist notification manager state: {exc}",
                    level="ERROR",
                )
        safetyhome_api = getattr(self, "safetyhome_api", None)
        if safetyhome_api is not None:
            try:
                safetyhome_api.stop()
            except Exception as exc:
                self.log(
                    f"Unable to stop SafetyHome API gateway: {exc}",
                    level="ERROR",
                )
        recovery_manager = getattr(self, "reco_man", None)
        if recovery_manager is not None:
            try:
                recovery_manager.stop()
            except Exception as exc:
                self.log(
                    f"Unable to persist recovery manager state: {exc}",
                    level="ERROR",
                )
        fault_evidence = getattr(self, "fault_evidence", None)
        if fault_evidence is not None:
            fault_evidence.stop()
        mqtt_entities = getattr(self, "mqtt_entities", None)
        if mqtt_entities is None:
            return
        try:
            if "sensor.safety_app_health" in mqtt_entities.discovered_entities:
                mqtt_entities.publish_sensor_state(
                    "sensor.safety_app_health", "stopped"
                )
            if "sensor.safetysystem_state" in mqtt_entities.discovered_entities:
                mqtt_entities.publish_sensor_state(
                    "sensor.safetysystem_state", "stopped"
                )
            mqtt_entities.publish_availability(False)
            mqtt_entities.stop()
        except Exception as exc:
            self.log(f"Unable to publish MQTT offline state: {exc}", level="ERROR")
        finally:
            dispatcher = getattr(self, "service_dispatcher", None)
            if dispatcher is not None:
                dispatcher.stop()

    def _register_health_entity(self) -> None:
        """Register the app health entity through MQTT discovery."""
        self.mqtt_entities.register_sensor(
            "sensor.safety_app_health",
            "Safety App Health",
            icon="mdi:heart-pulse",
            entity_category="diagnostic",
        )

    def _set_internal_entity(
        self,
        entity_id: str,
        state: Any,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Publish an internal SafetyFunctions entity state via MQTT."""
        self.mqtt_entities.publish_sensor_state(
            entity_id,
            state,
            attributes=attributes,
        )

    def _on_coverage_changed(self) -> None:
        """Apply scoped restrictions before downstream fault recovery handlers."""

        recovery_manager = getattr(self, "reco_man", None)
        if recovery_manager is not None:
            try:
                recovery_manager.invalidate_restricted_proposals()
            except Exception as exc:
                self.log(f"Unable to withdraw restricted recovery: {exc}", level="ERROR")
        coverage = self._external_coverage_snapshot()
        try:
            self._set_internal_entity(
                "sensor.safety_coverage_state",
                coverage["state"],
                attributes={key: value for key, value in coverage.items() if key != "state"},
            )
        except Exception as exc:
            self.log(f"Unable to publish safety coverage: {exc}", level="ERROR")

        if (
            getattr(self, "_coverage_reevaluation_enabled", False)
            and not getattr(self, "_coverage_reevaluating", False)
            and getattr(self, "_coverage_reevaluation_handle", None) is None
            and self.degradation.pending_reevaluations()
        ):
            self._coverage_reevaluation_handle = self._owned_root_timeout(
                "coverage_reevaluation", self._reevaluate_coverage, 0
            )

    def _reevaluate_coverage(self, **_: Any) -> None:
        """Recheck restored H inputs once, using the normal qualified evaluator."""

        self._coverage_reevaluation_handle = None
        self._coverage_reevaluating = True
        try:
            for symptom_id in self.degradation.pending_reevaluations():
                symptom = self.symptoms[symptom_id]
                if symptom.sm_state != SMState.ENABLED:
                    continue
                evaluation_serial = getattr(symptom.module, "_evaluation_serial", 0)
                try:
                    evaluator = getattr(symptom.module, symptom.sm_name)
                    evaluator(symptom.module.safety_mechanisms[symptom_id])
                    pending_before_success = self.degradation.pending_reevaluations()
                    self.event_bus.publish(
                        "evaluation_succeeded", symptom_id=symptom_id
                    )
                    # A custom evaluator can clear its technical dependency
                    # after publishing H. Recheck once after that clear; never
                    # spin on unavailable input or a pending debounce result.
                    if (
                        symptom_id not in pending_before_success
                        and symptom_id in self.degradation.pending_reevaluations()
                    ):
                        evaluator(symptom.module.safety_mechanisms[symptom_id])
                        self.event_bus.publish(
                            "evaluation_succeeded", symptom_id=symptom_id
                        )
                except Exception as exc:
                    self.event_bus.publish(
                        "evaluation_unavailable", symptom_id=symptom_id
                    )
                    self.event_bus.publish(
                        "evaluation_exception", symptom_id=symptom_id
                    )
                    if getattr(symptom.module, "_evaluation_serial", 0) == evaluation_serial:
                        symptom.module.record_evaluation(success=False)
                    self.log(
                        f"Coverage reevaluation failed for {symptom_id}: {exc}",
                        level="ERROR",
                    )
        finally:
            self._coverage_reevaluating = False


    def _drain_indoor_owner(self, **_kwargs: Any) -> None:
        """Drain storage on the root owner, including a disabled indoor monitor."""
        owner = self.__dict__.get("indoor_state_owner")
        if not isinstance(owner, IndoorStateOwner):
            return
        before = (owner.durable_revision, owner.persistence_error)
        cleared = owner.drain()
        if not cleared and before == (owner.durable_revision, owner.persistence_error):
            return
        monitor = self.sm_modules.get("InternalEnvironmentalHazardMonitorComponent")
        if monitor is not None:
            monitor.apply_durable_clears(cleared)
        else:
            self.mqtt_entities.publish_sensor_state("sensor.internal_environment_summary",
                "active_hazard" if any(item.alarm_active for item in owner.records.values()) else "degraded",
                attributes=owner.projection({}, monitoring_enabled=False, localize=self.localizer.text))
        diagnostics = self.__dict__.get("self_diagnostics")
        if diagnostics is not None:
            diagnostics.record_app_cause("persistence", owner.persistence_error is not None,
                detail="internal_environment_state", operation="save")
        notification = self.__dict__.get("notify_man")
        if notification is not None and owner.gas_inhibited:
            notification.inhibit_local_switching("active_or_unresolved_flammable_gas")

    def _restore_indoor_assertions(self) -> None:
        """Merge trusted indoor retained evidence without replacing other owners."""
        owner = self.indoor_state_owner
        # Missing continuity is a history diagnostic, not evidence of four
        # active incidents. Only actual retained/journal alarm evidence owns H.
        uncertain: set[str] = set()
        for fault_id in INDOOR_FAULTS.values():
            journal = self.fault_evidence.get(fault_id)
            if journal and journal.get("active") and not any(item.fault_id == fault_id and item.alarm_active for item in owner.records.values()):
                if owner.covers_older_journal_activation(fault_id, journal.get("freeze_frame", {})):
                    self.fault_evidence.clear(fault_id)
                else:
                    uncertain.add(fault_id)
        if any(item.kind == "legacy_unattributed" and item.alarm_active for item in owner.records.values()):
            uncertain.update(INDOOR_FAULTS.values())
        self.fm.restore_indoor_assertions(owner.records, uncertain_faults=uncertain)
        self.self_diagnostics.record_app_cause("persistence", owner.persistence_error is not None,
            detail="internal_environment_state", operation="load")

    def _restore_external_assertions(self) -> None:
        """Restore retained real danger before any initial fault state publication."""
        self._external_assertions: dict[str, AssertionRecord] = {}
        self.real_assertion_store: RealAssertionStore | None = None
        load_failed = False
        try:
            self.real_assertion_store = RealAssertionStore(self.state_database)
            self._external_assertions = self.real_assertion_store.records
        except (OSError, ValueError, TypeError) as exc:
            load_failed = True
            self.log(f"Unable to load real external assertions: {exc}", level="ERROR")
        self.self_diagnostics.record_app_cause(
            "persistence", load_failed, detail="external_hazard_assertions", operation="load"
        )
        uncertain: set[str] = set()
        for fault_id in ("ExternalWeatherExposure", "OutdoorAirQualityExposure"):
            evidence = self.fault_evidence.get(fault_id)
            if evidence and evidence.get("active") and not any(
                record.fault_id == fault_id for record in self._external_assertions.values()
            ):
                uncertain.add(fault_id)
        self.fm.restore_external_assertions(self._external_assertions, uncertain_faults=uncertain)

    def _external_coverage_snapshot(self) -> dict[str, Any]:
        """Retained unresolved real danger cannot disappear from global coverage."""
        snapshot = self.degradation.snapshot(limit=32)
        fault_manager = getattr(self, "fm", None)
        if fault_manager is None:
            return snapshot
        records = [record for fault_id in ("ExternalWeatherExposure", "OutdoorAirQualityExposure")
                   for record in fault_manager.retained_assertions(fault_id)]
        unknown = any(
            key.startswith("RetainedUnknown")
            for fault in fault_manager.faults.values()
            for key in fault.evaluation.active_contributors
        )
        if records or unknown:
            if snapshot["state"] in {"FULL", "PARTIAL"}:
                snapshot["state"] = "UNKNOWN"
            snapshot["retained_external_assertion_count"] = len(records)
            snapshot["retained_external_assertions"] = records[:32]
            snapshot["retained_hazard_unknown"] = unknown
        return snapshot

    def _checkpoint_external_assertion(
        self, symptom_id: str, active: bool, context: Mapping[str, Any]
    ) -> bool:
        """Persist real transitions; storage uncertainty can never acknowledge clear."""
        candidate = dict(self._external_assertions)
        try:
            if (not active and symptom_id not in candidate
                    and self.real_assertion_store is not None
                    and symptom_id not in self.real_assertion_store.records):
                # No active in-memory or durable assertion is being cleared.
                # Avoid a write transaction for every already-clear channel;
                # this does not acknowledge recovery of any retained danger.
                self.fm.acknowledge_external_evidence(symptom_id)
                return True
            if active:
                symptom = self.symptoms[symptom_id]
                hazard = str(symptom.parameters["hazard"])
                source = str(context.get("source", ""))
                definition = self.provider_definitions.get(source)
                if definition is None or definition.data_kind != "live":
                    raise ValueError("Real assertion requires a selected live source")
                previous = candidate.get(symptom_id)
                retained_context = {
                    **context,
                    "hazard_code": hazard,
                    "opening_id": str(symptom.parameters["opening_name"]),
                }
                candidate[symptom_id] = AssertionRecord(
                    symptom_id=symptom_id,
                    fault_id="OutdoorAirQualityExposure" if hazard == "outdoor_air_pollution" else "ExternalWeatherExposure",
                    opening=str(symptom.parameters["opening_name"]),
                    hazard=hazard,
                    source=source,
                    asserted_at=previous.asserted_at if previous else datetime.now(timezone.utc).isoformat(),
                    context=retained_context,
                )
            else:
                candidate.pop(symptom_id, None)
            if self.real_assertion_store is None:
                raise OSError("Real assertion checkpoint is unavailable")
            self.real_assertion_store.replace(candidate)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            if active:
                self._external_assertions = candidate
            self.log(f"Unable to persist real external assertion: {exc}", level="ERROR")
            self.self_diagnostics.record_app_cause(
                "persistence", True, detail="external_hazard_assertions", operation="write"
            )
            return active
        self._external_assertions = candidate
        self.fm.acknowledge_external_evidence(symptom_id)
        self.self_diagnostics.record_app_cause(
            "persistence", False, detail="external_hazard_assertions", operation="write"
        )
        return True

    def register_entities(self) -> None:
        """
        Registers all entities required by the Safety Functions app in Home Assistant.

        This includes:
        - Initializing the `sensor.system_state` entity with a default safe state.
        - Registering fault entities for each fault in the system.

        Ensures that the entities are properly initialized and available for monitoring in Home Assistant.
        """
        # Register system state entity
        self.mqtt_entities.register_sensor(
            "sensor.safetysystem_state",
            "System State",
            state=SYSTEM_STATE_BY_FAULT_LEVEL.get(self.fm.get_system_fault_level(), "warning"),
            attributes={
                "attribution": "Managed by SafetyFunction",
                "description": "Overall safety system state based on fault conditions.",
            },
            icon="mdi:shield-check",
            entity_category="diagnostic",
        )

        self.mqtt_entities.register_sensor(
            "sensor.safety_evaluation_progress",
            "Safety Evaluation Progress",
            state="unknown",
            icon="mdi:progress-check",
            entity_category="diagnostic",
        )

        coverage = self._external_coverage_snapshot()
        self.mqtt_entities.register_sensor(
            "sensor.safety_coverage_state",
            "Safety Coverage",
            state=coverage["state"],
            attributes={key: value for key, value in coverage.items() if key != "state"},
            icon="mdi:shield-search",
            entity_category="diagnostic",
        )

        # Register fault entities
        for name, fault in self.faults.items():
            contributors = sorted(
                symptom_id
                for symptom_id, symptom in self.symptoms.items()
                if (
                    symptom_id in fault.related_symptom_ids
                    if fault.related_symptom_ids
                    else symptom.sm_name in fault.related_symptoms
                )
            )
            evidence = self.fault_evidence.get(name)
            evidence_attributes = {}
            if evidence is not None:
                evidence_attributes = {
                    "freeze_frame": evidence["freeze_frame"],
                }
            self.mqtt_entities.register_sensor(
                "sensor.fault_" + name,
                fault.friendly_name,
                state=fault.evaluation.status.value,
                attributes={
                    "attribution": "Managed by SafetyFunction",
                    "description": f"Status of the {name} fault.",
                    "level": f"level_{fault.level}",
                    "active": fault.evaluation.active,
                    "shadowed_by": [],
                    "latched": fault.evaluation.latched,
                    "category": fault.category.value,
                    "fault_id": name,
                    "contributors": contributors[:64],
                    "contributors_total": len(contributors),
                    "active_contributors": sorted(fault.evaluation.active_contributors)[:64],
                    "active_contributors_total": len(fault.evaluation.active_contributors),
                    "retained_assertions": self.fm.retained_assertions(name),
                    **self.fm.retained_assertion_counts(name),
                    "retained_hazard_unknown": any(
                        key.startswith("RetainedUnknown") for key in fault.evaluation.active_contributors
                    ),
                    **evidence_attributes,
                },
                icon="mdi:alert-outline",
                entity_category="diagnostic",
            )
