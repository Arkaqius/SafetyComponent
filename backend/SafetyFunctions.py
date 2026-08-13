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

from typing import Any, Dict, Mapping
from urllib.parse import urlparse

import appdaemon.plugins.hass.hassapi as hass
from pydantic import ValidationError

from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)
from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.derivative_monitor import DerivativeMonitor
from components.core.localization import LocalizationSettings
from components.core.mqtt_entity_manager import MqttEntityManager
from components.external_apis import (
    ExternalApiRuntime,
    HttpJsonClient,
    get_registered_api_components,
)
from components.faults_manager import cfg_parser as cfg_pr
from components.faults_manager.fault_manager import FaultManager
from components.notification_manager.notification_manager import NotificationManager
from components.recovery_manager.recovery_manager import RecoveryManager
from components.safetycomponents.core.safety_component import (
    get_registered_components,
)
import components.safetycomponents.temperature.temperature_component  # noqa: F401 - component registration
import components.safetycomponents.safety_doors.safety_doors_component  # noqa: F401 - component registration
import components.safetycomponents.external_hazard.external_hazard_component  # noqa: F401 - component registration
import components.safetycomponents.entity_monitor.entity_monitor_component  # noqa: F401 - component registration
from components.core.types_common import Symptom, RecoveryAction

DEBUG = False

if DEBUG:
    from remote_pdb import RemotePdb  # type: ignore



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
        if not self._initialize_mqtt():
            self.stop_app(self.name)
            return

        try:
            self.args: Dict[str, Any] = AppCfgValidator.validate(
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

        if DEBUG:
            RemotePdb("172.30.33.4", 5050).set_trace()

        # Prepare shared runtime state and event infrastructure.
        self.sm_modules: dict = {}
        self.api_modules: dict = {}
        self.symptoms: dict[str, Symptom] = {}
        self.recovery_actions: dict[str, RecoveryAction] = {}
        self.derivative_monitor = DerivativeMonitor(self, self.mqtt_entities)
        self.event_bus = EventBus()

        # Extract the validated configuration sections used at runtime.
        self.fault_dict: dict = self.args["app_config"]["faults"]
        self.safety_components_cfg: dict = self.args["user_config"]["safety_components"]
        self.notification_cfg: dict = self.args["user_config"]["notification"]
        self.common_entities_cfg: dict = self.args["user_config"]["common_entities"]
        self.api_components_cfg: dict = self.args["user_config"].get(
            "api_components", {}
        )
        self.site_cfg: dict = self.args["user_config"].get("site", {})

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
            if not isinstance(provider_cfg, dict) or not provider_cfg.get("enabled", True):
                continue
            provider_host = urlparse(str(provider_cfg["base_url"])).hostname
            if not provider_host:
                raise ValueError(f"Invalid provider base URL for {component_name}")
            self.api_modules[component_name] = component_cls(
                provider_config=provider_cfg,
                site_config=self.site_cfg,
                http_client=HttpJsonClient(allowed_hosts={provider_host}),
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

                component_cfg = self.safety_components_cfg[component_name]
                symptoms_data, recovery_data = component_instance.get_symptoms_data(
                    self.sm_modules, component_cfg
                )

                self.symptoms.update(symptoms_data)
                self.recovery_actions.update(recovery_data)
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

        # Build fault models from the validated fault configuration.
        self.faults = cfg_pr.get_faults(self.fault_dict)

        # Create the fault aggregation and lifecycle manager.
        self.fm: FaultManager = FaultManager(
            self,
            self.sm_modules,
            self.symptoms,
            self.faults,
            self.event_bus,
            self.mqtt_entities,
        )

        # Create the localized user-notification manager.
        self.notify_man: NotificationManager = NotificationManager(
            self, self.notification_cfg, localizer=self.localizer
        )

        # Create the recovery orchestration manager.
        self.reco_man: RecoveryManager = RecoveryManager(
            self,
            self.fm,
            self.recovery_actions,
            self.common_entities,
            self.notify_man,
            self.mqtt_entities,
        )
        for component in self.sm_modules.values():
            if callable(getattr(component, "evaluate_recovery_policy", None)):
                self.reco_man.register_policy_evaluator(component)

        # Wire symptom and fault events in deterministic priority order.
        self.event_bus.subscribe(
            "symptom", self.fm.handle_symptom_event, priority=0
        )
        self.event_bus.subscribe(
            "fault", self.notify_man.handle_fault_event, priority=0
        )
        self.event_bus.subscribe(
            "fault", self.reco_man.handle_fault_event, priority=1
        )

        # Publish system and fault entities before mechanisms begin evaluation.
        self.register_entities()

        # Initialize state listeners and timers for every safety mechanism.
        self.fm.init_safety_mechanisms()

        # Enable configured symptoms after all managers and listeners exist.
        self.fm.enable_all_symptoms()

        # Remote polling starts only after managers, listeners and entities exist.
        if self.api_modules:
            runtime_cls = getattr(self, "_external_api_runtime_cls", ExternalApiRuntime)
            self.external_api_runtime = runtime_cls(
                self,
                self.event_bus,
                self.api_modules,
            )
            self.external_api_runtime.start()

        # Announce successful startup and begin MQTT heartbeat reporting.
        self._set_internal_entity("sensor.safety_app_health", "running")
        self._start_mqtt_reporting()
        self.log("Safety app started successfully", level="DEBUG")

    def _attach_entity_monitor_dependencies(self) -> None:
        """Collect Group B declarations before safety components are created."""

        monitor_cfg = self.safety_components_cfg.get("EntityMonitorComponent")
        if not isinstance(monitor_cfg, dict):
            return
        failure_debounce = int(monitor_cfg["default_failure_debounce_seconds"])
        recovery_debounce = int(monitor_cfg["default_recovery_debounce_seconds"])
        dependencies: list[dict[str, Any]] = []
        for component_name, component_cls in get_registered_components().items():
            if component_name == "EntityMonitorComponent":
                continue
            component_cfg = self.safety_components_cfg.get(component_name)
            if component_cfg is None:
                continue
            for dependency in component_cls.get_entity_dependencies(component_cfg):
                dependencies.append(
                    {
                        **dependency,
                        "source": "component",
                        "fault_owner": "entity_monitor",
                        "failure_debounce_seconds": failure_debounce,
                        "recovery_debounce_seconds": recovery_debounce,
                    }
                )
        for key, entity_id in self.common_entities_cfg.items():
            checks = (
                {
                    "freshness": {
                        "timestamp_source": "last_updated",
                        "max_silence_seconds": 3600,
                    },
                    "finite_number": {"target": "state"},
                }
                if key == "outside_temp"
                else {}
            )
            dependencies.append(
                {
                    "key": "Common" + "".join(
                        part.capitalize() for part in str(key).split("_")
                    ),
                    "entity_id": entity_id,
                    "owner": "SafetyFunctions",
                    "purpose": f"Shared application entity: {key}",
                    "checks": checks,
                    "detection_budget_seconds": (
                        3615 if key == "outside_temp" else 30
                    ),
                    "source": "component",
                    "fault_owner": "entity_monitor",
                    "failure_debounce_seconds": failure_debounce,
                    "recovery_debounce_seconds": recovery_debounce,
                }
            )
        for dependency in dependencies:
            budget = dependency.get("detection_budget_seconds")
            if budget is None:
                continue
            if failure_debounce > int(budget):
                raise ValueError(
                    f"{dependency['key']} availability debounce exceeds detection budget"
                )
            freshness = dependency.get("checks", {}).get("freshness")
            if freshness and (
                int(freshness["max_silence_seconds"]) + failure_debounce
                > int(budget)
            ):
                raise ValueError(
                    f"{dependency['key']} freshness and failure debounce "
                    "exceed detection budget"
                )
        monitor_cfg["component_entities"] = dependencies

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
            strict_validation = bool(app_config.get("strict_validation", True))
            localization = LocalizationSettings.model_validate(
                dict(raw_localization_cfg),
                context={"strict_validation": strict_validation},
            )

            self.mqtt_entities = MqttEntityManager(
                self,
                raw_mqtt_cfg,
                strict_validation=strict_validation,
                localization=localization,
            )
            self.localizer = self.mqtt_entities.localizer
            self.mqtt_entities.publish_availability(False)
            self.mqtt_entities.cleanup_legacy_discovery_topics()
            self._register_health_entity()
            self._set_internal_entity("sensor.safety_app_health", "init")
        except (ValidationError, ValueError) as exc:
            self.log(f"Invalid MQTT configuration: {exc}", level="ERROR")
            return False
        except Exception as exc:
            self.log(f"Unable to initialize MQTT publishing: {exc}", level="ERROR")
            return False
        return True

    def _start_mqtt_reporting(self) -> None:
        """Make MQTT entities available and keep their states fresh."""
        self.mqtt_entities.publish_availability(True)
        if self.mqtt_entities.settings.heartbeat_seconds > 0:
            self.run_every(
                self._mqtt_heartbeat,
                "now",
                self.mqtt_entities.settings.heartbeat_seconds,
            )

    def _mqtt_heartbeat(self, **_: Any) -> None:
        """Refresh MQTT sensor states used by ``expire_after``."""
        self.mqtt_entities.publish_heartbeat()

    def terminate(self) -> None:
        """Publish offline availability during a clean AppDaemon shutdown."""
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
        except Exception as exc:
            self.log(f"Unable to publish MQTT offline state: {exc}", level="ERROR")

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
            state="no_faults",
            attributes={
                "attribution": "Managed by SafetyFunction",
                "description": "Overall safety system state based on fault conditions.",
            },
            icon="mdi:shield-check",
            entity_category="diagnostic",
        )

        # Register fault entities
        for name, fault in self.faults.items():
            self.mqtt_entities.register_sensor(
                "sensor.fault_" + name,
                fault.friendly_name,
                state="Not_tested",
                attributes={
                    "attribution": "Managed by SafetyFunction",
                    "description": f"Status of the {name} fault.",
                    "level": f"level_{fault.level}",
                },
                icon="mdi:alert-outline",
                entity_category="diagnostic",
            )
