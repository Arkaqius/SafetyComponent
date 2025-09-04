# Backend PRD — Safety Functions (Brownfield)

**Date:** 2025-09-05
**Owner:** PM (John)
**Status:** Draft v0.3
**Companion:** See **Frontend PRD — Safety Functions (Brownfield)**

---

## 1) Executive Summary

Backend-first brownfield upgrade to achieve **HARA/SYS parity**, implement missing mechanisms, unify **prefault → fault → recovery** modeling, and add robust observability and deterministic testing. The frontend will surface evidence and metrics but is tracked in the companion PRD.

## 2) Goals & Non‑Goals

### Goals

* **SYS Parity:** Implement all in-scope SYS mechanisms and transitions (e.g., TC\_SM1, **TC\_SM2 — Forecasting**).
* **Determinism:** Seeded fixtures, injected clocks, reproducible simulations.
* **Traceability:** HARA → SYS → Code → Tests → Metrics mapping generated in CI.
* **Observability:** Structured logs + metrics at every decision point; evidence sink for last N decisions.

### Non‑Goals

* Engine rewrite or runtime migration.
* Semantic changes without documented SYS deltas and validation.

## 3) Current State (Inventory)

* Python engine with modules: `derivative_monitor.py`, `temperature_component.py`, `fault_manager.py`, `recovery_manager.py`, `notification_manager.py`, base abstractions (`safety_component.py`, `safety_mechanism.py`, `types_common.py`).
* Pytest suite present; some `.not_ready` tests indicate unimplemented paths.
* SYS mechanisms referenced: **TC\_SM1 LowTemperatureMonitoring**, **TC\_SM2 LowTemperatureForecasting**.

## 4) Gaps vs SYS

* **TC\_SM1** partial: lacks explicit prefault mapping, suppression windows, evidence logging.
* **TC\_SM2** missing: no module, config, recovery/notification branches, or trend data source.

## 5) Functional Requirements

### 5.1 TC\_SM1 — Complete & Harden

* Explicit enums/IDs for `PF_UNDERTEMP` and `F_UNDERTEMP` in `types_common.py` with SYS anchors.
* **Hysteresis** + **suppression windows** (per-room) with configurable thresholds.
* Decision evidence logging (inputs, thresholds, debounce/suppression states, outcome, latency).
* `fault_manager` acceptance hooks to persist **last decision** per mechanism/room.

### 5.2 TC\_SM2 — New Forecasting Mechanism

* Module `low_temp_forecast.py` using rolling window + EMA/AR baseline (bounded complexity).
* Config (`app_cfg.yaml`): `forecast_horizon_min`, `min_confidence`, `min_delta_deg`.
* **Shadow mode** first: emit `prefault_forecast` without recovery; promote to active once precision KPI met.
* Define guarded recovery / notification when active.

### 5.3 Unified Prefault/Fault Model

* Centralize IDs/enums in `types_common.py` with docstrings linking to SYS sections.
* Provide mapping table: Hazard ↔ Mechanism ↔ Code symbol ↔ Test ID.

### 5.4 Recovery & Notification

* `recovery_manager`: idempotent actions (bounded retries, cooldowns).
* `notification_manager`: leveled notifications (L1–L4) with templated payloads.

### 5.5 Configuration & Feature Flags

* Add flags: `enable_TC_SM1_v2`, `enable_TC_SM2_shadow`, `enable_TC_SM2_active` (default off).
* Thresholds/hysteresis/suppression/forecast params set in `backend/app_cfg.yaml`.

### 5.6 Observability & Evidence

* Structured JSON logs with: timestamp, room, rule\_id, decision, inputs, thresholds, debounce/suppression, action, latency.
* Metrics: counters (triggered/ignored), gauges (suppression active), timers (decision latency).
* Evidence sink: **last N decisions** list and **decision-by-ID** record (file or local endpoint).

### 5.7 Deterministic Testing & Simulation

* Seeded time-series fixture generators; replay harness for derivative & forecast logic.
* Convert `.not_ready` tests to executable; expand branch/path coverage across `fault_manager`/`recovery_manager`.
* CI gates: coverage delta, flake rate threshold.

## 6) Non‑Functional Requirements

* **Safety first:** Fail‑safe defaults; new features disabled by default.
* **Performance:** Decision loop within existing latency; forecasting O(window).
* **Compatibility:** Backward compatible configs; migration notes and diffs.
* **Auditability:** Code/doc comments link to HARA/SYS; CI publishes traceability artifacts.

## 7) Data & Interfaces

* **Config:** `backend/app_cfg.yaml` as source of truth.
* **Evidence API/File:** `GET /evidence?limit=N`, `GET /evidence/{id}` (or file sink).
* **Metrics export:** counters/gauges/timers for FE Trends.

## 8) Risks & Mitigations

| Risk                               | Impact | Mitigation                                                 |
| ---------------------------------- | ------ | ---------------------------------------------------------- |
| Over-suppression hides real faults | High   | Shadow trials, guardrails, targeted alarms                 |
| Forecasting noise                  | Medium | Confidence thresholds, window tuning, validation in shadow |
| Test flakiness                     | Medium | Seeded fixtures, injected clocks, CI gates                 |

## 9) Metrics & Acceptance Criteria

**Backend Metrics**

* **TC\_SM1 precision** +20% vs baseline; **recall** within ±3%.
* **TC\_SM2 shadow precision** ≥ 70% at configured confidence before activation.
* **Coverage:** +15% lines and +20% branches across mechanisms & managers.
* **Latency:** p95 within existing budget.

**Sample Acceptance**

* Oscillation near threshold does **not** flap with hysteresis/suppression; logs include rule\_id + debounce info.
* Breach > T sec escalates `PF_UNDERTEMP` → `F_UNDERTEMP` with a single recovery attempt recorded.
* Forecast breach with confidence ≥ X logs **prefault\_forecast** only in shadow; metrics incremented.
* Traceability artifact lists HARA→SYS→Code→Test IDs for TC\_SM1/TC\_SM2.

## 10) Release Plan

* **Phase 0:** Enums/IDs, evidence logging, flags, seeded fixtures, traceability scaffolding.
* **Phase 1:** TC\_SM1 hardening (hysteresis/suppression, prefault→fault, observability).
* **Phase 2:** TC\_SM2 shadow mode; tune to KPI.
* **Phase 3:** TC\_SM2 active with guarded recovery/notification; rollback via flag.

## 11) Open Questions

* Host/runtime of engine (service/daemon/embedded)?
* External notification consumers beyond scope?
* Exact sampling/window configuration constraints from SYS?
