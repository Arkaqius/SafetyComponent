# Software Safety Requirements Document — SafetyComponent

**Document ID:** SAF-SWR-SSRD

**Version:** 0.3.0

**Status:** Working baseline aligned with implementation

**Last updated:** 2026-08-02

## 1. Purpose and scope

This Software Safety Requirements Document (SSRD) defines the implemented
software behaviour of the AppDaemon-based SafetyComponent. It refines the
system requirements and hazards described in:

- `SafetyConcept - HARA.md`;
- `SafetyConcept - SYS.md`;
- the deployed configuration in `backend/app_cfg.yaml`.

The software in scope includes configuration validation, component lifecycle,
temperature and safety-door monitoring, fault aggregation, notification and
recovery handling, MQTT discovery/state publication, localization metadata,
and backend verification. The web frontend consumes the published contract but
does not implement safety decisions.

## 2. Operating context

SafetyComponent runs as the `SafetyFunctions` AppDaemon application connected
to Home Assistant. It reads Home Assistant entities, schedules evaluations,
publishes internal entities over MQTT discovery, calls explicitly allow-listed
Home Assistant services for recoveries, and sends user notifications.

The implementation assumes:

- Home Assistant, AppDaemon, and the MQTT broker are available;
- configured entity IDs and area IDs identify the intended installation
  objects;
- severity level `1` is the highest severity and level `4` the lowest;
- raw entity IDs and runtime state codes form a stable machine contract;
- translated names and labels are presentation metadata, not control inputs.

## 3. Software architecture

| Element | Responsibility |
| --- | --- |
| `SafetyFunctions` | Validate configuration, create managers/components, wire events, start and stop MQTT reporting. |
| `AppCfgValidator` | Validate the complete Pydantic configuration model, component schemas, entity syntax/existence, and Home Assistant areas. |
| `SafetyComponent` | Common safety-mechanism lifecycle, listeners, reevaluation, and debounce handling. |
| `TemperatureComponent` | Direct and forecast low/high temperature evaluation and window recovery proposals. |
| `SafetyDoorsComponent` | Per-door open-duration monitoring with optional state gating. |
| `ExternalHazardComponent` *(planned)* | Correlate normalized external hazards with configured openings, create notification-only symptoms, and maintain advice-inhibition state. |
| External API Components *(planned)* | One isolated component per remote API; validate and normalize provider data without creating faults or actions. |
| `DerivativeMonitor` | Calculate and publish first- and second-order temperature derivatives. |
| `FaultManager` | Aggregate symptoms, preserve multi-symptom fault context, and publish fault/system state. |
| `NotificationManager` | Maintain one notification per fault and refresh its human-readable content. |
| `RecoveryManager` | Determine, execute, and confirm supported recovery actions. |
| `MqttEntityManager` | MQTT discovery, state, attributes, availability, retained cleanup, and heartbeat. |
| `Localizer` | Translate presentation text while retaining stable internal codes. |

Event ordering is deterministic: the FaultManager processes symptom events;
for fault events, NotificationManager runs before RecoveryManager.

## 4. Software safety requirements

### 4.1 Configuration and initialization

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-CFG-001 | The application shall validate the complete configuration before enabling any safety mechanism. | `AppCfgValidator.validate` |
| SWR-CFG-002 | An enabled component shall have a registered implementation and a valid component-specific configuration. | component registry and schemas |
| SWR-CFG-003 | Strict mode shall reject unknown configuration fields; compatibility mode shall retain them and log their paths. | `StrictBaseModel`, `log_extra_keys` |
| SWR-CFG-004 | Entity IDs shall be syntax-checked and, when configured, checked for existence in Home Assistant. | `AppCfgValidator` |
| SWR-CFG-005 | Every configured temperature room and safety door shall provide an `area_id`. | temperature and Safety Doors schemas |
| SWR-CFG-006 | At startup the application shall resolve every configured `area_id` with Home Assistant `area_name(...)`; an unknown area shall invalidate the configuration. | `AppCfgValidator._resolve_area_names` |
| SWR-CFG-007 | A validation failure shall publish health state `invalid_cfg`, include `configuration_error`, keep MQTT reporting available for diagnosis, and shall not enable safety mechanisms. | `SafetyFunctions.initialize` |
| SWR-CFG-008 | Successful initialization shall publish health state `running` only after managers, event subscriptions, entities, and mechanisms are initialized and enabled. | `SafetyFunctions.initialize` |

### 4.2 Temperature monitoring

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-TEMP-001 | Each configured room shall evaluate direct low temperature (`sm_tc_1`), forecast low temperature (`sm_tc_2`), direct high temperature (`sm_tc_3`), and forecast high temperature (`sm_tc_4`). | `TemperatureComponent` |
| SWR-TEMP-002 | Direct mechanisms shall compare the current numeric sensor value with the configured low or high threshold. | `sm_tc_1`, `sm_tc_3` |
| SWR-TEMP-003 | Forecast mechanisms shall calculate a forecast from the current temperature, first derivative, and configured forecast timespan. | `sm_tc_2`, `sm_tc_4` |
| SWR-TEMP-004 | Missing, non-numeric, `unknown`, or `unavailable` input shall not create a new temperature fault from invalid data. | `_get_temperature_value` and mechanism callbacks |
| SWR-TEMP-005 | Mechanism results shall use configured debounce and reevaluation timing before fault lifecycle changes are emitted. | `SafetyComponent`, temperature calibration |
| SWR-TEMP-006 | The DerivativeMonitor shall publish only derivative measurements (`_rate` in °C/min and `_rateofrate` in °C/min²); it shall not own temperature safety limits. | `DerivativeMonitor` |
| SWR-TEMP-007 | Each room shall expose its low and high configured limits as separate diagnostic MQTT sensors named `<source>_low_threshold` and `<source>_high_threshold`. | `TemperatureComponent._register_temperature_threshold_entities` |
| SWR-TEMP-008 | Threshold sensors shall identify the source entity, threshold type, `area_id`, and current Home Assistant area name. | threshold sensor attributes |
| SWR-TEMP-009 | Low-temperature symptoms shall provide a window recovery proposal when a window sensor or supported cover actuator is configured. | `RiskyTemperature_recovery` |

### 4.3 Safety Doors monitoring

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-DOOR-001 | Every configured door or gate shall have an independent `timeout_seconds` value, inherited from component defaults only when no per-door override is supplied. | Safety Doors schema |
| SWR-DOOR-002 | A continuously open door shall set its symptom only after its own configured timeout expires. | `sm_safety_door_open_timeout` |
| SWR-DOOR-003 | Closing a door shall cancel its pending timer and clear its symptom. | Safety Doors runtime |
| SWR-DOOR-004 | An unavailable or unsupported door state shall publish diagnostic state `unavailable` and shall not create a new open-timeout fault. | `_read_door_state` and evaluation flow |
| SWR-DOOR-005 | A configured condition shall monitor its entity alongside the door; pass states enable timing and blocked states suspend timing and clear the symptom. | `SafetyDoorCondition`, Safety Doors runtime |
| SWR-DOOR-006 | An unavailable or unsupported condition state shall suspend timing and shall not create a new fault. | `_read_condition_state` |
| SWR-DOOR-007 | Each Safety Door MQTT entity shall publish door state, elapsed and remaining time, source entity, timeout, condition diagnostics, `area_id`, and resolved area name. | `_publish_door_state` |
| SWR-DOOR-008 | The current installation calibration shall use 180 s for `GarageGate`, 180 s for `ExternalGate`, 120 s for `LivingRoomTerraceDoor`, and 900 s for `GarageDoor`. | `backend/app_cfg.yaml` |
| SWR-DOOR-009 | `LivingRoomTerraceDoor` monitoring shall pass only while `sensor.home_monitor_occupancy` is `empty` and shall be blocked while it is `occupied`. | `backend/app_cfg.yaml` |

### 4.4 Fault aggregation and system state

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-FLT-001 | A fault shall aggregate all related active symptoms rather than replace the previous contribution from the same fault. | `FaultManager` merged symptom context |
| SWR-FLT-002 | When one symptom clears but another related symptom remains set, the fault shall remain set and its notification context shall be refreshed. | `FaultManager._clear_fault` |
| SWR-FLT-003 | The highest active severity shall be the minimum numeric active fault level. | `get_system_fault_level` |
| SWR-FLT-004 | With no active faults, system state shall be `no_faults` and `highest_fault_level` shall be `0`. This state describes fault absence, not application health. | `SYSTEM_STATE_BY_FAULT_LEVEL` |
| SWR-FLT-005 | With active faults, system state shall be `emergency`, `hazard`, `warning`, or `information` for levels 1 through 4 respectively. | `SYSTEM_STATE_BY_FAULT_LEVEL` |
| SWR-FLT-006 | Application health shall be represented independently by `sensor.safety_app_health`. | `SafetyFunctions` |
| SWR-FLT-007 | Fault entities shall publish stable raw lifecycle states `Set`, `Shadowed`, `Cleared`, and `Not_tested`. | `FaultManager` |

### 4.5 Notifications and recovery

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-NOT-001 | Notifications shall use the configured fault friendly name and resolved user-facing location. | `FaultManager`, `NotificationManager` |
| SWR-NOT-002 | A fault shall use one stable notification tag throughout its lifecycle. | fault tag generation and `active_notification` |
| SWR-NOT-003 | A repeated SET for an active fault shall update the current base message instead of creating a second notification. | `NotificationManager.active_notification` |
| SWR-NOT-004 | Distinct recovery guidance accumulated for the same active fault shall be retained and shown once under a localized guidance heading. | `_recovery_messages` |
| SWR-NOT-005 | Clearing a fault shall publish a friendly cleared message using the same tag. | `cleared_notification` |
| SWR-REC-001 | Recovery commands shall be limited to explicitly supported Home Assistant entity domains and services. | `RecoveryManager._resolve_entity_action` |
| SWR-REC-002 | A recovery action shall verify the requested postcondition and shall report failure or timeout instead of assuming success. | RecoveryManager confirmation flow |
| SWR-REC-003 | Recovery entities shall expose stable raw states `TO_PERFORM` and `DO_NOT_PERFORM` plus localized `state_label`. | RecoveryManager and Localizer |

### 4.6 Localization contract

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-LOC-001 | English (`en`), Polish (`pl`), and German (`de`) shall be supported installation languages. | `LocalizationSettings`, `_TRANSLATIONS` |
| SWR-LOC-002 | Entity IDs, MQTT topic identifiers, fault identifiers, event codes, and raw lifecycle states shall remain language-independent. | backend runtime contract |
| SWR-LOC-003 | Localization shall apply to MQTT discovery names, `state_label`, notification text, recovery guidance, and dynamic threshold/recovery entity names. | Localizer consumers |
| SWR-LOC-004 | Home Assistant area names shall be used as returned by Home Assistant and shall not be translated or reconstructed from internal configuration keys. | area resolution flow |
| SWR-LOC-005 | Missing translation keys shall fall back to English and then to the key itself without changing safety logic. | `Localizer.text`, `state_label` |

### 4.7 MQTT lifecycle and diagnostics

| ID | Requirement | Implemented by |
| --- | --- | --- |
| SWR-MQTT-001 | Internal entities shall use MQTT discovery with stable unique IDs and default entity IDs. | `MqttEntityManager` |
| SWR-MQTT-002 | Discovery payloads may be retained; transient state and attribute payloads shall not be retained. | MQTT settings and publisher |
| SWR-MQTT-003 | Startup shall clear configured legacy discovery topics and stale retained state before publishing current state. | MQTT startup flow |
| SWR-MQTT-004 | Availability shall be `offline` during initialization and `online` after successful startup or diagnostic invalid-configuration startup. | `SafetyFunctions` |
| SWR-MQTT-005 | The heartbeat period shall remain shorter than `expire_after` so unchanged entities do not become unavailable. | `heartbeat_seconds`, `expire_after` |
| SWR-MQTT-006 | Application termination shall publish health and system state `stopped` before publishing availability `offline`. | `SafetyFunctions.terminate` |

### 4.8 Planned External Hazard Monitoring — not implemented

This subsection records the proposed implementation contract without claiming
that the feature exists in the current software. The detailed design is in
[`External Hazard Monitoring - Architecture.md`](../features/External%20Hazard%20Monitoring%20-%20Architecture.md).

| ID | Planned requirement | Planned implementation |
| --- | --- | --- |
| SWR-EXT-001 | The feature shall use separate `OpenMeteoWeatherApiComponent`, `ImgwWarningsApiComponent`, `GiosAirQualityApiComponent`, `OpenMeteoAirQualityApiComponent`, and `PaaRadiationApiComponent` classes. | external API component registry |
| SWR-EXT-002 | API Components shall have independent schemas, polling schedules, caches, failure counters, health, and contract tests. | `components/external_apis/*` |
| SWR-EXT-003 | API Components shall not inherit from `SafetyComponent` and shall not create symptoms, faults, notifications, recovery actions, or actuator calls. | `ExternalApiComponent` protocol |
| SWR-EXT-004 | Network work shall run outside the serialized safety-decision callback and results shall return through a bounded queue for ordered EventBus publication. | `ExternalApiRuntime` |
| SWR-EXT-005 | `ExternalHazardComponent` shall be the only Safety Component in this feature and shall own household thresholds, freshness, cross-provider policy, opening correlation, aggregation, and notification context. | `ExternalHazardComponent` |
| SWR-EXT-006 | Frost, wind/gust, rain/storm, and outdoor-pollution exposure symptoms shall require both applicable valid hazard evidence and an open configured aperture. | external hazard policy mechanisms |
| SWR-EXT-007 | An official ionizing-radiation warning shall notify regardless of aperture state; open apertures shall be context only. | radiation authority mechanism |
| SWR-EXT-008 | Raw radiation measurements shall not create the confirmed radiation-alert fault; any enabled anomaly warning shall be explicitly unconfirmed and corroborated by configured policy. | radiation anomaly mechanism |
| SWR-EXT-009 | Provider timeout, stale data, or schema error shall not clear an active condition and shall publish provider degradation diagnostics. | provider health and clear policy |
| SWR-EXT-010 | Version 1 shall be notification-only, shall register no executable recovery action, and shall make no Home Assistant actuator service call. | negative actuation boundary |
| SWR-EXT-011 | Same-fault updates shall retain all active hazards/openings and refresh one notification tag using friendly names and localized area labels. | FaultManager and NotificationManager integration |
| SWR-EXT-012 | External pollution, damaging wind, storm, or confirmed sheltering policy shall inhibit contradictory advice to open external apertures. | `RecoveryPolicyEvaluator` integration |
| SWR-EXT-013 | PAA radiation integration shall remain disabled until a machine-readable contract and fixtures are explicitly reviewed. | `PaaRadiationApiComponent` feature gate |

## 5. Non-functional requirements

| ID | Requirement |
| --- | --- |
| SWR-NFR-001 | Public modules, classes, and functions shall use type hints and purpose-oriented docstrings. |
| SWR-NFR-002 | Safety decisions shall be deterministic for identical validated configuration, entity states, and timestamps. |
| SWR-NFR-003 | Failure to read optional diagnostics shall not crash AppDaemon or set a false safety condition. |
| SWR-NFR-004 | Exceptions that prevent configuration or runtime actions shall be logged with enough context to identify the component and entity. |
| SWR-NFR-005 | Backend application line coverage (`backend/components` and `backend/SafetyFunctions.py`) shall remain at least 90%. Generated test stubs, tests, templates, and deployment utilities are excluded from this metric. |
| SWR-NFR-006 | Every defect fix that changes a safety contract shall include an automated regression test. |
| SWR-NFR-007 | Production deployment shall stop AppDaemon, preserve a rollback backup, replace the complete backend application directory, verify file hashes, restart AppDaemon, and verify live health/log/entity behaviour. |

## 6. Verification strategy

The required local verification commands are:

```text
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

Coverage shall be interpreted over application code only. Including tests,
AppDaemon stubs, templates, or `backend/deploy.py` in the denominator is not a
valid measure of safety-logic verification.

## 7. Requirements traceability

| Requirement group | Primary tests |
| --- | --- |
| SWR-CFG-* | `test_app_cfg_validator.py`, `test_component_schema_validation.py` |
| SWR-TEMP-* | `test_temperatureComponent.py`, `test_derivative_monitor.py`, `test_safetyFunctions.py` |
| SWR-DOOR-* | `test_safety_doors_component.py`, `test_app_cfg_validator.py` |
| SWR-FLT-* | `test_fault_manager.py`, `test_system_notification_recovery.py` |
| SWR-NOT-* | `test_notify_man.py`, `test_system_notification_recovery.py` |
| SWR-REC-* | `test_recovery_man.py` |
| SWR-LOC-* | `test_localization.py`, `test_mqtt_entity_manager.py`, frontend domain tests |
| SWR-MQTT-* | `test_mqtt_entity_manager.py`, `test_safetyFunctions.py` |
| SWR-EXT-* *(planned)* | provider contract tests, external hazard policy tests, EventBus/FaultManager/notification integration tests, negative-actuation tests |
| SWR-NFR-005 | pytest-cov application-code report |

## 8. Known gaps and planned extensions

- Fire, smoke, gas, water-leak, privacy, and additional access-control hazard
  components are not implemented.
- External Hazard Monitoring and all five external API Components described in
  §4.8 are not implemented. The PAA provider contract is an explicit blocker for
  ionizing-radiation implementation.
- Evidence persistence beyond Home Assistant history/logging is not
  implemented.
- System operating modes such as Sleep, Local-only, and Maintenance are not
  implemented.
- Hardware and communication paths are not certified safety channels; this
  software provides monitoring and response assistance within the Home
  Assistant installation.

## 9. Change control

Changes to raw state codes, entity-ID generation, fault severity mapping,
timing semantics, notification correlation, recovery service allow-lists, or
configuration validation are safety-contract changes. They require an SSRD
update, regression tests, review, and controlled deployment verification.
