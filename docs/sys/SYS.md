# Lean SYS + TSC — Safety Architecture & Requirements (v0.3a)

**Item:** Home Automation Safety Monitoring & Recovery (multi-hazard)

**Date:** 2025-09-18
**Owner:** System/Safety (SYS)
**Status:** Working Draft → for SYS review
**Scope:** Blend **ASPICE SYS.x** with **ISO 26262-3/4/6** work products; align with provided **HARA**

---

## 1 Purpose and Audience

- Provide a **single, lean specification** that turns the existing **HARA** (hazards, S/E/C, initial risk levels) into actionable **Safety Goals, System Requirements, Technical Safety Requirements, Safe States, and FTTI budgets**.
- Maintain **end‑to‑end traceability** from _hazard → safety goal → requirement → verification_, while minimizing work products for a **hobby/semiprofessional, open‑source** effort (no formal certification claim).
- Serve as the **source of truth** for the concept phase and subsequent implementation/validation; any YAML/CSV/config artifacts are generated from this document.

**Scope of this document:**

- Covers the **safety‑critical logic** of the _Home Automation Safety App_ (currently running atop **Home Assistant + AppDaemon**), specifically: detection, decision, and **actuation** for hazards identified in HARA (Fire/Smoke, Gas, CO, Water Leak, **Undercooling/Overheating**, Air Quality, System/Comms failure, HVAC degradation, Unauthorized Access/Privacy, Rain/Ingress).
- Defines **safety goals, SYS‑level requirements (blended with FSR), TSRs, safe states, timing (FTTI), parameters, and V\&V** at the **system level**. Software architecture details of a specific implementation are **intentionally out of scope for now** and will be adapted later.

**Out of scope (for clarity):**

- General home‑automation conveniences (scenes, presence lighting, media, non‑safety automations).
- Brand‑specific hardware design/certification and regulatory approvals (this is a best‑effort, non‑certified project).
- Detailed software component design of your current app (to be integrated once concept is finalized).

---

## 2 System Boundaries

### 2.1 Internal Elements

- AppDaemon safety application (symptom, fault, hazard evaluators, orchestrator, notifier).
- Health monitoring, configuration parser, watchdogs.

### 2.2 External Elements

- Sensors (CO, smoke, water leak, temperature, window/door, motion, etc.).
- Actuators (valves, covers, switches, sirens, HVAC).
- Home Assistant core (entity registry, service calls).
- User interfaces (mobile notifications, TTS, logs).

### 2.3 Context Diagram

_(Insert block diagram – System vs. environment)_

---

## 3 System Modes

- **Normal** – No hazard, no internal fault.
- **Warning** – Symptom observed but not yet fault.
- **Hazard** – Confirmed hazard within FTTI.
- **Safe State External (SS-EXT)** – Hazard mitigations applied.
- **Safe State Internal (SS-INT)** – Internal failure fallback.
- **Recovery** – Returning to Normal after successful mitigation.

_(Include mode diagram if possible.)_

---

## 4 Safety Goals (SGs)

_(Reference HARA. Provide SG ID, hazard link, ASIL/criticality, FTTI.)_

| SG ID      | Hazard Ref. | Safety Goal                                                | Criticality      | FTTI |
| ---------- | ----------- | ---------------------------------------------------------- | ---------------- | ---- |
| SG-CO-01   | HAZ-CO-01   | Detect CO and alert user within 10 s; activate ventilation | Life-threatening | 10 s |
| SG-RAIN-01 | HAZ-RAIN-01 | Detect storm + open window, alert, auto-close              | Property-damage  | 30 s |
| …          | …           | …                                                          | …                | …    |

---

## 5 System Requirements

### 5.1 Functional Requirements

| ID              | Requirement                                                      | Linked SG  |
| --------------- | ---------------------------------------------------------------- | ---------- |
| SYS-REQ-CO-01   | Detect CO > threshold for 2 samples; notify within 2 s           | SG-CO-01   |
| SYS-REQ-RAIN-01 | If storm alert + window open >30s, notify and attempt auto-close | SG-RAIN-01 |

### 5.2 Non-Functional Requirements

| ID     | Requirement                                                    | Category       |
| ------ | -------------------------------------------------------------- | -------------- |
| NFR-01 | End-to-end hazard detection latency ≤2 s                       | Performance    |
| NFR-02 | System heartbeat ≥1 Hz, watchdog restart ≤3 s                  | Reliability    |
| NFR-03 | All hazard transitions logged with timestamp and IDs           | Diagnosability |
| NFR-04 | Config validated against schema; fallback to last known good   | Integrity      |
| NFR-05 | Notifications retried across at least two independent channels | Availability   |

---

## 6 Technical Safety Concept

### 6.1 External Hazard Mitigations

- **CO:** threshold check, debounce, notification, ventilation ON, boiler OFF.
- **Fire:** smoke detection, unlock exits, notify + siren.
- **Rain + Window:** storm condition + open state, notify, auto-close.
- **Water Leak:** sensor trigger, water main OFF, notify.

### 6.2 Internal Fault Detection & Mitigations

- Heartbeat entity → missed 3 beats = SS-INT.
- Sensor stale detection (age > 2× expected period).
- Actuator verification (command vs. state).
- Loop watchdog (cycle time <250 ms critical).
- Config schema validation.
- Controlled restart on unhandled exception.

### 6.3 Mode Arbitration

Final system mode = max(Layer A external, Layer B internal).
Arbitration applied every cycle (<100 ms).

### 6.4 Safe States

- **SS-EXT:** hazard-specific bundles executed within FTTI (ventilation, covers, cutoff valves).
- **SS-INT:** inhibit risky actuators, bias to safe defaults (gas OFF, covers CLOSED), raise persistent alarm every 60 s, keep minimal sensing + notification alive.

---

## 7 Timing & FTTI Budgeting

| Hazard        | FTTI | Detection Budget | Evaluation Budget | Mitigation Budget |
| ------------- | ---- | ---------------- | ----------------- | ----------------- |
| CO            | 10 s | 3 s              | 2 s               | 5 s               |
| Fire          | 15 s | 5 s              | 2 s               | 8 s               |
| Rain + Window | 30 s | 10 s             | 5 s               | 15 s              |

---

## 8 Glossary

- **FTTI:** Fault-Tolerant Time Interval.
- **SS-EXT:** Safe State triggered by external hazard.
- **SS-INT:** Safe State triggered by internal fault.
- **Symptom:** Raw detection event (unfiltered).
- **Fault:** Debounced/confirmed condition.

---

## 9 Parameter Table (Proposed Defaults)

_(To be replaced with calibrated HARA values.)_

| Parameter               | Default | Note                    |
| ----------------------- | ------- | ----------------------- |
| Heartbeat period        | 1 s     | Missed 3 beats ⇒ SS-INT |
| CO threshold            | 30 ppm  | Standard alarm trigger  |
| Window storm grace      | 30 s    | Before auto-close       |
| Actuator verify timeout | 5 s     | Fail ⇒ Degraded/SS-INT  |
