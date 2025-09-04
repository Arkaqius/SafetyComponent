# Frontend PRD — Safety Functions (Brownfield)

**Date:** 2025-09-05
**Owner:** PM (John)
**Status:** Draft v0.3
**Companion:** See **Backend PRD — Safety Functions (Brownfield)**

---

## 1) Executive Summary

Frontend work focuses on **operator triage** by exposing backend evidence and trends. We will not redesign the UI broadly; instead, we will add focused surfaces (Evidence Pane, Fault Detail drawer, Trends cards, and Log Explorer filters) so operators can see **what the engine decided and why**.

## 2) Goals & Non‑Goals

### Goals

* **Evidence-first UX:** Immediate visibility of last decisions with inputs/thresholds/outcomes.
* **Faster triage:** Filters and deep links to raw JSON evidence; trends for alert/suppression/recovery.
* **Transparency:** Surface feature-flag status and last evidence ingest time.

### Non‑Goals

* Broad visual redesign or component library migration.
* Changing safety semantics in UI.

## 3) Target Users

* **Operator:** Needs clear, timely evidence and next actions.
* **Safety Engineer/QA:** Needs auditable, exportable decision data aligned to backend.

## 4) Scope & Features

### 4.1 Evidence Pane (All Pages)

* Right-side drawer showing **last N decisions** with: timestamp, room, rule\_id, inputs (min/max/avg), thresholds, debounce/suppression state, outcome, action link.
* Appears on Dashboard, LogPage, Temperature.

### 4.2 Fault Detail Drawer

* Sparkline (last 60 min) of the relevant signal(s) with overlay of threshold & hysteresis bands.
* Button **View Raw JSON** deep-links to the exact evidence payload (from backend evidence endpoint/file).
* Show recovery attempts and last success time if available.

### 4.3 Trends & Metrics

* Cards for: alert rate, suppression active %, recovery success %, decision latency p50/p95.
* Data source: backend metrics (counters/gauges/timers).
* Minimal Trends view or Dashboard section.

### 4.4 Log Explorer Upgrades

* Structured filters (chips) for `rule_id`, `room`, `decision` (shadow/active), time window.
* Live tail toggle, pagination; export of filtered rows as JSON.

### 4.5 Navigation & Status

* Topbar shows engine status: feature flags and last evidence ingest time.

### 4.6 Accessibility & Performance

* Keyboard navigation through lists/drawers; ARIA labels; high-contrast support.
* Performance targets: p95 drawer open ≤ 250 ms with cached last N decisions; p95 initial route ≤ 2 s.

## 5) Data & Interfaces

* **Evidence endpoint/file** provided by backend: `GET /evidence?limit=N`, `GET /evidence/{id}`.
* **Metrics source** exported by backend for Trends cards.
* Feature flags exposed to UI for status display: `enable_TC_SM1_v2`, `enable_TC_SM2_shadow`, `enable_TC_SM2_active`, UI flags `show_evidence_pane`, `show_trends`.

## 6) Non‑Functional Requirements

* **Reliability:** UI resilient to delayed evidence; retries and empty states.
* **Usability:** Keyboard-first flows; screen-reader labels; consistent focus states.
* **Performance:** As per targets; minimal additional bundle weight.

## 7) Acceptance Criteria

* **Evidence Pane:** New decisions appear within ≤ 2s; each shows inputs/thresholds/outcome; deep link opens exact JSON payload.
* **Fault Detail Sparkline:** Overlays threshold & hysteresis bands; hover reveals values; time range adjustable (15/60/180 min).
* **Filters:** Selecting `rule_id=TC_SM2` + `decision=shadow` filters list and export includes only visible rows.
* **Status:** Topbar shows current feature flags and last ingest time.

## 8) Metrics

* **Triage speed:** median time to evidence ↓ 25%.
* **Usability:** SUS ≥ 75 on evidence flows.
* **Performance:** p95 drawer open ≤ 250 ms; p95 first meaningful paint ≤ 2 s.

## 9) Release Plan (Aligned with Backend)

* **Phase 1:** Evidence Pane (read-only) + Topbar status.
* **Phase 2:** Trends cards + Log Explorer filters; integrate shadow/active decision badges.
* **Phase 3:** Polish: a11y/perf; export UX; help/tooltips.

## 10) Open Questions

* Confirm evidence pagination and retention policy.
* Preferred placement for Trends (card vs page).
* Localization needs, if any.
