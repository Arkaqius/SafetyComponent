Got it 👍 I’ll merge both documents into **one unified SSRD**, keeping the ASPICE/ISO style, eliminating redundancy, and making sections consistent. I’ll preserve all details: purpose, scope, context, requirements, architecture, design, testing, backlog, and traceability. Here’s the combined draft:

---

# ASPICE SSRD — SafetyFunctions Application (v0.2.0, Consolidated)

## 1. Introduction

### 1.1 Purpose

This Software Safety Requirements Document (SSRD) captures the current state of the **Home Automation SafetyFunctions** application. It consolidates requirements, architecture, and detailed design into a single ASPICE-aligned document. It ensures that the system concept from the SYS and HARA work products can be implemented, verified, and evolved in alignment with ASPICE SYS.2/SWE.1 expectations.

### 1.2 Scope

- **Item**: Home Automation Safety Monitoring & Recovery App (AppDaemon-based).
- **Includes**: Safety runtime (SafetyFunctions), shared SafetyComponent framework, TemperatureComponent MVP, supporting managers (Fault, Notification, Recovery, DerivativeMonitor), configuration handling, and test harness.
- **Excludes**: Frontend UI, non-safety automations, hardware certification, hazard analysis (covered in HARA), and deployment tooling.

### 1.3 Intended Audience

- Software architects & developers adding safety components or extending platform.
- V\&V engineers planning unit, integration, and end-to-end drills.
- Safety managers tracking ASPICE coverage against SYS/HARA.

### 1.4 References

- `docs/sys/SafetyConcept - HARA.md`
- `docs/sys/SafetyConcept - SYS.md`
- Backend source (`backend/`)
- `backend/app_cfg.yaml` (YAML config)
- SafetyFunctions orchestration & component code (`SafetyFunctions.py`, `safety_component.py`, `temperature_component.py`, `fault_manager.py`, `notification_manager.py`, `recovery_manager.py`, `derivative_monitor.py`)
- Current pytest suites (`backend/tests/`)

### 1.5 Definitions & Abbreviations

- **SM** — Safety Mechanism
- **FM** — Fault Manager
- **NM** — Notification Manager
- **RM** — Recovery Manager
- **HA** — Home Assistant
- **MVP** — Minimum Viable Product
- **FTTI** — Fault Tolerant Time Interval

---

## 2. System Context & Overview

### 2.1 Operating Context

- Runtime: AppDaemon inside Home Assistant.
- Inputs: HA sensor entities (temperature, rate), derivative monitor outputs, configuration YAML.
- Outputs: HA state entities, notifications, actuator commands, recovery prompts.
- Dependencies: HA event loop, scheduler, notify services.

### 2.2 Responsibilities

1. Load configuration and instantiate safety components.
2. Monitor hazards via SMs with debouncing.
3. Aggregate prefaults into faults and manage lifecycle.
4. Notify users or automation targets at graded urgency.
5. Execute/suggest recovery actions.
6. Provide health/state telemetry to HA entities.

---

## 3. Requirements

### 3.1 Functional Requirements (Implemented)

| ID     | Requirement                                       | Status / Implementation                  |
| ------ | ------------------------------------------------- | ---------------------------------------- |
| FR-001 | Load component/fault configuration from YAML.     | ✅ (`SafetyFunctions.initialize`)        |
| FR-002 | Register HA health/fault entities.                | ✅ (`register_entities`)                 |
| FR-003 | Detect sustained under-temperature (threshold).   | ✅ (`sm_tc_1`)                           |
| FR-004 | Forecast under-temperature using derivative data. | ✅ (`sm_tc_2`)                           |
| FR-005 | Aggregate temperature prefaults into faults.      | ✅ (FM + TC symptom definitions)         |
| FR-006 | Orchestrate recovery suggestions/actions.         | ⚠️ Partial (windows, notifications only) |
| FR-007 | Send notifications with tagging/persistence.      | ✅ (NM)                                  |
| FR-008 | Track active faults & expose highest severity.    | ✅ (`FM.update_system_state_entity`)     |
| FR-009 | Enable/disable SMs programmatically.              | ✅ (FM)                                  |

### 3.2 Functional Requirements (Backlog / Gaps)

| ID     | Requirement                                                   | Gap                     |
| ------ | ------------------------------------------------------------- | ----------------------- |
| FR-010 | Support all hazard domains (fire, gas, water, privacy, etc.). | ❌ Only TC implemented. |
| FR-011 | Over-temperature detection + HVAC actuation.                  | ❌ Not yet in TC.       |
| FR-012 | System modes (Normal, Sleep, Local-Only, Maintenance).        | ❌ Not implemented.     |
| FR-013 | Self-diagnostics, heartbeat, watchdog statuses.               | ❌ Missing.             |
| FR-014 | Record evidence logs per SYS §8.2.5.                          | ❌ Not implemented.     |
| FR-015 | Timeout handling for async SM execution.                      | ❌ Not implemented.     |
| FR-016 | Safe-state fallback (e.g., local-only).                       | ❌ Not implemented.     |

### 3.3 Non-Functional Requirements

| ID      | Requirement                              | Status                            |
| ------- | ---------------------------------------- | --------------------------------- |
| NFR-001 | Config-driven behaviour (no code edits). | ⚠️ Partial (hard-coded registry). |
| NFR-002 | Modular architecture.                    | ⚠️ Partial; cross-coupled.        |
| NFR-003 | Testability with pytest & mocks.         | ⚠️ Partial; heavy mocking.        |
| NFR-004 | Central logging.                         | ⚠️ Basic only.                    |
| NFR-005 | Deterministic tests (no scheduler deps). | ❌ Not met.                       |
| NFR-006 | Resilience against config errors.        | ⚠️ Partial.                       |

---

## 4. Architecture

### 4.1 Logical Components

- **SafetyFunctions (AppDaemon app)**: Orchestrator that performs a deterministic boot sequence (`10.* → 130.*` in code) to seed the health entity, materialise component instances, and publish a consolidated configuration snapshot as Home Assistant entity attributes. It registers all exposed sensors (`sensor.system_state`, per-fault sensors, recovery entities) and delegates lifecycle control to the domain managers.
- **SafetyComponent (abstract base)**: Supplies reusable infrastructure for safety mechanisms, including `DebounceState`/`DebounceAction` primitives, entity validation helpers, and the `safety_mechanism_decorator` that guards execution, applies debouncing, and schedules forced re-evaluations through the AppDaemon scheduler when symptoms are still stabilising.
- **TemperatureComponent (MVP)**: Builds on `SafetyComponent` to offer two safety mechanisms—`sm_tc_1` (direct threshold) and `sm_tc_2` (forecast using derivative trends). It auto-registers derivative monitors for sensors, constructs `Symptom`/`RecoveryAction` objects per location, and exposes configurable recovery hooks (`RiskyTemperature_recovery`).
- **FaultManager**: Maintains the canonical mapping of `Symptom` → `Fault`, manages state transitions, hashes a unique `fault_tag` for notification/recovery correlation, updates HA entities, and enforces enable/disable semantics for each safety mechanism.
- **NotificationManager**: Translates `FaultState` changes into multi-channel notifications. It maps severity levels to dedicated handlers (lights, alarms, dashboard updates), builds persistent `notify/notify` payloads tagged with the `fault_tag`, and clears notifications when faults resolve.
- **RecoveryManager**: Executes recovery actions while checking for dry-run conflicts. It simulates proposed entity changes against all enabled safety mechanisms, filters out conflicting recovery strategies, coordinates notification enrichment, and tracks recovery state via dedicated HA entities.
- **DerivativeMonitor**: Singleton helper that registers entities for periodic sampling, applies saturation and moving-average filtering to first/second derivatives, and publishes `_rate` / `_rateOfRate` entities used by forecast safety mechanisms.
- **CommonEntities & cfg_parser utilities**: Provide access to shared HA readings (e.g., outside temperature) and translate YAML dictionaries into strongly typed `Fault` objects consumed by the managers.

### 4.2 Data Flow Summary

1. YAML config → SafetyFunctions → component factory instantiation and DerivativeMonitor bootstrap.
2. Components register SMs; decorator handles debouncing, retry scheduling, and forwards `Symptom` events to FaultManager.
3. HA triggers SM callbacks (directly or via scheduled `sm_recalled`); SafetyComponent evaluates conditions and invokes `process_symptom`.
4. FaultManager updates Fault state, emits unique `fault_tag`, and reflects changes onto HA entities.
5. NotificationManager receives callbacks to set/clear tagged notifications and trigger auxiliary services (lights, alarms, dashboards).
6. RecoveryManager validates and performs recovery actions, logging state to HA and re-listening for completion, while DerivativeMonitor continues publishing `_rate` metrics for proactive mechanisms.

### 4.3 Interfaces & External Dependencies

- **Home Assistant/AppDaemon APIs**: `set_state`, `get_state`, `listen_state`, `run_in`, `run_every`, `call_service` underpin orchestration, scheduling, and service invocation.
- **External Entities**: Temperature sensors, actuators, notification services, and dashboard entities referenced in configuration must exist for deterministic operation.
- **Remote Debugging (optional)**: `remote_pdb` may be attached when `DEBUG` is enabled in `SafetyFunctions`.

### 4.4 Deployment

- Runs in HA/AppDaemon container.
- Interfaces: `set_state`, `listen_state`, `run_in`, `run_every`, `call_service`.
- Debugging: `remote_pdb` when enabled.

### 4.5 Configuration Model

- **app_config.faults**: Defines each `Fault` with `related_sms` and severity `level`; `cfg_parser.get_faults` materialises them into runtime objects.
- **user_config.safety_components**: Lists component instances per location with thresholds, actuators, and debounce parameters consumed by component factories.
- **user_config.notification**: Maps severity levels to HA services/entities (lights, alarms, dashboard) for NotificationManager.
- **user_config.common_entities**: Provides shared entity IDs such as `outside_temp` leveraged by recovery logic.

---

## 5. Detailed Design

### 5.1 SafetyFunctions

- Initialization: Executes a numbered boot routine that seeds `sensor.safety_app_health`, instantiates `DerivativeMonitor`, merges configuration for telemetry, and short-circuits with `invalid_cfg` health state if mandatory sections are missing.
- Entity registration: `register_entities` creates `sensor.system_state`, per-fault sensors with descriptive attributes, and embeds serialised `Symptom` / `RecoveryAction` metadata into the health entity for diagnostics.
- Integration: Wires FaultManager, NotificationManager, and RecoveryManager via callback registration to ensure recovery/notification loops carry the generated `fault_tag`.
- Issues: Hard-coded component dict; no shutdown hooks; no mode management; recovery configuration embedded within health entity without schema validation.

#### Public Interfaces
- `initialize()` — deterministic bootstrap that wires configuration, instantiates managers, registers callbacks, and transitions the health entity through `init → running` states.
- `register_entities()` — creates HA entities for the system state and each configured fault while returning the attribute payload injected into `sensor.safety_app_health`.

#### Key Private/Helper Functions
- No dedicated private helpers; orchestration relies on collaborating manager classes for specialised behaviours.

### 5.2 SafetyComponent Base

- Responsibilities: Hosts `DebounceState` memory per mechanism, `_debounce` counter logic, and `process_symptom` orchestration that reads the current `FaultState`, applies hysteresis, and optionally forces re-runs via AppDaemon scheduling.
- Execution guard: `safety_mechanism_decorator` logs execution, skips disabled mechanisms, re-queues `sm_recalled` for additional samples when counters have not stabilised, and supports “dry mode” evaluation used by recovery dry-runs.
- Validation: Provides generic entity type validation (`validate_entity`/`validate_entities`) and safe sensor conversion helpers shared across components.
- Issues: Tight HA scheduler coupling; no timeout; hidden dependency on DerivativeMonitor; `change_all_entities_state` helper currently returns nested list instead of flattened mapping.

#### Public Interfaces
- `__init__(hass_app, common_entities)` and `init_common_data()` — seed per-instance caches, attach the shared `DerivativeMonitor`, and keep dictionaries resettable across reloads.
- `get_symptoms_data(modules, component_cfg)` / `init_safety_mechanism(sm_name, name, parameters)` / `enable_safety_mechanism(name, state)` — abstract hooks subclasses must implement to expose their safety mechanisms to the orchestrator.
- `register_fm(fm)` — associates the component with the global `FaultManager` so debounced events can drive fault transitions.
- `validate_entity(...)` and `validate_entities(...)` — reusable type guards invoked by concrete components during configuration parsing.
- `get_num_sensor_val(...)` and `change_all_entities_state(...)` — static helpers that normalise sensor reads and recovery state payloads for reuse.
- `process_symptom(...)` — core debouncing pipeline returning the updated counter and the `force_sm` flag consumed by the decorator.
- `sm_recalled(**kwargs)` — extension point invoked by the decorator’s scheduler; subclasses override to resubmit safety mechanisms with cached context.
- Module-level `safety_mechanism_decorator(func)` (and resulting `safety_mechanism_wrapper`) — wraps concrete safety mechanism functions with logging, enablement gating, debouncing, and re-scheduling.

#### Key Private/Helper Functions
- `_debounce(counter, pr_test, debounce_limit)` — tri-state counter adjustment that returns a `DebounceResult` guiding whether to set, clear, or continue sampling a symptom.

### 5.3 TemperatureComponent

- SMs: `sm_tc_1` (direct cold threshold) and `sm_tc_2` (forecast via exponential decay using derivative trends). Both reuse the decorator for debouncing and schedule-driven follow-ups.
- Config processing: Iterates per-location dictionaries to create `Symptom`/`RecoveryAction` pairs, leveraging helper factories (`_create_symptom`, `_create_recovery_action`) to embed location context and actuators.
- Forecasting: Registers sensors with `DerivativeMonitor` (60×`FORECAST_SAMPLING_TIME` cadence) and computes future temperatures via `forecast_temperature`, saturating derivative inputs to avoid unrealistic projections.
- Recovery: `RiskyTemperature_recovery` cross-compares indoor vs outdoor temperatures, toggles windows/actuators, and raises notifications when manual intervention is required.
- Concerns: Intermixed config parsing; no high-temperature support; silent skips on missing config; relies on derivative entities being available.

#### Public Interfaces
- `__init__(hass_app, common_entities)` — initialises base state, binds the shared `CommonEntities`, and pulls in the global `DerivativeMonitor` singleton.
- `get_symptoms_data(modules, component_cfg)` — expands per-location YAML into `Symptom` and `RecoveryAction` objects consumed by `SafetyFunctions`.
- `init_safety_mechanism(sm_name, name, parameters)` — routes to `_init_sm` with the method lookup for either `sm_tc_1` or `sm_tc_2`.
- `enable_safety_mechanism(name, state)` — flips `SafetyMechanism` enablement and executes immediate baseline checks when enabling.
- `sm_tc_1(sm, entities_changes=None)` — evaluates raw temperature thresholds and returns `SafetyMechanismResult` payloads for debouncing.
- `sm_tc_2(sm, entities_changes=None)` — projects future temperatures using derivative data and flags prefaults before thresholds are crossed.
- `forecast_temperature(initial_temperature, dT, forecast_timespan_hours)` — exposes the exponential decay model for reuse in analytics and tests.
- `sm_recalled(**kwargs)` — scheduler callback that replays stored mechanism context to continue debouncing cycles.
- `RiskyTemperature_recovery(hass_app, symptom, common_entities, **kwargs)` — static recovery hook used by `RecoveryManager` to derive entity changes and advisory messaging.

#### Key Private/Helper Functions
- `_process_symptoms_for_location(...)` and `_process_sm_tc(...)` — iterate location configs, derive canonical symptom names, and populate return dictionaries for both SM variants.
- `_create_symptom(...)` / `_create_recovery_action(...)` — construct typed objects with copied configuration and injected location context to avoid shared mutable state.
- `_get_sm_tc_{1,2}_pr_name`, `_get_sm_tc_{1,2}_symptom`, `_get_sm_tc_{1,2}_recovery_action` — encapsulate naming plus `Symptom`/`RecoveryAction` wiring for each mechanism flavour.
- `_init_sm(...)` — prevents duplicate registration, extracts validated parameters, initialises debounce state, and registers derivative sampling for `sm_tc_2`.
- `_extract_params(...)` and `_create_safety_mechanism_instance(...)` — normalise YAML dictionaries into the `SafetyMechanism` constructor payload, including optional actuators and forecast spans.
- `_get_temperature_value(sensor_id, entities_changes)` — prioritises stubbed readings during dry runs before falling back to `SafetyComponent.get_num_sensor_val`.

### 5.4 FaultManager

- Aggregation: Converts YAML definitions into runtime `Fault` objects, initialises SMs (`init_safety_mechanisms`), and maintains `symptoms` / `faults` registries.
- State management: `_set_fault` and `_clear_fault` synthesise `fault_tag` hashes, mutate HA entities, merge supplemental attributes via `_determinate_info`, and coordinate NotificationManager/RecoveryManager callbacks.
- Enablement flow: `enable_all_symptoms` iterates across SMs, toggles them to `ENABLED`, and invokes the SM functions immediately to capture baseline states; disable paths call `disable_symptom` to reset to `NOT_TESTED`.
- Concerns: Accesses component internals; lacks persistence/evidence logging; relies on correct `related_symptoms` mapping to avoid configuration errors.

#### Public Interfaces
- `__init__(hass, modules, symptoms, faults)` — stores orchestrator references and precomputes the working registries.
- `register_callbacks(recovery_cb, notification_cb)` — injects recovery and notification hooks invoked on fault transitions.
- `init_safety_mechanisms()` — walks all symptoms to call their module-specific `init_safety_mechanism` implementations.
- `get_all_symptom()` — exposes the internal symptom registry for diagnostics.
- `enable_all_symptoms()` — enables every configured mechanism and immediately executes them to seed debounce counters.
- `set_symptom(symptom_id, additional_info)` / `clear_symptom(symptom_id, additional_info)` — public entry points used by components to mutate symptom state.
- `disable_symptom(symptom_id, additional_info)` — resets symptom tracking and clears mapped HA entities when mechanisms are disabled.
- `check_symptom(symptom_id)` / `check_fault(fault_id)` — return the current `FaultState` for orchestration logic.
- `found_mapped_fault(symptom_id, sm_id)` — resolves the `Fault` object tied to a symptom/SM pair.
- `enable_sm(sm_name, sm_state)` — toggles individual safety mechanisms, including rerunning logic when re-enabled.
- `get_system_fault_level()` and `update_system_state_entity()` — compute the highest active severity and push results to `sensor.system_state`.

#### Key Private/Helper Functions
- `_set_fault(symptom_id, additional_info)` — aggregates contributing symptoms, stamps a `fault_tag`, updates HA entities, and calls recovery/notification hooks.
- `_determinate_info(entity_id, additional_info, fault_state)` — merges or strips additional metadata when updating HA sensor attributes.
- `_clear_fault(symptom_id, additional_info)` — evaluates whether related symptoms are healed, clears entity state, and cascades notifications.
- `_generate_fault_tag(fault, additional_info=None)` — stable SHA-256 hash builder ensuring consistent tags for correlated events.

### 5.5 NotificationManager

- Behaviour: Maintains `active_notification` registry keyed by `fault_tag`, composes persistent `notify/notify` payloads with dashboard links, and drives auxiliary services per severity (alarm trigger + red lights for Level 1, yellow lighting for Level 2).
- Extensibility: `level_methods` map severity tiers to optional call-backs, enabling future integration of Level 3/4 handlers while defaulting to logging when unimplemented.
- Clearing: Uses `clear_notification` service requests to retract persistent notifications and ensures local registry consistency.
- Concerns: Level 3/4 not handled; embedded notification structure; unstructured logging; relies on downstream HA entities existing.

#### Public Interfaces
- `__init__(hass_app, notification_config)` — caches HA context plus severity-specific configuration and seeds the `level_methods` dispatch table.
- `notify(fault, level, fault_status, additional_info, fault_tag)` — primary entry point invoked by `FaultManager` to either publish or clear notifications per fault event.

#### Key Private/Helper Functions
- `_process_active_fault(level, message, fault_tag)` / `_process_cleared_fault(level, fault_tag)` — manage the lifecycle of tagged notifications and invoke severity-specific side effects.
- `_set_dashboard_notification(message, level)` — writes severity-scoped text to configured dashboard entities.
- `_notify_level_1_additional()` and `_notify_level_2_additional()` — trigger alarm and lighting scenes aligned with the configured severity.
- `_prepare_notification_data(level, message, fault_tag)` — builds the payload for `notify/notify`, including persistent tags and UI deep-links.
- `_notify_company_app(level, message, fault_tag, fault_state)` — ensures the appropriate service calls are executed and logged, routing through `_handle_notify_reg` and `_send_notification`.
- `_clear_company_app(level, fault_tag)` — retracts persistent notifications using the same tag and updates the in-memory registry.
- `_add_recovery_action(...)`, `_add_rec_msg(...)`, `_clear_symptom_msg(...)` — mutate stored notification payloads to append recovery guidance or clearance messaging before re-sending.

### 5.6 RecoveryManager

- Execution: Initialises per-recovery HA sensors, computes potential `RecoveryResult` objects by calling configured `rec_fun`, and writes actuator states while trapping `set_state` exceptions.
- Validation: Performs dry-run simulations via `_is_dry_test_failed`, checking whether proposed state changes would trip other enabled SMs, and `_isRecoveryConflict` to respect higher priority faults before proceeding.
- Post-processing: Updates notifications with recovery guidance, registers state listeners to detect when manual steps complete, and clears recovery state when symptoms heal.
- Concerns: Coupled to HA listeners; lacks state machine clarity; needs hazard awareness; private `_add_recovery_action` call bypasses NotificationManager public API.

#### Public Interfaces
- `__init__(hass_app, fm, recovery_actions, common_entities, nm)` — wires collaborators, stores configured recovery callables, and initialises their HA entities.
- `recovery(symptom, fault_tag)` — invoked by `FaultManager` when a symptom sets; orchestrates validation, execution, and notification updates for the selected recovery action.

#### Key Private/Helper Functions
- `_init_all_rec_entities()` / `_set_rec_entity(recovery)` — create and maintain HA state representations for each recovery action.
- `_isRecoveryConflict(symptom)` with `_get_matching_actions(...)` and `_check_conflict_with_matching_actions(...)` — inspect priority conflicts before running recoveries.
- `_perform_recovery(symptom, notifications, entities_changes, fault_tag)` — central execution path that finds the matching `RecoveryAction`, applies entity updates, and appends notifications.
- `_find_recovery(symptom_name)` and `_get_potential_recovery_action(...)` — resolve configured recovery handlers for the current symptom context.
- `_is_dry_test_failed(symptom, entities_changes)` and `_validate_recovery_action(symptom, recovery)` — perform dry-run simulations and guard conditions before actuating.
- `_execute_recovery(symptom, recovery, entities_changes)` and `_recovery_performed(symptom, result)` — apply state changes, catch exceptions, and log the outcome.
- `_handle_cleared_state(symptom)` / `_recovery_clear(symptom)` / `_listen_to_changes(symptom, entities_changes)` — manage post-recovery monitoring, listener registration, and clean-up.

### 5.7 DerivativeMonitor

- Sampling: Enforces singleton initialisation, registers entities with sampling rate/saturation thresholds, and seeds derivative history deques for moving-average smoothing.
- Computation: Schedules `_calculate_diff` via `run_every`, clamps derivatives within configured bounds, filters results, and writes `_rate` entities (second derivative currently logged but not published).
- Accessors: Exposes getter functions to retrieve cached derivative values for other components.
- Concerns: Retains state across reloads; no reset; test issues; no error handling; second derivative entity updates commented out.

#### Public Interfaces
- `__new__(...)` / `__init__(hass_app)` — enforce singleton semantics while capturing the AppDaemon context and initialising storage dictionaries once.
- `register_entity(entity_id, sample_time, low_saturation, high_saturation)` — records per-entity sampling configuration, creates derivative HA entities, and primes filter buffers.
- `schedule_sampling(entity_id, sample_time)` — registers periodic callbacks via `run_every` to feed `_calculate_diff`.
- `get_first_derivative(entity_id)` / `get_second_derivative(entity_id)` — expose cached derivative results to consumers such as `TemperatureComponent`.

#### Key Private/Helper Functions
- `_calculate_diff(entity_id=..., sample_time=...)` — fetches sensor readings, clamps and filters derivative values, updates histories, and publishes the smoothed results.
- `_get_entity_value(entity_id)` — wraps Home Assistant state retrieval with logging and guards against missing data.

### 5.8 Config Handling

- Process: `SafetyFunctions.initialize` ingests `app_cfg.yaml` sections, builds a combined configuration snapshot, and passes component-specific dictionaries to factory methods.
- Utilities: `cfg_parser.get_faults` constructs `Fault` objects while component helpers copy dictionaries to avoid mutation of shared config.
- Concerns: No schema validation; hard-coded component mapping; missing error reporting when derived configs are empty beyond initial guard.

### 5.9 Logging & Diagnostics

- Current state: Extensive docstring-driven logging at DEBUG level from decorators, managers, and DerivativeMonitor to trace SM execution, derivative calculations, and recovery validation steps.
- Gaps: Logs remain unstructured strings; no central correlation IDs; health entity attributes carry raw configuration but no runtime counters; watchdog/self-test hooks absent.

### 5.10 Modes & Safe States

- SYS defines modes; none implemented.

---

## 6. Testing

### 6.1 Current Coverage

- Pytest covers TC, FM, NM, RM with mocks.
- Relies on heavy HA mocking.

### 6.2 Testability Concerns

- Real listener registration; singleton state leakage; scheduler coupling.

### 6.3 Future Strategy

- Introduce adapter interfaces for HA services.
- Reset hooks for singletons.
- Extend tests for config errors, recovery conflicts, notification clearing.

---

## 7. Improvement Backlog

1. Dynamic component registration (no hard-coding).
2. Config schema & validation layer.
3. Mode management state machine.
4. Timeout & watchdog for SMs.
5. Structured logging + evidence persistence.
6. Extend hazards (over-temp, fire, gas, water, etc.).
7. RecoveryManager refactor (conflict handling, hazard-aware).
8. DerivativeMonitor lifecycle reset.
9. Complete notification levels 3/4.
10. Self-diagnostics & health metrics.

---

## 8. Traceability

- Hazard ↔ Requirement linkage maintained in SYS/HARA.
- Current implementation covers **Cold Exposure hazard (HARA §1.1)**.
- Trace matrix to be expanded as new hazard components are added.

---

## 9. Document Control

- **Owner**: Safety Architecture / Development Team.
- **Version**: 0.2.0 (merged SSRD + SafetyComponent doc).
- **Status**: Working draft; baseline for multi-hazard expansion.

---

✅ This combined doc unifies both sources. It keeps SSRD structure (purpose → context → requirements → architecture → design → testing → backlog → traceability).
Do you want me to also **insert a proper traceability matrix table** (Hazard → SYS Req → SW Req → Test Case) at the end, like in your SYS doc?
