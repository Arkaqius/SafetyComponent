# Software Safety Requirements Document — SafetyComponent

**Document ID:** SAF-SWR-SSRD

**Version:** 0.4.0

**Status:** Software requirements baseline

**Last updated:** 2026-08-03

## 1. Purpose and scope

This Software Safety Requirements Document (SSRD) defines the required software
behaviour of the AppDaemon-based SafetyComponent. It refines the
system requirements and hazards described in:

- `SafetyConcept - HARA.md`;
- `SafetyConcept - SYS.md`;
- the deployed configuration in `backend/app_cfg.yaml`.

The software in scope includes configuration validation, component lifecycle,
temperature, safety-door, and external-hazard monitoring, fault aggregation,
notification and recovery handling, MQTT discovery/state publication,
localization metadata, and backend verification. The web frontend consumes the
published contract but does not implement safety decisions.

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
| `ExternalHazardComponent` | Correlate normalized external hazards with configured openings, create close recommendations, and maintain advice-inhibition state. |
| External API Components | One isolated component per remote API; validate and normalize provider data without creating faults or actions. |
| `DerivativeMonitor` | Calculate and publish first- and second-order temperature derivatives. |
| `FaultManager` | Aggregate symptoms, preserve multi-symptom fault context, and publish fault/system state. |
| `NotificationManager` | Maintain one notification lifecycle per fault, including acknowledgement, retry, deadlines, WAN queueing, bounded L1 repeats, persistence, and diagnostics. |
| `MobilePushProvider` | Build Android/iOS Companion payloads and submit them to explicit Home Assistant notify services. |
| `LocalAnnunciator` | Operate optional local light and alarm outputs independently from mobile delivery. |
| `NotificationStateStore` | Atomically persist filtered active and pending notification state across AppDaemon reloads and restarts. |
| `RecoveryManager` | Determine, execute, and confirm supported recovery actions. |
| `MqttEntityManager` | MQTT discovery, state, attributes, availability, retained cleanup, and heartbeat. |
| `Localizer` | Translate presentation text while retaining stable internal codes. |

Event ordering is deterministic: the FaultManager processes symptom events;
for fault events, NotificationManager runs before RecoveryManager.

## 4. Software safety requirements

### 4.1 Configuration and initialization

| ID | Requirement | Responsible element |
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

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-TEMP-001 | Each configured room shall evaluate direct low temperature (`sm_tc_1`), forecast low temperature (`sm_tc_2`), direct high temperature (`sm_tc_3`), and forecast high temperature (`sm_tc_4`). | `TemperatureComponent` |
| SWR-TEMP-002 | Direct mechanisms shall compare the current numeric sensor value with the configured low or high threshold. | `sm_tc_1`, `sm_tc_3` |
| SWR-TEMP-003 | Forecast mechanisms shall calculate a forecast from the current temperature, first derivative, and configured forecast timespan. | `sm_tc_2`, `sm_tc_4` |
| SWR-TEMP-004 | Missing, non-numeric, non-finite, `unknown`, or `unavailable` temperature or derivative input shall neither create a new symptom nor constitute positive evidence to clear an active symptom. | `_get_temperature_value` and mechanism callbacks |
| SWR-TEMP-005 | Mechanism results shall use configured debounce and reevaluation timing before fault lifecycle changes are emitted. | `SafetyComponent`, temperature calibration |
| SWR-TEMP-006 | The DerivativeMonitor shall publish only derivative measurements (`_rate` in °C/min and `_rateofrate` in °C/min²); it shall not own temperature safety limits. | `DerivativeMonitor` |
| SWR-TEMP-007 | Each room shall expose its low and high configured limits as separate diagnostic MQTT sensors named `<source>_low_threshold` and `<source>_high_threshold`. | `TemperatureComponent._register_temperature_threshold_entities` |
| SWR-TEMP-008 | Threshold sensors shall identify the source entity, threshold type, `area_id`, and current Home Assistant area name. | threshold sensor attributes |
| SWR-TEMP-009 | Low-temperature mechanisms `sm_tc_1` and `sm_tc_2` shall provide `ManipulateWindow<Room>` recovery proposals when a window sensor or supported cover actuator is configured. High-temperature mechanisms `sm_tc_3` and `sm_tc_4` shall create no recovery action, and C-TEMP shall not issue HVAC/climate commands. | `RiskyTemperature_recovery`, recovery registration |
| SWR-TEMP-010 | Direct low/high symptoms shall aggregate into level-2 `RiskyTemperature`; forecast low/high symptoms shall aggregate into level-3 `RiskyTemperatureForecast`; the direct fault shall shadow the forecast fault and each fault shall remain active until every related symptom clears. | fault catalog and `FaultManager` |

Stable Temperature runtime IDs are:

| Mechanism | Symptom ID pattern | Fault ID |
| --- | --- | --- |
| `sm_tc_1` | `RiskyTemperature<Room>` | `RiskyTemperature` |
| `sm_tc_2` | `RiskyTemperature<Room>ForeCast` | `RiskyTemperatureForecast` |
| `sm_tc_3` | `RiskyTemperatureHigh<Room>` | `RiskyTemperature` |
| `sm_tc_4` | `RiskyTemperatureHigh<Room>ForeCast` | `RiskyTemperatureForecast` |

The existing `ForeCast` capitalization is part of the runtime contract.

### 4.3 Safety Doors monitoring

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-DOOR-001 | Every configured door or gate shall have an independent `timeout_seconds` value, inherited from component defaults only when no per-door override is supplied. | Safety Doors schema |
| SWR-DOOR-002 | A continuously open door shall set its symptom only after its own configured timeout expires. | `sm_safety_door_open_timeout` |
| SWR-DOOR-003 | Closing a door shall cancel its pending timer and clear its symptom. | Safety Doors runtime |
| SWR-DOOR-004 | An unavailable or unsupported door state shall publish diagnostic state `unavailable`, cancel pending timing, and shall neither create a new open-timeout fault nor clear an already active per-door symptom. | `_read_door_state` and evaluation flow |
| SWR-DOOR-005 | A configured condition shall monitor its entity alongside the door; pass states enable timing and blocked states suspend timing and clear the symptom. | `SafetyDoorCondition`, Safety Doors runtime |
| SWR-DOOR-006 | An unavailable or unsupported condition state shall publish diagnostic state `unavailable`, cancel pending timing, and shall neither create a new fault nor clear an already active per-door symptom. | `_read_condition_state` |
| SWR-DOOR-007 | Each Safety Door MQTT entity shall publish door state, elapsed and remaining time, source entity, timeout, condition diagnostics, `area_id`, and resolved area name. | `_publish_door_state` |
| SWR-DOOR-008 | The current installation calibration shall use 180 s for `GarageGate`, 180 s for `ExternalGate`, 120 s for `LivingRoomTerraceDoor`, and 900 s for `GarageDoor`. | `backend/app_cfg.yaml` |
| SWR-DOOR-009 | `LivingRoomTerraceDoor` monitoring shall pass only while `sensor.home_monitor_occupancy` is `empty` and shall be blocked while it is `occupied`. | `backend/app_cfg.yaml` |
| SWR-DOOR-010 | `SafetyDoorsComponent` shall use mechanism ID `sm_safety_door_open_timeout`, per-door symptom IDs `SafetyDoorOpenTimeout<DoorName>`, the single level-2 fault `SafetyDoorOpenTimeout`, and diagnostic entities `sensor.safety_door_<door_name>`. It shall register no recovery action. | Safety Doors runtime and fault catalog |
| SWR-DOOR-011 | Safety Doors shall not infer unauthorized entry, lock integrity, or intrusion state and shall not close, lock, unlock, or otherwise actuate a door or gate; those security responsibilities are outside C-DOOR. | Safety Doors component boundary |

### 4.4 Fault aggregation and system state

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-FLT-001 | A fault shall aggregate all related active symptoms rather than replace the previous contribution from the same fault. | `FaultManager` merged symptom context |
| SWR-FLT-002 | When one symptom clears but another related symptom remains set, the fault shall remain set and its notification context shall be refreshed. | `FaultManager._clear_fault` |
| SWR-FLT-003 | The highest active severity shall be the minimum numeric active fault level. | `get_system_fault_level` |
| SWR-FLT-004 | With no active faults, system state shall be `no_faults` and `highest_fault_level` shall be `0`. This state describes fault absence, not application health. | `SYSTEM_STATE_BY_FAULT_LEVEL` |
| SWR-FLT-005 | With active faults, system state shall be `emergency`, `hazard`, `warning`, or `information` for levels 1 through 4 respectively. | `SYSTEM_STATE_BY_FAULT_LEVEL` |
| SWR-FLT-006 | Application health shall be represented independently by `sensor.safety_app_health`. | `SafetyFunctions` |
| SWR-FLT-007 | Fault entities shall publish stable raw lifecycle states `Set`, `Shadowed`, `Cleared`, and `Not_tested`. | `FaultManager` |

### 4.5 Notifications and recovery

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-NOT-001 | Notifications shall use the configured fault friendly name and resolved user-facing location. | `FaultManager`, `NotificationManager` |
| SWR-NOT-002 | A fault shall use one stable notification tag throughout its lifecycle. | fault tag generation and `active_notification` |
| SWR-NOT-003 | A repeated SET for an active fault shall update the current base message instead of creating a second notification. | `NotificationManager.active_notification` |
| SWR-NOT-004 | Distinct recovery guidance accumulated for the same active fault shall be retained and shown once under a localized guidance heading. | `_recovery_messages` |
| SWR-NOT-005 | Clearing a fault shall publish a friendly cleared message using the same tag. | `cleared_notification` |
| SWR-NOT-006 | Mobile delivery shall use one or more explicitly configured `notify/<service>` targets and shall reject the ambiguous `notify/notify` service. | `MobilePushConfig`, `MobilePushProvider` |
| SWR-NOT-007 | A shadowed fault shall remove its mobile notification by sending `message: clear_notification` with the stable tag. | `MobilePushProvider.clear` |
| SWR-NOT-008 | Levels 1 through 3 shall use separately configured Android and iOS profiles. A newly active fault or same-tag increase in urgency may alert audibly; repeated context and recovery-guidance updates at the same severity shall use a quiet profile and shall not reactivate local annunciators. An update shall not downgrade a still-pending new-alert attempt for an undelivered target to quiet. | `MobileProfile`, `MobilePushProvider`, `LocalAnnunciator` |
| SWR-NOT-009 | Mobile submission shall explicitly request a Home Assistant service result. A returned result shall be reported as `accepted_by_home_assistant` and shall not be represented as confirmed phone delivery; a missing or failed result shall be retried as a transport failure. | delivery result and diagnostics contract |
| SWR-NOT-010 | Failed target submissions shall be retried independently with bounded exponential backoff. Failure of one target shall not prevent submission to another configured target. | `PendingDelivery`, scheduler |
| SWR-NOT-011 | When configured WAN state is not positively online, remote notification submissions shall remain queued. The queue shall be flushed after confirmed WAN recovery. Unknown, unavailable, or malformed WAN state shall not be treated as online. | WAN state handler and delivery queue |
| SWR-NOT-012 | Home Assistant acceptance later than 10 seconds for L1 or 30 seconds for L2/L3 shall increment deadline-miss telemetry without blocking fault or recovery processing. | retry deadlines and diagnostics |
| SWR-NOT-013 | An acknowledgement action shall suppress subsequent L1 repeats without clearing the active fault or preventing quiet content refreshes. | mobile action handler |
| SWR-NOT-014 | L1 repeats shall use a configurable interval and finite maximum count. Clearing, shadowing, or acknowledging the fault shall cancel pending repeats. | `LevelOneRepeatPolicy` |
| SWR-NOT-015 | Active records, acknowledgement, pending deliveries, repeat state, counters, and last transport result shall be restored from a versioned atomic state snapshot after AppDaemon reload or restart. A restored active record shall remain fail-safe until a current authoritative fault event confirms or clears it. | `NotificationStateStore`, fault-event reconciliation |
| SWR-NOT-016 | Only configured allowlisted detail fields shall be included in mobile payloads or persistent notification state. | `_filter_details` |
| SWR-NOT-017 | Mobile transport, local light/alarm outputs, and persistence shall be isolated adapters. Failure in one adapter shall not block fault state, recovery policy, or another delivery adapter. | notification adapter boundaries |
| SWR-NOT-018 | `sensor.notification_delivery_health` shall expose active, acknowledged, queued, accepted, failed, deadline-miss and exhausted counts; per-service status, attempt time and error; plus the last Home Assistant acceptance result and error. | MQTT delivery diagnostics |
| SWR-REC-001 | Recovery commands shall be limited to explicitly supported Home Assistant entity domains and services. | `RecoveryManager._resolve_entity_action` |
| SWR-REC-002 | A recovery action shall verify the requested postcondition and shall report failure or timeout instead of assuming success. | RecoveryManager confirmation flow |
| SWR-REC-003 | Recovery entities shall expose stable raw states `DO_NOT_PERFORM`, `TO_PERFORM`, `AWAITING_CONFIRMATION`, `EXECUTING`, `CONFIRMED`, `FAILED`, and `TIMED_OUT`; the frontend shall localize their presentation. | RecoveryManager and SafetyHome |
| SWR-REC-004 | A `user_confirmed` proposal shall not execute until RecoveryManager receives the exact current proposal ID and one-time confirmation token through the authenticated Home Assistant event connection. | confirmation event handler |
| SWR-REC-005 | RecoveryManager shall re-evaluate current symptom state, expiry, policy, and the exact configured actuator immediately before a confirmed command, and shall reject replayed or stale confirmation. | confirmation validation |
| SWR-REC-006 | Active proposal state shall be atomically persisted outside the deployed app directory. Restart shall restore operator-visible state without replaying an actuator command and shall rotate confirmation tokens. | `RecoveryStateStore` |
| SWR-REC-007 | MQTT proposal attributes shall use an explicit allowlist and shall include instruction, policy, lifecycle, reason, source, validity, area, postcondition, and actuator only where applicable. | proposal publication |
| SWR-REC-008 | Recovery guidance shall be owned by proposal ID so that updates replace prior text and clearing or shadowing removes stale guidance. | NotificationManager guidance API |

### 4.6 Localization contract

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-LOC-001 | English (`en`), Polish (`pl`), and German (`de`) shall be supported installation languages. | `LocalizationSettings`, `_TRANSLATIONS` |
| SWR-LOC-002 | Entity IDs, MQTT topic identifiers, fault identifiers, event codes, and raw lifecycle states shall remain language-independent. | backend runtime contract |
| SWR-LOC-003 | Localization shall apply to MQTT discovery names, `state_label`, notification text, recovery guidance, and dynamic threshold/recovery entity names. | Localizer consumers |
| SWR-LOC-004 | Home Assistant area names shall be used as returned by Home Assistant and shall not be translated or reconstructed from internal configuration keys. | area resolution flow |
| SWR-LOC-005 | Missing translation keys shall fall back to English and then to the key itself without changing safety logic. | `Localizer.text`, `state_label` |

### 4.7 MQTT lifecycle and diagnostics

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-MQTT-001 | Internal entities shall use MQTT discovery with stable unique IDs and default entity IDs. | `MqttEntityManager` |
| SWR-MQTT-002 | Discovery payloads may be retained; transient state and attribute payloads shall not be retained. | MQTT settings and publisher |
| SWR-MQTT-003 | Startup shall clear configured legacy discovery topics and stale retained state before publishing current state. | MQTT startup flow |
| SWR-MQTT-004 | Availability shall be `offline` during initialization and `online` after successful startup or diagnostic invalid-configuration startup. | `SafetyFunctions` |
| SWR-MQTT-005 | The heartbeat period shall remain shorter than `expire_after` so unchanged entities do not become unavailable. | `heartbeat_seconds`, `expire_after` |
| SWR-MQTT-006 | Application termination shall publish health and system state `stopped` before publishing availability `offline`. | `SafetyFunctions.terminate` |

### 4.8 External Hazard Monitoring

This subsection defines the software contract for External Hazard Monitoring.
The detailed design is in
[`External Hazard Monitoring - Architecture.md`](../features/External%20Hazard%20Monitoring%20-%20Architecture.md).

The stable runtime contract is:

| Fault ID | Safety Mechanism ID (`related_sms`) | Symptom ID contract | Level |
| --- | --- | --- | ---: |
| `ExternalWeatherExposure` | `sm_ext_weather_exposure` | `ExternalWeatherExposure{HazardId}{OpeningId}` | 2 |
| `OutdoorAirQualityExposure` | `sm_ext_outdoor_air_quality_exposure` | `OutdoorAirQualityExposure{OpeningId}` | 3 |
| `ExternalHazardDataUnavailable` | `sm_ext_provider_unavailable` | `ExternalHazardDataUnavailable{CapabilityId}` | 3 |

Each Safety Mechanism ID shall occur in exactly one fault's `related_sms` list.
The complete `SafetyFunctions.app_config` and `SafetyFunctions.user_config`
contract, including provider policies and opening bindings, is defined in the
feature architecture §12.

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-EXT-001 | The feature shall use separate `OpenMeteoWeatherApiComponent`, `ImgwWarningsApiComponent`, and `OpenMeteoAirQualityApiComponent` classes. | external API component registry |
| SWR-EXT-002 | API Components shall have independent schemas, polling schedules, caches, failure counters, health, and contract tests. | `components/external_apis/*` |
| SWR-EXT-003 | API Components shall not inherit from `SafetyComponent` and shall not create symptoms, faults, notifications, recovery actions, or actuator calls. | `ExternalApiComponent` protocol |
| SWR-EXT-004 | Network work shall run outside the serialized safety-decision callback and results shall return through a bounded queue for ordered EventBus publication. | `ExternalApiRuntime` |
| SWR-EXT-005 | `ExternalHazardComponent` shall be the only Safety Component in this feature and shall own household thresholds, freshness, cross-provider policy, opening correlation, aggregation, notification context, and the stable runtime identifiers defined above. | `ExternalHazardComponent` |
| SWR-EXT-006 | Frost, wind/gust, rain/storm, and outdoor-pollution exposure symptoms shall require both applicable valid hazard evidence and an open configured aperture. | external hazard policy mechanisms |
| SWR-EXT-009 | Provider timeout, stale data, or schema error shall not clear an active condition and shall publish provider degradation diagnostics. | provider health and clear policy |
| SWR-EXT-010 | External Hazard Monitoring shall register a close recommendation for each exposure symptom. Window and ordinary-door recommendations shall remain manual. | recovery registration |
| SWR-EXT-011 | Same-fault updates shall retain all active hazards/openings and refresh one notification tag using friendly names and localized area labels. | FaultManager and NotificationManager integration |
| SWR-EXT-012 | External pollution, damaging wind, or storm shall inhibit contradictory advice to open external apertures. | `RecoveryPolicyEvaluator` integration |
| SWR-EXT-014 | `ImgwWarningsApiComponent` shall expose only current sanitized warnings matching at least one configured TERYT code, mark them as locally applicable, and dispatch locally applicable recognized hazards into household safety policy. | `ImgwWarningsApiComponent` and provider diagnostic MQTT entity |
| SWR-EXT-015 | Each provider diagnostic MQTT entity shall expose an `observations` list of at most 64 summaries containing the stable observation ID, hazard type, provider level, observation and validity timestamps, and an optional operator-display value and unit. The list shall contain normalized current observations only and shall not expose unbounded provider payloads. | `ExternalHazardComponent._publish_provider_health` |
| SWR-EXT-016 | The garage and external gate may bind only directional `cover.*` actuators and `user_confirmed` execution. No other opening kind may define an actuator. | `OpeningConfig` validation |
| SWR-EXT-017 | A gate close shall call only `cover.close_cover` after valid SafetyHome confirmation and shall use its configured contact as the physical closed postcondition. | RecoveryManager confirmed execution |

### 4.9 Entity Health Monitoring

The detailed design is in
[`Entity Health Monitoring - Architecture.md`](../features/Entity%20Health%20Monitoring%20-%20Architecture.md).

The stable runtime contract is:

| Element | Stable ID |
| --- | --- |
| Component | `EntityMonitorComponent` |
| Safety Mechanism pattern | `sm_entity_health_<entity_key>` |
| Symptom pattern | `EntityHealthFailure{EntityKey}{CheckKey}` |
| Fault pattern | `EntityHealth{EntityKey}`, level 3 |
| Per-entity diagnostic | `sensor.entity_health_<entity_key>` |
| Aggregate diagnostic | `sensor.entity_monitor_summary` |

| ID | Requirement | Responsible element |
| --- | --- | --- |
| SWR-ENT-001 | The feature shall distinguish `explicit`, `component`, and `inventory` source groups. `EntityHealthRegistry` shall maintain Groups A/B, and the frontend shall join them with Group C while preserving every applicable membership. | `EntityHealthRegistry` and SafetyHome join |
| SWR-ENT-002 | Explicit safety entities shall be accepted only from validated installation configuration with a stable key, valid entity ID, area when configured, debounce policy, and complete definitions for every enabled optional check. | Entity Monitor schema and `AppCfgValidator` |
| SWR-ENT-003 | Safety Components and the application core shall register their entity dependencies with owner, purpose, checks, debounce, optional freshness contract, and fault ownership; all configured `common_entities` shall be registered as component dependencies. | component registry integration |
| SWR-ENT-004 | Availability shall fail when Home Assistant reports `unknown` or `unavailable`, the entity cannot be read, or the entity disappears after startup. For a safety-relevant dependency, availability failure debounce shall fit its allocated FTTI detection budget. | availability check |
| SWR-ENT-005 | Freshness shall be enabled only when the entity contract identifies a trustworthy heartbeat or timestamp source and `max_silence_seconds`. It shall become `stale` when that confirmation expires; startup grace shall prevent a false stale result before the initial snapshot is evaluated. For a safety-relevant dependency, freshness timeout plus failure debounce shall fit its allocated FTTI detection budget. | freshness check and scheduler |
| SWR-ENT-006 | Required-value, allowed-values, finite-number, numeric-range, and rate-of-change checks shall be opt-in and shall reject incomplete or type-incompatible calibration. Numeric-range checks shall define at least one inclusive bound. Rate-of-change checks shall define a sample window, minimum sample count, and at least one permitted rise or fall bound. | check registry and schemas |
| SWR-ENT-007 | A failing C-ENT-owned check shall set its stable symptom only after failure debounce and shall clear only after fresh valid observations pass recovery debounce. Invalid or missing observations shall not clear an active symptom. | evaluation state machine |
| SWR-ENT-008 | Component-owned fault handling shall take precedence for a component dependency. Entity Monitor shall expose the dependency health but shall not emit a duplicate C-ENT symptom for the same failure. | fault-ownership resolver |
| SWR-ENT-009 | C-ENT-owned check symptoms shall aggregate per entity into one level-3 `EntityHealth{EntityKey}` fault. Different unhealthy entities shall have different faults. Each fault shall retain the friendly name, entity ID, source groups, failed checks, last valid value, and relevant timestamps. | dynamic fault registration and FaultManager integration |
| SWR-ENT-010 | Each Group A/B diagnostic shall publish `healthy`, `degraded`, `stale`, or `unavailable`, plus source membership, owner, friendly name, area, device, current state, last change, last update, last valid observation, checks, and fault ownership. | MQTT diagnostics |
| SWR-ENT-011 | The aggregate diagnostic shall publish bounded counts by health and source group plus bounded summaries of unhealthy Group A/B entities; it shall not contain the complete Home Assistant inventory. | `sensor.entity_monitor_summary` publisher |
| SWR-ENT-012 | The frontend shall read Group C entity/device state and registry metadata through its authenticated Home Assistant connection and support filtering by domain, device, area, availability, source group, and last-change or last-update time. | SafetyHome entity audit view |
| SWR-ENT-013 | Group C shall not create symptoms, faults, notifications, recovery actions, MQTT inventory payloads, or application-health degradation. | frontend inventory boundary and backend negative contract |
| SWR-ENT-014 | Entity Monitor shall register no recovery action and shall make no Home Assistant actuator service call. | negative actuation boundary |
| SWR-ENT-015 | User-facing Entity Monitor names and states shall support English, Polish, and German; entity IDs, source codes, check codes, and raw health states shall remain language-independent. | localization and frontend presentation |

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

| Safety scope | SYS requirements | Software requirements |
| --- | --- | --- |
| SG-001 Unsafe Cold Exposure | `SYS-SR-TEMP-001/002/004/005/007/008/009/010` | `SWR-TEMP-*` |
| SG-002 Temperature Prediction | `SYS-SR-TEMP-001/003/004/005/006/009/010` | `SWR-TEMP-*` |
| SG-003 Sensor/Communication Fault Detection | `SYS-SR-ENT-001..009/012/014` plus component-specific unavailable-input requirements | `SWR-ENT-*`, `SWR-TEMP-004`, `SWR-DOOR-004/006`, `SWR-EXT-009` |
| SG-004 Unsafe Heat Exposure | `SYS-SR-TEMP-001/002/003/004/005/006/007/008/010` | `SWR-TEMP-*` |
| SG-015 Door/Gate Open-Duration Contribution | `SYS-SR-DOOR-001..011` | `SWR-DOOR-*` |
| SG-011/017/018 External Weather Exposure | `SYS-SR-EXT-001..005/010..013/040..043/050..052` | `SWR-EXT-*` |
| SG-019 Outdoor Pollution Exposure | `SYS-SR-EXT-001..005/020..023/040..043/050..052` | `SWR-EXT-*` |

| Requirement group | Primary tests |
| --- | --- |
| SWR-CFG-* | `test_app_cfg_validator.py`, `test_component_schema_validation.py` |
| SWR-TEMP-* | `test_temperatureComponent.py`, `test_derivative_monitor.py`, `test_safetyFunctions.py` |
| SWR-DOOR-* | `test_safety_doors_component.py`, `test_app_cfg_validator.py` |
| SWR-FLT-* | `test_fault_manager.py`, `test_system_notification_recovery.py` |
| SWR-NOT-* | `test_notify_man.py`, `test_notification_schema.py`, `test_notification_state_store.py`, `test_system_notification_recovery.py` |
| SWR-REC-* | `test_recovery_man.py` |
| SWR-LOC-* | `test_localization.py`, `test_mqtt_entity_manager.py`, frontend domain tests |
| SWR-MQTT-* | `test_mqtt_entity_manager.py`, `test_safetyFunctions.py` |
| SWR-EXT-* | provider contract tests, external hazard policy tests, EventBus/FaultManager/notification integration tests, negative-actuation tests |
| SWR-ENT-* | entity health registry/check/state-machine tests, component dependency and common-entity integration tests, FaultManager/MQTT tests, frontend inventory/filter tests, negative-actuation tests |
| SWR-NFR-005 | pytest-cov application-code report |

## 8. Assurance boundary

SafetyComponent provides monitoring and response assistance within a Home
Assistant installation. Home Assistant, AppDaemon, the host, networks, sensors,
actuators, cloud providers, and notification transports are external or
non-certified dependencies. This software and its documentation do not claim
regulatory certification, guaranteed provider availability, or medical guidance.

## 9. Change control

Changes to raw state codes, entity-ID generation, fault severity mapping,
timing semantics, notification correlation, recovery service allow-lists, or
configuration validation are safety-contract changes. They require an SSRD
update, regression tests, review, and controlled deployment verification.
