# Traceability Matrix — SYS v0.2 (SG ↔ FSR ↔ TSR ↔ Code ↔ Tests ↔ Metrics)

**Date:** 2025-09-05
**Owner:** Safety (SYS) / QA
**Status:** Draft v0.1
**Sources:** SYS v0.2, PRD v0.2 (SYS-aligned), Architecture Review v0.2

---

## 0) Overview & Conventions

* **Scope:** Maps Safety Goals (**SG-xxx**) to Functional Safety Requirements (**FSR-xxx**), Technical Safety Requirements (**TSR-xxx**), code elements, tests, metrics, evidence fields, feature flags, and config keys.
* **Rule IDs:** `RULE_SM1`, `RULE_SM2`, … `RULE_SM10` (and sub-ids when needed).
* **Mechanism IDs:** `SM1..SM10` as in SYS v0.2.
* **Evidence (schema v1):** `timestamp, room, rule_id, decision, inputs[min|max|avg], thresholds, debounce, suppression, action, latency, hazard_ref`.
* **Metrics:** counters `decisions_total{rule,decision}`, gauge `suppression_active`, timer `decision_latency_ms` (p50/p95).
* **Test IDs:** Use pattern `TS_<Mechanism>_<Behavior>_<Index>` (e.g., `TS_SM1_Hysteresis_NoFlap_001`).
* **Config keys:** Live in `backend/app_cfg.yaml`.
* **Flags:** Safety toggles are read-only in UI via `/flags`.

---

## 1) Master Matrix (compact)

| SG                      | Mechanism                  | FSRs                        | TSRs                                                | Primary Code (module.symbol)                                                                             | Example Tests (IDs)                                                                                 | Metrics (names)                                                               | Feature Flags                                  | Key Config                                                                       |
| ----------------------- | -------------------------- | --------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- |
| SG-001 (Undercool)      | **SM1** LowTempMonitoring  | FSR-002,004,005,006,008,009 | TSR-010,011,012,040,041,050–052,060–061,070–081,090 | `temperature_component.LowTempMonitor`, `fault_manager.FaultManager`, `recovery_manager.RecoveryManager` | TS\_SM1\_Hysteresis\_NoFlap\_001; TS\_SM1\_Escalate\_PFtoF\_002; TS\_SM1\_Recovery\_Idempotent\_003 | `decisions_total{rule=RULE_SM1}`, `suppression_active`, `decision_latency_ms` | `enable_TC_SM1_v2`                             | `thresholds.t_min`, `windows.t_det`, `hysteresis.h`, `suppression.s`             |
| SG-002 (Predict cold)   | **SM2** LowTempForecast    | FSR-003,006,008             | TSR-020,041,050–052,060–061,070–081                 | `low_temp_forecast.Forecast`, `fault_manager.FaultManager`                                               | TS\_SM2\_Shadow\_PrecisionKPI\_001; TS\_SM2\_NoActuationInShadow\_002                               | `decisions_total{rule=RULE_SM2}`, `decision_latency_ms`                       | `enable_TC_SM2_shadow`, `enable_TC_SM2_active` | `forecast.horizon`, `forecast.confidence_min`, `forecast.delta_min`              |
| SG-003 (Diagnostics)    | **SMx** System Diagnostics | FSR-007,006,008             | TSR-001–003,041,080–081,090                         | `diagnostics.SensorDiag`, `diagnostics.CommDiag`                                                         | TS\_DIAG\_StuckAt\_001; TS\_DIAG\_Timeout\_002; TS\_DIAG\_RangeROC\_003                             | `decisions_total{rule=RULE_DIAG}`                                             | n/a                                            | `timeouts.sensor`, `timeouts.comm`, `roc.max`                                    |
| SG-004 (Overheat)       | **SM3** HighTempMonitoring | FSR-011,004,005,006,008,009 | TSR-110–112,041,050–052,060–061,070–081,090         | `temperature_component.HighTempMonitor`, `recovery_manager.RecoveryManager`                              | TS\_SM3\_Hot\_Hysteresis\_NoFlap\_001; TS\_SM3\_F\_OVERTEMP\_Action\_002                            | `decisions_total{rule=RULE_SM3}`                                              | `enable_SM3_hot`                               | `thresholds.t_max`, `windows.t_det_hot`, `hysteresis.h_hot`, `suppression.s_hot` |
| SG-005 (Air Quality)    | **SM4** AQ Mon/Forecast    | FSR-020,021,006,008         | TSR-120–122,041,050–052,060–061,070–081             | `aq_monitor.AQMonitor`, `aq_forecast.AQForecast`                                                         | TS\_SM4\_AQ\_Breach\_001; TS\_SM4\_AQ\_Forecast\_Shadow\_002                                        | `decisions_total{rule=RULE_SM4}`                                              | `enable_SM4_aq`                                | `aq.thresholds`, `aq.timeout`, `aq.actuation_deadline`                           |
| SG-006 (Fire)           | **SM5** Fire/Smoke         | FSR-030,006,008             | TSR-130,041,050–052,060–061,070–081                 | `smoke_detector.SmokeDetector`                                                                           | TS\_SM5\_Smoke\_AlarmLatency\_001                                                                   | `decisions_total{rule=RULE_SM5}`                                              | `enable_SM5_fire`                              | `fire.sensor`, `notify.levels`                                                   |
| SG-007 (Gas)            | **SM6** Gas                | FSR-040,006,008             | TSR-140,041,050–052,060–061,070–081                 | `gas_detector.GasDetector`                                                                               | TS\_SM6\_Gas\_AlarmLatency\_001                                                                     | `decisions_total{rule=RULE_SM6}`                                              | `enable_SM6_gas`                               | `gas.sensor`, `ventilation.valve`                                                |
| SG-008 (CO)             | **SM7** CO                 | FSR-050,006,008             | TSR-150,041,050–052,060–061,070–081                 | `co_detector.CODetector`                                                                                 | TS\_SM7\_CO\_AlarmLatency\_001                                                                      | `decisions_total{rule=RULE_SM7}`                                              | `enable_SM7_co`                                | `co.sensor`                                                                      |
| SG-009 (Leak)           | **SM8** Water Leak         | FSR-060,006,008             | TSR-160–161,041,050–052,060–061,070–081             | `leak_detector.LeakDetector`, `actuators.ShutoffValve`                                                   | TS\_SM8\_Leak\_ValveClose\_001; TS\_SM8\_Debounce\_002                                              | `decisions_total{rule=RULE_SM8}`                                              | `enable_SM8_leak`                              | `leak.sensors`, `valve.present`, `valve.deadline`                                |
| SG-010 (HVAC)           | **SM9** HVAC Health        | FSR-070,006,008             | TSR-170,041,050–052,060–061,070–081                 | `hvac_health.HVACHealth`, `temperature_component.*`                                                      | TS\_SM9\_FlowROC\_Anomaly\_001                                                                      | `decisions_total{rule=RULE_SM9}`                                              | `enable_SM9_hvac`                              | `hvac.flow_thresholds`, `roc.max`                                                |
| SG-011 (Window/Weather) | **SM10** Window+Weather    | FSR-080,006,008             | TSR-180,041,050–052,060–061,070–081                 | `window_weather.Supervisor`                                                                              | TS\_SM10\_RainOpenWindow\_Prompt\_001                                                               | `decisions_total{rule=RULE_SM10}`                                             | `enable_SM10_window_weather`                   | `weather.api`, `window.sensors`, `suppression.weather`                           |

> **Note:** Code symbols reflect intended modules; adjust to exact paths/class/function names during implementation.

---

## 2) Detailed Mappings (per SG)

### SG-001 — Prevent Undercooling (ASIL B, FTTI 10 min)

* **Mechanism:** SM1 LowTemperatureMonitoring
* **FSR:** 002, 004, 005, 006, 008, 009
* **TSR:** 010, 011, 012, 040, 041, 050–052, 060–061, 070–081, 090
* **Code:** `temperature_component.LowTempMonitor`, `fault_manager.FaultManager`, `recovery_manager.RecoveryManager`
* **Tests:** `TS_SM1_Hysteresis_NoFlap_001`, `TS_SM1_Escalate_PFtoF_002`, `TS_SM1_Recovery_Idempotent_003`
* **Metrics:** `decisions_total{rule=RULE_SM1}`, `suppression_active`, `decision_latency_ms{rule=RULE_SM1}`
* **Flags:** `enable_TC_SM1_v2`
* **Config:** `thresholds.t_min`, `windows.t_det`, `hysteresis.h`, `suppression.s`
* **Evidence:** `rule_id=RULE_SM1`, `inputs (T)`, `thresholds (T_min)`, `debounce`, `suppression`, `outcome`, `latency`, `hazard_ref=HZ-UNDERTEMP-01`

### SG-002 — Predict Undercooling (QM/A, FTTI 10 min)

* **Mechanism:** SM2 Forecast
* **FSR:** 003, 006, 008
* **TSR:** 020, 041, 050–052, 060–061, 070–081
* **Code:** `low_temp_forecast.Forecast`
* **Tests:** `TS_SM2_Shadow_PrecisionKPI_001`, `TS_SM2_NoActuationInShadow_002`
* **Metrics:** `decisions_total{rule=RULE_SM2}`, `decision_latency_ms{rule=RULE_SM2}`
* **Flags:** `enable_TC_SM2_shadow`, `enable_TC_SM2_active`
* **Config:** `forecast.horizon`, `forecast.confidence_min`, `forecast.delta_min`
* **Evidence:** `rule_id=RULE_SM2`, `inputs (T series)`, `thresholds`, `outcome=PF_FORECAST`, `latency`, `hazard_ref=HZ-UNDERTEMP-02`

### SG-003 — Diagnostics (ASIL B, FTTI 60 s)

* **Mechanism:** SMx Diagnostics
* **FSR:** 007, 006, 008
* **TSR:** 001–003, 041, 080–081, 090
* **Code:** `diagnostics.*`
* **Tests:** `TS_DIAG_StuckAt_001`, `TS_DIAG_Timeout_002`, `TS_DIAG_RangeROC_003`
* **Metrics:** `decisions_total{rule=RULE_DIAG}`
* **Config:** `timeouts.*`, `roc.max`
* **Evidence:** fault type, timestamps, thresholds, outcome, latency, `hazard_ref=HZ-SYSTEM-FAIL-01`

### SG-004 — Prevent Overheating (ASIL B, FTTI 5 min)

* **Mechanism:** SM3 HighTempMonitoring
* **FSR:** 011, 004, 005, 006, 008, 009
* **TSR:** 110–112, 041, 050–052, 060–061, 070–081, 090
* **Code:** `temperature_component.HighTempMonitor`
* **Tests:** `TS_SM3_Hot_Hysteresis_NoFlap_001`, `TS_SM3_F_OVERTEMP_Action_002`
* **Metrics:** `decisions_total{rule=RULE_SM3}`
* **Flags:** `enable_SM3_hot`
* **Config:** `thresholds.t_max`, `windows.t_det_hot`, `hysteresis.h_hot`, `suppression.s_hot`
* **Evidence:** temp series, `T_max`, hysteresis, suppression, outcome

### SG-005 — Air Quality (ASIL A, FTTI 10 min)

* **Mechanism:** SM4 AQ
* **FSR:** 020, 021, 006, 008
* **TSR:** 120–122, 041, 050–052, 060–061, 070–081
* **Code:** `aq_monitor.AQMonitor`, `aq_forecast.AQForecast`
* **Tests:** `TS_SM4_AQ_Breach_001`, `TS_SM4_AQ_Forecast_Shadow_002`
* **Metrics:** `decisions_total{rule=RULE_SM4}`
* **Flags:** `enable_SM4_aq`
* **Config:** `aq.thresholds`, `aq.timeout`, `aq.actuation_deadline`
* **Evidence:** AQ inputs, thresholds, outcome, action, latency, hazard ref

### SG-006 — Fire/Smoke (ASIL C, FTTI 10 s)

* **Mechanism:** SM5 Fire
* **FSR:** 030, 006, 008
* **TSR:** 130, 041, 050–052, 060–061, 070–081
* **Code:** `smoke_detector.SmokeDetector`
* **Tests:** `TS_SM5_Smoke_AlarmLatency_001`
* **Metrics:** `decisions_total{rule=RULE_SM5}`
* **Flags:** `enable_SM5_fire`
* **Config:** `fire.sensor`, `notify.levels`
* **Evidence:** trigger timestamp, alarm emission time, payload

### SG-007 — Gas (ASIL C, FTTI 10 s)

* **Mechanism:** SM6 Gas
* **FSR:** 040, 006, 008
* **TSR:** 140, 041, 050–052, 060–061, 070–081
* **Code:** `gas_detector.GasDetector`
* **Tests:** `TS_SM6_Gas_AlarmLatency_001`
* **Metrics:** `decisions_total{rule=RULE_SM6}`
* **Flags:** `enable_SM6_gas`
* **Config:** `gas.sensor`, `ventilation.valve`
* **Evidence:** gas ppm, threshold, valve/vent action

### SG-008 — CO (ASIL C, FTTI 10 s)

* **Mechanism:** SM7 CO
* **FSR:** 050, 006, 008
* **TSR:** 150, 041, 050–052, 060–061, 070–081
* **Code:** `co_detector.CODetector`
* **Tests:** `TS_SM7_CO_AlarmLatency_001`
* **Metrics:** `decisions_total{rule=RULE_SM7}`
* **Flags:** `enable_SM7_co`
* **Config:** `co.sensor`
* **Evidence:** CO ppm, thresholds, ventilation action

### SG-009 — Water Leak (QM/A, FTTI 60 s)

* **Mechanism:** SM8 Leak
* **FSR:** 060, 006, 008
* **TSR:** 160–161, 041, 050–052, 060–061, 070–081
* **Code:** `leak_detector.LeakDetector`, `actuators.ShutoffValve`
* **Tests:** `TS_SM8_Leak_ValveClose_001`, `TS_SM8_Debounce_002`
* **Metrics:** `decisions_total{rule=RULE_SM8}`
* **Flags:** `enable_SM8_leak`
* **Config:** `leak.sensors`, `valve.present`, `valve.deadline`
* **Evidence:** leak trigger, debounce, valve action result, deadlines

### SG-010 — HVAC Health (QM/A, FTTI 30 min)

* **Mechanism:** SM9 HVAC
* **FSR:** 070, 006, 008
* **TSR:** 170, 041, 050–052, 060–061, 070–081
* **Code:** `hvac_health.HVACHealth`
* **Tests:** `TS_SM9_FlowROC_Anomaly_001`
* **Metrics:** `decisions_total{rule=RULE_SM9}`
* **Flags:** `enable_SM9_hvac`
* **Config:** `hvac.flow_thresholds`, `roc.max`
* **Evidence:** flow temps, ROC calc, anomaly classification

### SG-011 — Window/Weather (QM, FTTI 120 s)

* **Mechanism:** SM10 Window/Weather
* **FSR:** 080, 006, 008
* **TSR:** 180, 041, 050–052, 060–061, 070–081
* **Code:** `window_weather.Supervisor`
* **Tests:** `TS_SM10_RainOpenWindow_Prompt_001`
* **Metrics:** `decisions_total{rule=RULE_SM10}`
* **Flags:** `enable_SM10_window_weather`
* **Config:** `weather.api`, `window.sensors`, `suppression.weather`
* **Evidence:** weather context, window state, prompt issuance

---

## 3) JSON Mapping Seed (for `mapping.json` in CI)

```json
{
  "version": "1.0",
  "items": [
    {
      "sg": "SG-001",
      "asil": "B",
      "ftti": "10m",
      "mechanism": "SM1",
      "rule_id": "RULE_SM1",
      "fsr": ["FSR-002", "FSR-004", "FSR-005", "FSR-006", "FSR-008", "FSR-009"],
      "tsr": ["TSR-010", "TSR-011", "TSR-012", "TSR-040", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081", "TSR-090"],
      "code": ["temperature_component.LowTempMonitor", "fault_manager.FaultManager", "recovery_manager.RecoveryManager"],
      "tests": ["TS_SM1_Hysteresis_NoFlap_001", "TS_SM1_Escalate_PFtoF_002", "TS_SM1_Recovery_Idempotent_003"],
      "metrics": ["decisions_total{rule=RULE_SM1}", "suppression_active", "decision_latency_ms"],
      "flags": ["enable_TC_SM1_v2"],
      "config": ["thresholds.t_min", "windows.t_det", "hysteresis.h", "suppression.s"]
    },
    {
      "sg": "SG-002",
      "asil": "A",
      "ftti": "10m",
      "mechanism": "SM2",
      "rule_id": "RULE_SM2",
      "fsr": ["FSR-003", "FSR-006", "FSR-008"],
      "tsr": ["TSR-020", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["low_temp_forecast.Forecast", "fault_manager.FaultManager"],
      "tests": ["TS_SM2_Shadow_PrecisionKPI_001", "TS_SM2_NoActuationInShadow_002"],
      "metrics": ["decisions_total{rule=RULE_SM2}", "decision_latency_ms"],
      "flags": ["enable_TC_SM2_shadow", "enable_TC_SM2_active"],
      "config": ["forecast.horizon", "forecast.confidence_min", "forecast.delta_min"]
    },
    {
      "sg": "SG-003",
      "asil": "B",
      "ftti": "60s",
      "mechanism": "SMx",
      "rule_id": "RULE_DIAG",
      "fsr": ["FSR-007", "FSR-006", "FSR-008"],
      "tsr": ["TSR-001", "TSR-002", "TSR-003", "TSR-041", "TSR-080", "TSR-081", "TSR-090"],
      "code": ["diagnostics.SensorDiag", "diagnostics.CommDiag"],
      "tests": ["TS_DIAG_StuckAt_001", "TS_DIAG_Timeout_002", "TS_DIAG_RangeROC_003"],
      "metrics": ["decisions_total{rule=RULE_DIAG}", "decision_latency_ms"],
      "flags": [],
      "config": ["timeouts.sensor", "timeouts.comm", "roc.max"]
    },
    {
      "sg": "SG-004",
      "asil": "B",
      "ftti": "5m",
      "mechanism": "SM3",
      "rule_id": "RULE_SM3",
      "fsr": ["FSR-011", "FSR-004", "FSR-005", "FSR-006", "FSR-008", "FSR-009"],
      "tsr": ["TSR-110", "TSR-111", "TSR-112", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081", "TSR-090"],
      "code": ["temperature_component.HighTempMonitor", "recovery_manager.RecoveryManager"],
      "tests": ["TS_SM3_Hot_Hysteresis_NoFlap_001", "TS_SM3_F_OVERTEMP_Action_002"],
      "metrics": ["decisions_total{rule=RULE_SM3}", "decision_latency_ms"],
      "flags": ["enable_SM3_hot"],
      "config": ["thresholds.t_max", "windows.t_det_hot", "hysteresis.h_hot", "suppression.s_hot"]
    },
    {
      "sg": "SG-005",
      "asil": "A",
      "ftti": "10m",
      "mechanism": "SM4",
      "rule_id": "RULE_SM4",
      "fsr": ["FSR-020", "FSR-021", "FSR-006", "FSR-008"],
      "tsr": ["TSR-120", "TSR-121", "TSR-122", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["aq_monitor.AQMonitor", "aq_forecast.AQForecast"],
      "tests": ["TS_SM4_AQ_Breach_001", "TS_SM4_AQ_Forecast_Shadow_002"],
      "metrics": ["decisions_total{rule=RULE_SM4}", "decision_latency_ms"],
      "flags": ["enable_SM4_aq"],
      "config": ["aq.thresholds", "aq.timeout", "aq.actuation_deadline"]
    },
    {
      "sg": "SG-006",
      "asil": "C",
      "ftti": "10s",
      "mechanism": "SM5",
      "rule_id": "RULE_SM5",
      "fsr": ["FSR-030", "FSR-006", "FSR-008"],
      "tsr": ["TSR-130", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["smoke_detector.SmokeDetector"],
      "tests": ["TS_SM5_Smoke_AlarmLatency_001"],
      "metrics": ["decisions_total{rule=RULE_SM5}", "decision_latency_ms"],
      "flags": ["enable_SM5_fire"],
      "config": ["fire.sensor", "notify.levels"]
    },
    {
      "sg": "SG-007",
      "asil": "C",
      "ftti": "10s",
      "mechanism": "SM6",
      "rule_id": "RULE_SM6",
      "fsr": ["FSR-040", "FSR-006", "FSR-008"],
      "tsr": ["TSR-140", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["gas_detector.GasDetector"],
      "tests": ["TS_SM6_Gas_AlarmLatency_001"],
      "metrics": ["decisions_total{rule=RULE_SM6}", "decision_latency_ms"],
      "flags": ["enable_SM6_gas"],
      "config": ["gas.sensor", "ventilation.valve"]
    },
    {
      "sg": "SG-008",
      "asil": "C",
      "ftti": "10s",
      "mechanism": "SM7",
      "rule_id": "RULE_SM7",
      "fsr": ["FSR-050", "FSR-006", "FSR-008"],
      "tsr": ["TSR-150", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["co_detector.CODetector"],
      "tests": ["TS_SM7_CO_AlarmLatency_001"],
      "metrics": ["decisions_total{rule=RULE_SM7}", "decision_latency_ms"],
      "flags": ["enable_SM7_co"],
      "config": ["co.sensor"]
    },
    {
      "sg": "SG-009",
      "asil": "A",
      "ftti": "60s",
      "mechanism": "SM8",
      "rule_id": "RULE_SM8",
      "fsr": ["FSR-060", "FSR-006", "FSR-008"],
      "tsr": ["TSR-160", "TSR-161", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["leak_detector.LeakDetector", "actuators.ShutoffValve"],
      "tests": ["TS_SM8_Leak_ValveClose_001", "TS_SM8_Debounce_002"],
      "metrics": ["decisions_total{rule=RULE_SM8}", "decision_latency_ms"],
      "flags": ["enable_SM8_leak"],
      "config": ["leak.sensors", "valve.present", "valve.deadline"]
    },
    {
      "sg": "SG-010",
      "asil": "A",
      "ftti": "30m",
      "mechanism": "SM9",
      "rule_id": "RULE_SM9",
      "fsr": ["FSR-070", "FSR-006", "FSR-008"],
      "tsr": ["TSR-170", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["hvac_health.HVACHealth"],
      "tests": ["TS_SM9_FlowROC_Anomaly_001"],
      "metrics": ["decisions_total{rule=RULE_SM9}", "decision_latency_ms"],
      "flags": ["enable_SM9_hvac"],
      "config": ["hvac.flow_thresholds", "roc.max"]
    },
    {
      "sg": "SG-011",
      "asil": "QM",
      "ftti": "120s",
      "mechanism": "SM10",
      "rule_id": "RULE_SM10",
      "fsr": ["FSR-080", "FSR-006", "FSR-008"],
      "tsr": ["TSR-180", "TSR-041", "TSR-050", "TSR-051", "TSR-052", "TSR-060", "TSR-061", "TSR-070", "TSR-080", "TSR-081"],
      "code": ["window_weather.Supervisor"],
      "tests": ["TS_SM10_RainOpenWindow_Prompt_001"],
      "metrics": ["decisions_total{rule=RULE_SM10}", "decision_latency_ms"],
      "flags": ["enable_SM10_window_weather"],
      "config": ["weather.api", "window.sensors", "suppression.weather"]
    }
  ]
}

```

> Copy the JSON block to `mapping.json` and complete SG-003..011 using the **Master Matrix** above.

---

## 4) Upkeep & CI Publishing

* **Ownership:** Safety (SYS) drives SG/FSR/TSR; Dev owns code/test links; QA owns test IDs; SRE/Dev own metrics names.
* **Checks:** CI job validates that every SG maps to ≥1 FSR/TSR, ≥1 code symbol, ≥1 test, and ≥1 metric.
* **Drift Control:** Failing check blocks merge if any mapping becomes stale.
