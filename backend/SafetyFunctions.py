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

import appdaemon.plugins.hass.hassapi as hass
from pydantic import ValidationError

from components.app_config_validator.app_cfg_validator import (
    AppCfgValidationError,
    AppCfgValidator,
)
from components.core.common_entities import CommonEntities
from components.core.event_bus import EventBus
from components.core.derivative_monitor import DerivativeMonitor
from components.core.mqtt_entity_manager import MqttEntityManager
from components.faults_manager import cfg_parser as cfg_pr
from components.faults_manager.fault_manager import FaultManager
from components.notification_manager.notification_manager import NotificationManager
from components.recovery_manager.recovery_manager import RecoveryManager
from components.safetycomponents.core.safety_component import (
    SafetyComponent,
    get_registered_components,
)
import components.safetycomponents.temperature.temperature_component  # side-effect registration
from components.core.types_common import Fault, Symptom, RecoveryAction

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

        # 10.1. Internal storage for safety components
        self.sm_modules: dict = {}
        self.symptoms: dict[str, Symptom] = {}
        self.recovery_actions: dict[str, RecoveryAction] = {}
        self.derivative_monitor = DerivativeMonitor(self, self.mqtt_entities)
        self.event_bus = EventBus()

        # 10.2. Get configuration data
        self.fault_dict: dict = self.args["app_config"]["faults"]
        self.safety_components_cfg: dict = self.args["user_config"]["safety_components"]
        self.notification_cfg: dict = self.args["user_config"]["notification"]
        self.common_entities_cfg: dict = self.args["user_config"]["common_entities"]

        # 20. Initialize common entities
        self.common_entities: CommonEntities = CommonEntities(
            self, self.common_entities_cfg
        )

        # 30. Initialize components and collect symptoms/recovery actions
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

        # 40. Get faults data
        self.faults = cfg_pr.get_faults(self.fault_dict)

        # 50. Initialize fault manager
        self.fm: FaultManager = FaultManager(
            self,
            self.sm_modules,
            self.symptoms,
            self.faults,
            self.event_bus,
            self.mqtt_entities,
        )

        # 60. Initialize notification manager
        self.notify_man: NotificationManager = NotificationManager(
            self, self.notification_cfg
        )

        # 70. Initialize recovery manager
        self.reco_man: RecoveryManager = RecoveryManager(
            self,
            self.fm,
            self.recovery_actions,
            self.common_entities,
            self.notify_man,
            self.mqtt_entities,
        )

        # 80. Register callbacks for faults
        self.event_bus.subscribe(
            "symptom", self.fm.handle_symptom_event, priority=0
        )
        self.event_bus.subscribe(
            "fault", self.notify_man.handle_fault_event, priority=0
        )
        self.event_bus.subscribe(
            "fault", self.reco_man.handle_fault_event, priority=1
        )

        # 90. Event-driven flow means components publish to the bus instead.

        # 100. Register entities for faults
        self.register_entities()

        # 110. Initialize safety mechanisms
        self.fm.init_safety_mechanisms()

        # 120. Enable all symptoms
        self.fm.enable_all_symptoms()

        # 130 Emit config and set state to running
        self._set_internal_entity("sensor.safety_app_health", "running")
        self._start_mqtt_reporting()
        self.log("Safety app started successfully", level="DEBUG")

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
            if not isinstance(raw_mqtt_cfg, Mapping):
                raise ValueError("user_config.mqtt must be a mapping")
            strict_validation = bool(app_config.get("strict_validation", True))

            self.mqtt_entities = MqttEntityManager(
                self,
                raw_mqtt_cfg,
                strict_validation=strict_validation,
            )
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
        mqtt_entities = getattr(self, "mqtt_entities", None)
        if mqtt_entities is None:
            return
        try:
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
            state="safe",
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
                f"Fault: {name}",
                state="Not_tested",
                attributes={
                    "attribution": "Managed by SafetyFunction",
                    "description": f"Status of the {name} fault.",
                    "level": f"level_{fault.level}",
                },
                icon="mdi:alert-outline",
                entity_category="diagnostic",
            )
