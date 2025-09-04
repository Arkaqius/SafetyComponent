# Brownfield PRD — Safety Functions (Backend + Frontend) — v0.2 (SYS-aligned)

**Date:** 2025-09-05
**Owner:** PM (John)
**Status:** Draft v0.2
**References:** SYS v0.2 (SG/FSR/TSR), Architecture Review v0.1

---

## 1) Executive Summary

This PRD is aligned with **SYS v0.2** and remains **backend-first**. Objectives include full **SYS parity** across in-scope hazards: TC\_SM1/SM2 (cold-side monitoring/forecasting) **plus** SM3..SM10 (hot-side, air quality, fire/gas/CO, water leak, HVAC health, window/weather). We will implement missing mechanisms, unify prefault/fault models, and harden `fault_manager`/`recovery_manager` with deterministic tests and observability, while surfacing evidence in the UI.

## 2) Goals & Non‑Goals

### Goals (backend-first, SYS-aligned)

* **SYS Parity:** Implement/enable mechanisms per **SYS v0.2** for SG-001..SG-011.
* **Traceability:** HARA → SYS (SG/FSR/TSR) → Code → Tests → Metrics; publish `traceability.md` and `mapping.json` from CI.
* **Signal Quality:** Reduce false positives/negatives via tunable thresholds, hysteresis, suppression.
* **Deterministic Engine:** Strengthen coverage for managers/mechanisms with seeded, replayable fixtures.
* **Observability:** Structured logs + metrics; evidence sink consumed by UI.

### Non‑Goals

* Engine/runtime rewrites.
* Semantics changes without SYS deltas and validation.
* Broad UI redesign.

## 3) Inventory (delta)

* **Mechanisms:** SM1/SM2 existing; add **SM3..SM10** per SYS v0.2.
* **Flags:** `enable_TC_SM1_v2`, `enable_TC_SM2_shadow`, `enable_TC_SM2_active`, `enable_SM3_hot`, `enable_SM4_aq`, `enable_SM5_fire`, `enable_SM6_gas`, `enable_SM7_co`, `enable_SM8_leak`, `enable_SM9_hvac`, `enable_SM10_window_weather`.

## 4) Scope (Functional)

### 4.1 Core Temperature

* **SM1** (SG-001): prefault→fault mapping, hysteresis/suppression, evidence.
* **SM2** (SG-002): forecast in shadow, precision KPI ≥ 70% before activation.

### 4.2 Additional Mechanisms (per SYS v0.2)

* **SM3 HighTemperatureMonitoring** (SG-004, FSR-011, TSR-110..112).
* **SM4 AirQualityMonitoring & Forecasting** (SG-005, FSR-020/021, TSR-120..122).
* **SM5 Fire/Smoke** (SG-006, FSR-030, TSR-130).
* **SM6 Gas** (SG-007, FSR-040, TSR-140).
* **SM7 CO** (SG-008, FSR-050, TSR-150).
* **SM8 Water Leak** (SG-009, FSR-060, TSR-160..161).
* **SM9 HVAC Health** (SG-010, FSR-070, TSR-170).
* **SM10 Window/Weather** (SG-011, FSR-080, TSR-180).

### 4.3 Evidence & Metrics

* Evidence schema v1 (JSON) and endpoints (`/evidence`, `/evidence/{id}`); metrics snapshot with counters/gauges/timers.

### 4.4 Frontend Support

* Evidence Pane and Fault Detail drawer; Trends (alert rate, suppression %, recovery %, latency); Log filters; deep link to raw JSON.

## 5) Non‑Functional

* **Safety First, Determinism, Performance, Compatibility, Auditability** — as per SYS v0.2 and Architecture Review.

## 6) Metrics & Acceptance

* **Cold-side:** +20% precision; recall ±3%; shadow precision ≥ 70% (SM2).
* **Hot-side:** No flapping with H\_hot/S\_hot; emergency cooling on F\_OVERTEMP; evidence logged.
* **AQ:** Prefault\_forecast\_aq in shadow only; on breach, purifier/vent action recorded; stale-data diag.
* **Fire/Gas/CO:** L1 within T\_notify; evidence captured; decision loop non-blocking.
* **Leak:** Valve close within T\_act; evidence includes action result.
* **HVAC:** ROC anomaly → maintenance notify with evidence.
* **Window/Weather:** Prompt on rain/storm + open window; decision context logged.

## 7) Release Plan

* **P0:** Scaffolding (enums/IDs, evidence, flags, fixtures, traceability).
* **P1:** SM1 hardening + SM2 shadow + FE Evidence Pane.
* **P2:** SM3/SM4 shadow + Trends/filters.
* **P3:** SM5/SM6/SM7 alarm paths; verify latencies.
* **P4:** SM8/SM9 shadow→active; valve/maintenance actions.
* **P5:** SM10 prompts; FE polish.
* **P6:** Default-on for mechanisms meeting KPIs; docs & rollback.
