# Architecture Review — Alignment to SYS v0.2 (v0.2)

**Date:** 2025-09-05
**Author:** Solution Architect
**Status:** Applied update to align with SYS v0.2

---

## 1) Context & Objectives

Align the brownfield architecture to **SYS v0.2** across all SG-001..SG-011 by adding missing mechanisms (SM3..SM10), evidence/metrics interfaces, flags, and determinism. Preserve stability via shadow/feature-flag rollouts.

---

## 2) Runtime / Component View (To-Be)

* **Mechanisms:**

  * **SM1** LowTemperatureMonitoring (SG-001)
  * **SM2** LowTemperatureForecasting (SG-002)
  * **SM3** HighTemperatureMonitoring (SG-004)
  * **SM4** AirQualityMonitoring & Forecasting (SG-005)
  * **SM5** Fire/Smoke Detection (SG-006)
  * **SM6** Gas Detection (SG-007)
  * **SM7** CO Detection (SG-008)
  * **SM8** Water Leak Detection (SG-009)
  * **SM9** HVAC Health Monitoring (SG-010)
  * **SM10** Window/Door + Weather Supervision (SG-011)
* **Managers:** `fault_manager`, `recovery_manager`, `notification_manager`
* **Observability:** Evidence Sink (file/HTTP), Metrics Export
* **UI:** Evidence Pane, Fault Detail drawer, Trends, Log filters

---

## 3) Sequence — Decision Loop

1. Acquire sensor + config + timebase
2. Evaluate mechanisms (SM1..SM10)
3. Consolidate PF→F in `fault_manager`
4. Execute recovery/notification (bounded, idempotent)
5. Emit evidence + metrics
6. UI consumes evidence/metrics; operators triage

---

## 4) Interfaces & Contracts

* **Evidence**

  * `GET /evidence?limit=N` → `[DecisionSummary]`
  * `GET /evidence/{id}` → `DecisionDetail`
  * **Schema v1**: timestamp, room, rule\_id, decision, inputs (min/max/avg), thresholds, debounce/suppression, action, latency
* **Metrics**

  * Counters: `decisions_total{rule,decision}`
  * Gauges: `suppression_active`
  * Timers: `decision_latency_ms` (p50/p95)
* **Flags (read-only)**

  * `/flags` returns: `enable_TC_SM1_v2`, `enable_TC_SM2_shadow`, `enable_TC_SM2_active`, `enable_SM3_hot`, `enable_SM4_aq`, `enable_SM5_fire`, `enable_SM6_gas`, `enable_SM7_co`, `enable_SM8_leak`, `enable_SM9_hvac`, `enable_SM10_window_weather`

---

## 5) Determinism & Testability

* Injected monotonic clock across mechanisms.
* Seeded time-series fixture generators; replay harness for SM1/2/3/4.
* Convert `.not_ready` tests; add branch coverage in managers.
* CI gates: coverage delta, flake rate threshold; publish `traceability.md` and `mapping.json`.

---

## 6) Migration & Rollout Plan

* **P0:** Scaffolding (enums/IDs, evidence/metrics, flags, fixtures, traceability).
* **P1:** Temp cold (SM1 hardening, SM2 shadow) + FE Evidence.
* **P2:** Hot & AQ (SM3/SM4 shadow) + FE Trends/filters.
* **P3:** Life safety (SM5/6/7) with alarm paths & latency checks.
* **P4:** Infrastructure (SM8/SM9) shadow→active.
* **P5:** Contextual (SM10) prompts; FE polish.
* **P6:** Default-on for mechanisms meeting KPIs; rollback strategy maintained.

---

## 7) Risks & Mitigations (delta)

| Risk                                 | Impact | Mitigation                                                     |
| ------------------------------------ | ------ | -------------------------------------------------------------- |
| Interface creep across 10 mechanisms | Medium | Shared evidence schema; strict versioning; ADRs                |
| Alarm fatigue (SM5/6/7)              | High   | Conservative defaults, test alarm latencies, operator training |
| Overhead from forecasting            | Medium | Bounded EMA/AR; narrow windows; p95 latency gates              |
| Weather API instability              | Low    | Cache + debounce; fall back to last-known conditions           |

---

## 8) ADRs (to write)

1. Evidence schema v1 and versioning.
2. Deterministic timebase strategy.
3. Forecasting baseline (EMA/AR) with activation criteria.
4. Feature-flag taxonomy and rollout policy.

---

## 9) Traceability Alignment

* Map SG-001..011 → FSRs → TSRs → Code symbols → Test IDs → Metrics.
* Update `traceability.md` and `mapping.json` generators to include SM3..SM10.
