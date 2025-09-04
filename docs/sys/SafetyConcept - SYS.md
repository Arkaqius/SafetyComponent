# SYS — Safety Concept & System Requirements (v0.2)

**Date:** 2025-09-05
**Owner:** Safety (SYS)
**Status:** Working Draft — **Applied updates:** ASIL/FTTI assigned (provisional), new SG/FSR/TSR added, traceability hooks

**Source Inputs:** HARA (stakeholder analysis & hazards), PRD (backend-first), Architecture Review v0.1, SYS Review vs HARA v0.1
**Traceability IDs:** SG-xxx (Safety Goals), FSR-xxx (Functional Safety Requirements), TSR-xxx (Technical Safety Requirements)

> IMPORTANT: ASIL and FTTI values below are **proposed** based on typical S/E/C assumptions. Replace with exact HARA-derived values during confirmation.

---

## 1) Item Definition (ID)

**Item:** Safety Monitoring & Recovery for temperature-controlled rooms.
**Primary Purpose:** Detect, forecast, and mitigate environmental hazards (undercooling/overheating, AQ, fire/gas/CO, water leaks) and system failures to maintain safe operation.
**Operating Modes:** Normal, Startup, Shutdown, Maintenance/Service, Degraded (safe state).
**Environmental Conditions:** T: −20…+50 °C ambient; supply voltage per platform; timebase accuracy per host.
**System Boundaries:** Sensors → Safety Mechanisms → Fault Manager → Recovery/Notification → Evidence/UX.
**Assumptions of Use (AoU):**

* A1. Sensors calibrated and provide updates ≥ **f\_sensor\_min** Hz; communication error rate ≤ **p\_comm\_max**.
* A2. System timebase accuracy ≤ **Δt\_max** ms; persistent storage available for evidence.
* A3. Operator response to L3/L4 notifications within **T\_op\_resp** minutes (platform process).
* A4. Actuation available within **T\_act** seconds to effect temperature/AQ changes or shutoff valves.

---

## 2) Safety Goals (SG) — with ASIL & FTTI (provisional)

| ID         | Safety Goal                                                                               | Hazard(s) Ref     | **ASIL**      | **FTTI**   | Safe State                                      |
| ---------- | ----------------------------------------------------------------------------------------- | ----------------- | ------------- | ---------- | ----------------------------------------------- |
| **SG-001** | Prevent sustained **undercooling** below **T\_min** > **T\_crit** in occupied rooms.      | HZ-UNDERTEMP-01   | **ASIL B**    | **10 min** | **SS-1:** Fallback heating + L3 notify          |
| **SG-002** | Provide timely **prediction** of approaching undercooling to enable preventive action.    | HZ-UNDERTEMP-02   | **QM/ASIL A** | **10 min** | **SS-1**                                        |
| **SG-003** | Detect **sensor/communication faults** that could mask hazards; transition to safe state. | HZ-SYSTEM-FAIL-01 | **ASIL B**    | **60 s**   | **SS-2:** Isolate faulty channel + L3           |
| **SG-004** | Prevent sustained **overheating** above **T\_max** > **T\_crit\_hot** in occupied rooms.  | HZ-OVERTEMP-01    | **ASIL B**    | **5 min**  | **SS-1:** Emergency cooling/ventilation + L2/L3 |
| **SG-005** | Maintain acceptable **indoor air quality**; detect/forecast breach and mitigate.          | HZ-AQ-01          | **ASIL A**    | **10 min** | **SS-1:** Ventilate/purify + L2                 |
| **SG-006** | Detect **smoke/fire** promptly; alert occupants; enter alarm safe state.                  | HZ-FIRE-01        | **ASIL C**    | **10 s**   | **SS-Alarm:** Siren/lighting + L1               |
| **SG-007** | Detect **flammable gas** accumulation; alert and ventilate safely.                        | HZ-GAS-01         | **ASIL C**    | **10 s**   | **SS-Alarm:** Ventilate + L1                    |
| **SG-008** | Detect **CO** accumulation; alert and ventilate; escalate alarms.                         | HZ-CO-01          | **ASIL C**    | **10 s**   | **SS-Alarm:** Ventilate + L1                    |
| **SG-009** | Detect **water leak/flood**; alert and shut off supply if available.                      | HZ-WATER-01       | **QM/ASIL A** | **60 s**   | **SS-3:** Close valve + L2                      |
| **SG-010** | Detect **HVAC failures** affecting temp control; prompt maintenance before exposure.      | HZ-HVAC-01        | **QM/ASIL A** | **30 min** | **SS-4:** Degraded mode + L3                    |
| **SG-011** | Prevent **weather ingress** via open windows/doors during rain/storm.                     | HZ-WEATHER-01     | **QM**        | **120 s**  | **SS-5:** Prompt closure + L2                   |

> Replace ASIL/FTTI values with HARA-derived S/E/C table outputs as available.

---

## 3) Functional Safety Concept (FSC)

### 3.1 Functional Chain

1. **Acquire Signals** (temperature, AQ, smoke/gas/CO, leak, window/door, weather, system health)
2. **Evaluate Safety Mechanisms**:

   * **SM1:** LowTemperatureMonitoring
   * **SM2:** LowTemperatureForecasting
   * **SM3:** HighTemperatureMonitoring
   * **SM4:** AirQualityMonitoring & Forecasting
   * **SM5:** Fire/Smoke Detection
   * **SM6:** Gas Detection
   * **SM7:** CO Detection
   * **SM8:** Water Leak Detection
   * **SM9:** HVAC Health Monitoring
   * **SM10:** Window/Door + Weather Supervision
   * **SMx:** System Diagnostics (timeouts, ROC, stuck-at, stale-data)
3. **Determine State** (Prefault → Fault) and **Select Recovery**
4. **Notify** (L1–L4) and **Log Evidence**
5. **Enter/Exit Safe State** as required

### 3.2 FSC Requirements (FSR)

**Temperature (cold/hot)**

* **FSR-002:** Detect undercooling: **T\_room < T\_min** sustained **T\_det** with **hysteresis H** and **suppression S**.
* **FSR-003:** Predict undercooling breach within **H\_pred** when confidence ≥ **C\_min** and delta ≥ **ΔT\_min**.
* **FSR-011:** Detect overheating: **T\_room > T\_max** sustained **T\_det\_hot** with **H\_hot**/**S\_hot**.

**Diagnostics & Prefault/Fault**

* **FSR-004:** Escalate **PF → F** when breach persists for **T\_escalate** within FTTI.
* **FSR-007:** Detect sensor/comm faults (range, stuck-at, ROC, timeout); enter **SS-2**.

**Recovery/Notification/Evidence**

* **FSR-005:** On **F\_UNDERTEMP/F\_OVERTEMP**, command safe actuation (fallback heating/emergency cooling) with idempotent retries and cooldowns.
* **FSR-006:** Emit appropriate notification level (L1–L4) within **T\_notify** seconds.
* **FSR-008:** Record decision evidence (inputs, thresholds, debounce/suppression, outcome, latency, rule\_id).
* **FSR-009:** Exit safe state only when stabilization criteria met for ≥ **T\_stable**.

**Other Hazards**

* **FSR-020:** Monitor AQ vs thresholds; **FSR-021** forecast AQ breach; actuate ventilation/purifiers.
* **FSR-030:** Detect smoke/fire; enter alarm safe state (siren, lights).
* **FSR-040/050:** Detect gas/CO; enter alarm safe state and ventilate.
* **FSR-060:** Detect water leak; close shutoff valve (if available).
* **FSR-070:** Monitor HVAC health (flow temp, ROC); pre-emptively notify maintenance.
* **FSR-080:** When rain/storm and windows/doors open, notify to close.

**FSC → SG Mapping:**

* SG-001: FSR-002/004/005/006/008/009
* SG-002: FSR-003/006/008
* SG-003: FSR-007/006/008
* SG-004: FSR-011/004/005/006/008/009
* SG-005: FSR-020/021/006/008
* SG-006: FSR-030/006/008
* SG-007: FSR-040/006/008
* SG-008: FSR-050/006/008
* SG-009: FSR-060/006/008
* SG-010: FSR-070/006/008
* SG-011: FSR-080/006/008

---

## 4) Technical Safety Concept (TSC) — TSRs

**Acquisition & Timebase**

* **TSR-001:** Injected monotonic clock; clock error ≤ **Δt\_max**.
* **TSR-002:** Validate input timestamps; reject/flag samples older than **T\_stale**.
* **TSR-003:** Per-sensor plausibility (range, ROC **dX/dt\_max**, stuck-at, timeout **T\_timeout**).

**Temperature (SM1/SM2/SM3)**

* **TSR-010:** Tunable **H, S** per room for cold; parameters in `app_cfg.yaml`.
* **TSR-011:** Decision ≤ **T\_decision\_max**; publish PF/F and debounce evidence.
* **TSR-012:** Maintain per-room **last decision/recovery** records.
* **TSR-020:** Forecasting baseline (EMA/AR) with window **W** and horizon **H\_pred**; **Shadow mode** default; **Active** behind flag when precision ≥ **C\_target** over replay.
* **TSR-110:** Hot-side thresholds (**T\_max**, **H\_hot**, **S\_hot**) per room; emergency cooling/ventilation command.

**AQ (SM4)**

* **TSR-120:** Integrate AQ sensors; plausibility checks; stale timeout **T\_timeout\_aq**.
* **TSR-121:** Control purifiers/ventilation within **T\_act\_aq**; log actions; L2/L3 notifications.
* **TSR-122:** Forecast AQ breach (EMA/AR or threshold trend) with **H\_pred\_aq**, **C\_min\_aq**.

**Fire/Gas/CO (SM5/SM6/SM7)**

* **TSR-130:** Smoke/heat sensor integration; on trigger → **L1**, siren/lights, evidence.
* **TSR-140:** Gas sensor integration; ventilation/valve control; **L1**.
* **TSR-150:** CO sensor integration; ventilation escalation; **L1**.

**Water Leak (SM8)**

* **TSR-160:** Leak sensors with debounce; evidence; **TSR-161:** Shutoff valve actuation if present.

**HVAC Health (SM9)**

* **TSR-170:** Flow temp ROC; heater/cooler failure heuristics; maintenance notification; evidence.

**Windows/Weather (SM10)**

* **TSR-180:** Weather API + window/door sensors; suppression to avoid alert storms; evidence of decision context.

**Recovery & Notification**

* **TSR-040:** Recovery actions idempotent; retries **N\_retry**; cooldown **T\_cooldown**.
* **TSR-041:** Notification levels L1–L4 with templated payloads; **T\_notify** ≤ per SG.
* **TSR-042:** On conflicts, prefer **most conservative** safe action.

**Evidence & Metrics**

* **TSR-050:** Evidence schema v1 (JSON): timestamp, room, rule\_id, decision, inputs (min/max/avg), thresholds, debounce/suppression, action, latency.
* **TSR-051:** `GET /evidence?limit=N`, `GET /evidence/{id}` (local).
* **TSR-052:** Export metrics: `decisions_total{rule,decision}`, `suppression_active`, `decision_latency_ms` p50/p95.

**Configuration & Flags**

* **TSR-060:** Safety params in `backend/app_cfg.yaml`; versioned; defaults preserve legacy behavior.
* **TSR-061:** Feature flags: `enable_TC_SM1_v2`, `enable_TC_SM2_shadow` (on), `enable_TC_SM2_active` (off), `enable_SM3_hot`, `enable_SM4_aq`, `enable_SM5_fire`, `enable_SM6_gas`, `enable_SM7_co`, `enable_SM8_leak`, `enable_SM9_hvac`, `enable_SM10_window_weather`.

**Performance & Independence**

* **TSR-070:** Decision latency p95 ≤ **T\_decision\_max**; memory ≤ **M\_max**; CPU ≤ **CPU\_max%**.
* **TSR-080:** Freedom from interference between safety and non-safety code paths.
* **TSR-081:** Log/evidence failures must not block decision loop.

**Safe State Handling**

* **TSR-090:** Define **SS-1..SS-5** entry/exit criteria; document and test.

---

## 5) Timing & FTTI Budgeting

Let **FTTI = T\_detection + T\_decision + T\_recovery + T\_effect**.
**Proposed budgets** (replace with HARA values):

| SG                       | FTTI       | Example split                                                   |
| ------------------------ | ---------- | --------------------------------------------------------------- |
| SG-001 (undercool)       | **10 min** | Detect 6 min / Decide 1 s / Recover 30 s / Effect 3.5 min       |
| SG-004 (overheat)        | **5 min**  | Detect 2 min / Decide 1 s / Recover 30 s / Effect 2.5 min       |
| SG-002 (predict)         | **10 min** | Detect trend 8 min / Decide 1 s / Recover 30 s / Effect 1.5 min |
| SG-003 (diag)            | **60 s**   | Detect 30 s / Decide 1 s / Recover 5 s / Effect 24 s            |
| SG-005 (AQ)              | **10 min** | Detect 5 min / Decide 1 s / Recover 30 s / Effect 4.5 min       |
| SG-006/7/8 (fire/gas/CO) | **10 s**   | Detect 3 s / Decide 0.5 s / Actuate 1.5 s / Effect 5 s          |
| SG-009 (leak)            | **60 s**   | Detect 30 s / Decide 1 s / Close valve 5 s / Effect 24 s        |
| SG-010 (HVAC)            | **30 min** | Detect 25 min / Decide 1 s / Notify 30 s / Effect 4.5 min       |
| SG-011 (window/weather)  | **120 s**  | Detect 30 s / Decide 1 s / Notify 5 s / Effect 84 s             |

---

## 6) Verification & Validation (V\&V)

* **Unit/Integration Tests:** Seeded fixtures for SM1/SM2/SM3, AQ, fire/gas/CO, leak, HVAC, window/weather; injected clock.
* **Coverage Targets:** +15% lines; +20% branches across mechanisms/managers.
* **Shadow Validation:** SM2 and AQ forecasting precision ≥ **C\_target** before activation.
* **Fault Injection:** Sensor timeout, stuck-at, out-of-range, comm loss; confirm safe state transitions and notifications.
* **Performance Tests:** p95 decision latency under nominal/peak loads.

---

## 7) Traceability & Work Products

* `traceability.md` linking **SG ↔ FSR ↔ TSR ↔ Test IDs ↔ Metrics**.
* `mapping.json` machine-readable map for CI.
* ADRs: timebase, evidence schema, forecasting baseline, feature-flag strategy.

---

## 8) Open Points (need HARA confirmation)

* Replace **ASIL** and **FTTI** with exact HARA-derived values.
* Confirm threshold values (**T\_min**, **T\_max**, **ΔT\_min**, **C\_min**, etc.).
* Confirm notification level routing per SG.
* Confirm evidence retention and pagination policy.

---

## 9) Appendices

### A) Glossary

**Prefault:** Early warning state prior to confirmed fault; may trigger suppression/hysteresis logic.
**Safe State:** A condition in which risk is reduced to an acceptable level by design (e.g., fallback heating + notifications).

### B) Parameter Table (proposed defaults — replace with HARA values)

| Name             | Description                        | Proposed                    |
| ---------------- | ---------------------------------- | --------------------------- |
| T\_min           | Minimum safe room temperature      | 16–18 °C                    |
| T\_max           | Maximum safe room temperature      | 28–30 °C                    |
| T\_crit          | Max duration below T\_min (SG-001) | 10 min                      |
| T\_crit\_hot     | Max duration above T\_max (SG-004) | 5 min                       |
| T\_det           | Cold-side detection window         | 120–360 s                   |
| H (cold)         | Hysteresis band                    | 0.5–1.5 °C                  |
| S (cold)         | Suppression window                 | 60–180 s                    |
| T\_det\_hot      | Hot-side detection window          | 60–180 s                    |
| H\_hot           | Hot hysteresis                     | 0.5–1.5 °C                  |
| S\_hot           | Hot suppression                    | 60–180 s                    |
| H\_pred          | Forecast horizon (cold)            | 5–15 min                    |
| C\_min           | Min forecast confidence            | 0.7–0.8                     |
| ΔT\_min          | Min forecast delta                 | 0.5–1.0 °C                  |
| H\_pred\_aq      | AQ forecast horizon                | 10–30 min                   |
| C\_min\_aq       | Min AQ forecast confidence         | 0.7–0.8                     |
| T\_timeout       | Sensor/comm timeout                | 30–60 s                     |
| dT/dt\_max       | ROC threshold (temp)               | 2–5 °C/min                  |
| Δt\_max          | Max timebase error                 | 20–100 ms                   |
| f\_sensor\_min   | Min sensor frequency               | 0.2–1 Hz                    |
| T\_stable        | Safe-state exit stabilization      | 5–15 min                    |
| T\_notify        | Notification deadline              | ≤ 10 s (L1), ≤ 30 s (L2/L3) |
| T\_decision\_max | Decision computation time          | ≤ 100 ms                    |
| C\_target        | Shadow precision KPI (forecast)    | ≥ 70%                       |
| T\_timeout\_aq   | AQ stale timeout                   | 60–120 s                    |
| T\_act\_aq       | AQ actuation deadline              | ≤ 30 s                      |
| N\_retry         | Recovery retries                   | 1–3                         |
| T\_cooldown      | Cooldown between retries           | 30–120 s                    |
