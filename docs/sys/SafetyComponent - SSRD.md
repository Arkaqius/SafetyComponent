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

- **SafetyFunctions (AppDaemon app)**: Orchestrator; loads config; instantiates components; wires FM/NM/RM; sets health entity.
- **SafetyComponent (abstract base)**: Provides SM lifecycle, debouncing, FM integration, decorator for enable/disable & retries.
- **TemperatureComponent (MVP)**: Implements under-temperature & forecast SMs.
- **FaultManager**: Owns Symptom/Fault models, aggregates, manages lifecycle.
- **NotificationManager**: Maps fault lifecycle to HA notify service.
- **RecoveryManager**: Orchestrates recovery actions, resolves conflicts.
- **DerivativeMonitor**: Singleton calculating derivatives, publishing `_rate` entities.
- **CommonEntities**: Accessor for shared HA entities.

### 4.2 Data Flow Summary

1. YAML config → SafetyFunctions → component factory.
2. Components register SMs; decorator handles debounce + FM.
3. HA triggers SM; SafetyComponent → FM.
4. FM updates Fault state → NM + RM.
5. RM executes recovery actions; NM sends notifications.
6. DerivativeMonitor runs periodically; outputs consumed by TC forecast SM.

### 4.3 Deployment

- Runs in HA/AppDaemon container.
- Interfaces: `set_state`, `listen_state`, `run_in`, `run_every`, `call_service`.
- Debugging: `remote_pdb` when enabled.

---

## 5. Detailed Design

### 5.1 SafetyFunctions

- Initialization: Load YAML, instantiate components, wire FM/NM/RM, expose entities.
- Issues: Hard-coded component dict; no shutdown hooks; no mode management.

### 5.2 SafetyComponent Base

- Responsibilities: Debounce logic, FM integration, SM decorator.
- Issues: Tight HA scheduler coupling; no timeout; hidden dependency on DerivativeMonitor.

### 5.3 TemperatureComponent

- SMs: `sm_tc_1` (threshold), `sm_tc_2` (forecast).
- Concerns: Intermixed config parsing; no high-temperature support; silent skips on missing config.

### 5.4 FaultManager

- Aggregates faults; enables/disables SMs; updates system state.
- Concerns: Accesses component internals; lacks persistence/evidence logging.

### 5.5 NotificationManager

- Formats & sends HA notifications.
- Concerns: Level 3/4 not handled; embedded notification structure; unstructured logging.

### 5.6 RecoveryManager

- Executes/validates recovery actions.
- Concerns: Coupled to HA listeners; lacks state machine clarity; needs hazard awareness.

### 5.7 DerivativeMonitor

- Singleton; calculates derivatives.
- Concerns: Retains state across reloads; no reset; test issues; no error handling.

### 5.8 Config Handling

- Parsed in SafetyFunctions; passed raw to components.
- Concerns: No schema validation; hard-coded component mapping.

### 5.9 Logging & Diagnostics

- Basic `log` calls; no structured fields; no self-test/watchdog.

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
