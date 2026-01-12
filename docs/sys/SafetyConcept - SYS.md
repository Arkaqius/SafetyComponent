# Lean SYS + TSC — Safety Architecture & Requirements (v1.0.0)

**Item:** Home Automation Safety Monitoring & Recovery (multi-hazard)

**Date:** 2025-09-18
**Owner:** System/Safety (SYS)
**Status:** Working Draft → for SYS review
**Scope:** Blend **ASPICE SYS.x** with **ISO 26262-3/4/6** work products; align with provided **HARA** and **SYS v0.2** inputs.

---

## 1 Purpose and Audience

**Why this document exists (HARA-linked):**

- Provide a **single, lean specification** that turns the existing **HARA** (hazards, S/E/C, initial risk levels) into actionable **Safety Goals, System Requirements, Technical Safety Requirements, Safe States, and FTTI budgets**.
- Maintain **end‑to‑end traceability** from _hazard → safety goal → requirement → verification_, while minimizing work products for a **hobby/semiprofessional, open‑source** effort (no formal certification claim).
- Serve as the **source of truth** for the concept phase and subsequent implementation/validation; any YAML/CSV/config artifacts are generated from this document.

**Intended readers:**

- **Developers** — implement safety logic and interfaces (HA/AppDaemon or other runtimes later).
- **Testers** — design and execute unit, integration, HIL, and household drills per the V\&V guidance.
- **Contributors** — propose changes to thresholds/FTTI, add sensors/actuators, improve documentation.
- **Maintainers** — govern releases, parameter changes, evidence retention, and issue triage.
- **Safety reviewer (you)** — resolve open points (ASIL/FTTI confirmation, safe‑state policies, decomposition choices).

**Scope of this document:**

- Covers the **safety‑critical logic** of the _Home Automation Safety App_ (currently running atop **Home Assistant + AppDaemon**), specifically: detection, decision, and **actuation** for hazards identified in HARA (Fire/Smoke, Gas, CO, Water Leak, **Undercooling/Overheating**, Air Quality, System/Comms failure, HVAC degradation, Unauthorized Access/Privacy, Rain/Ingress).
- Defines **safety goals, SYS‑level requirements (blended with FSR), TSRs, safe states, timing (FTTI), parameters, and V\&V** at the **system level**. Software architecture details of a specific implementation are **intentionally out of scope for now** and will be adapted later.

**Out of scope (for clarity):**

- General home‑automation conveniences (scenes, presence lighting, media, non‑safety automations).
- Brand‑specific hardware design/certification and regulatory approvals (this is a best‑effort, non‑certified project).
- Detailed software component design of your current app (to be integrated once concept is finalized).

## 2 System Boundaries

This section defines the **fence** of the Safety System: what is _inside_ (owned/controlled and specified here) and what is _outside_ (relied upon, with contracts/assumptions).

```
[External Env & Services]
   ↑ inputs / ↓ outputs via defined interfaces
[  Safety System (this doc)  ]  ← internal logic, configs, evidence, timing
```

### 2.1 Internal Elements

The following **interfaces and processing** are **inside** the system boundary and are specified, tested, and maintained here.

**A) Input Interfaces — Hardware Sensors**

- Window contact sensors
- Door contact sensors
- Smoke detectors
- Gas detectors
- Carbon monoxide (CO) detectors
- Room climate sensors (temperature, humidity) — per room
- Indoor air quality sensors (e.g., CO₂/PM/VOC)
- Boiler signals and measurements

**B) Input Interfaces — Cloud/Data Feeds (logical interfaces inside the boundary)**
_Note: the data **providers** are external; the **interfaces** and how we use them are internal._

- Weather data: current (temperature, pressure, wind speed, clouds) and forecast (same set)
- Weather hazard alerts: storm, blizzard, wind, rain, heatwave, tornado
- Occupancy status (cloud or presence service)
- Outdoor air pollution
- System health & update info (platform feeds)
- Ethernet port status; link status (router, WAN)
- Network performance: system latency, packet loss

**C) Output Interfaces — Hardware Actuators**

- Smart locks
- Siren
- Information light
- Alert/emergency light

**D) Output Interfaces — Cloud/UI Actuators (logical interfaces inside the boundary)**

- Phone application pop‑ups / push notifications
- Main safety card in UI (status/acknowledge)
- User action scheduler / prompts

**E) Processing**

- Home automation instance running the Safety App (decision logic, thresholds/FTTI, evidence logging, notifications).

**Responsibilities (internal):**

- Validate freshness/plausibility of all inputs; meet FTTI on life‑safety paths; issue idempotent actuation with read‑back verification; log evidence; degrade safely on external failures (e.g., network loss).

### 2.2 External Elements

Elements **outside** the boundary that we rely on and for which we define assumptions/contracts:

- **Physical environment** of the home (weather, building layout, utilities) being sensed/acted upon.
- **Users** interacting physically (e.g., evacuation, manual overrides) or via app/UI.
- **Internet and third‑party services** supplying data (e.g., weather forecasts/alerts, presence/occupancy, outdoor AQ, update feeds) and delivering notifications (push/SMS).
- **Home Assistant core, AppDaemon runtime, OS/host hardware**, device firmware, and vendor integrations (Zigbee/Z‑Wave/etc.).

**Assumptions (external):**

- Sensors/actuators meet their vendor specs and expose timely state to the system.
- Network connectivity is _usually_ available; loss triggers local‑only fallbacks.
- Weather/air‑quality feeds and alerting services are reasonably accurate within their stated SLAs.
- Users maintain devices (battery/power) and respond to L1/L2 notifications per household policy.

## 3 System Modes

> **Principle:** Modes describe how the **whole system operates**, not whether a fault/alert is active. Life‑safety events (fire/gas/CO) **override** mode policies where noted.

### 3.1 Mode Set (finalized)

- **M1: Startup** — Boot, load config, run self‑checks. No proactive control until ready.
- **M2: Normal** — Default operating mode.
- **M3: Sleep (Quiet Hours)** — Occupied/quiet context. Reduced non‑critical noise/notifications; stricter privacy. _Life‑safety siren still allowed._
- **M4: Local‑Only (WAN Lost)** — Internet/WAN unavailable; keep local sensing/actuation and queue outbound notifications.
- **M5: Maintenance/Debug** — Human‑initiated. Suppress non‑life‑safety actuations; allow sensor tests/calibration; enable extra logging/diagnostics.
- **M6: Shutdown** — Controlled stop; persist evidence; leave actuators in safe posture.

> _Not a mode:_ “Alarm latched” is an overlay state that can exist in any mode for life‑safety hazards.

### 3.2 Mode Policies (what each mode controls)

| Mode                     | Actuation Policy                                                                                      | Notifications                                  | Privacy                                   | Config Changes                        | Notes                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| **M1 Startup**           | No proactive control until self‑checks pass; read‑only verification                                   | L3 only if self‑check fails                    | Default                                   | Block safety‑critical threshold edits | Transitions to M2 when ready                                    |
| **M2 Normal**            | All safe actions allowed within FTTI                                                                  | L1/L2/L3 as configured                         | Standard                                  | Allowed with review                   | Default runtime                                                 |
| **M3 Sleep**             | Suppress **non‑life‑safety** noisy actions (e.g., non‑critical sirens); **life‑safety siren allowed** | L1 immediate; batch/quiet L2/L3 where possible | Auto‑mask cameras/mics unless life‑safety | Allowed (with prompt/warning)         | Enter by schedule/manual only (occupancy does not define modes) |
| **M4 Local‑Only**        | Keep **local** actuations (relays/locks/sirens/valves); disable cloud‑dependent actions               | Queue outbound; retry on recovery              | Standard                                  | Frozen (except emergency toggles)     | Enters when **WAN link lost**; exit on recovery                 |
| **M5 Maintenance/Debug** | Permit test commands but **suppress non‑life‑safety** automations; life‑safety still armed            | L3/L2 informational; L1 only for true hazards  | Standard                                  | Allowed; log every change             | Human‑entered; manual exit                                      |
| **M6 Shutdown**          | Place system in declared safe posture, then stop                                                      | Final status only                              | Standard                                  | Blocked                               | Manual action                                                   |

### 3.3 Transitions (high‑level)

- **M1 → M2** once self‑checks pass and config loads successfully.
- **M2 ↔ M3** by schedule or manual toggle. _(Occupancy does not control modes.)_
- **Any → M4** when WAN link is reported **down**; **M4 → previous mode** on WAN recovery.
- **Any ↔ M5** by explicit user action. Non‑life‑safety actuations remain suppressed while in M5.
- **Any → M6** by explicit user action (graceful shutdown).

### 3.4 Invariants (apply in all modes)

- Life‑safety hazards (Fire/Gas/CO) may **actuate siren and emergency lights** regardless of mode.
- Evidence logging remains active; failures to log **must not** block safety decisions.
- Read‑back verification follows each actuation; on mismatch → retry → escalate per requirement.

## 4 Notifications

This chapter defines **notification levels and vectors** used by the Safety System. Levels carry increasing urgency and determine the **channels**, **deadlines**, and **UI behavior**. Delivery adheres to system modes (see §3): L1 always overrides; L2/L3 may be quieted in _Sleep_; cloud paths are queued in _Local‑Only_.

### 4.1 Levels & Vectors

| Level       | Description                                     | Notification Vectors                                                                                                                                          |
| ----------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Level 1** | Highest urgency (life‑safety, immediate action) | **Home Assistant phone notification** with high priority, **sound alarm**, **information/alert light set to yellow**, and **dashboard card marked as HAZARD** |
| **Level 2** | High urgency (prompt action)                    | **Home Assistant phone notification** with high priority, **light notification as yellow**, and **dashboard card marked as HAZARD**                           |
| **Level 3** | Medium urgency (attention)                      | **Home Assistant phone notification** and **dashboard card marked as WARNING**                                                                                |
| **Level 4** | Low urgency (informational)                     | **Dashboard card** update only                                                                                                                                |

> _Vectors are logical; specific entities/services are bound in configuration. “Sound alarm” may be a phone alert tone and/or local siren if configured for the event._

### 4.2 Deadlines & Retries

- **Delivery deadlines:** Level 1 ≤ **10 s**; Level 2/3 ≤ **30 s** from fault confirmation; Level 4 best‑effort.
- **Retries:** If delivery confirmation is unavailable, attempt **N_retry** with **T_cooldown** between attempts (configurable). In _Local‑Only_, queue cloud/mobile and prefer local lights/siren.
- **Repeat policy (optional):** For persistent L1 events (e.g., CO at night), repeat phone alerts every **T_repeat ≤ 60 s** until acknowledged.

### 4.3 Mode‑Aware Behavior

- **Sleep:** L1 plays sound alarm + lights; L2/L3 use quiet profiles where possible (noisy actions suppressed).
- **Local‑Only:** WAN lost → deliver local lights/siren immediately; queue phone/UI pushes and flush on recovery.
- **Maintenance/Debug:** L1 still delivered; L2/L3 may be tagged as test if event is user‑initiated.

### 4.4 UI/UX Rules

- Dashboard “Main Safety Card” shows **current level badge** (HAZARD/WARNING/INFO) and supports **acknowledge** for L1–L3. Acknowledgement does **not** clear hazards; it silences repeats.
- Lights used for signaling should restore to previous state when the event clears.

### 4.5 Configuration Hooks (safety.yaml)

```yaml
notify_deadlines_s:
  L1: 10
  L2: 30
  L3: 30
  L4: 0 # best-effort
notifications:
  l1_profile: high_priority_with_sound
  l2_profile: high_priority
  l3_profile: normal
  dashboard_card: main_safety
  light_entity_info: light.info
  light_entity_alert: light.alert
  repeat_s_l1: 60
  retries:
    n_retry: 2
    cooldown_s: 45
  dual_path:
    enabled: true # enable WAN-loss fallback logic
    local_vectors: # what to use when WAN is down
      - light.info
      - light.alert
      - switch.siren
    cellular:
      enabled: false # set true if a local LTE/SMS path is available
      gateway_service: notify.sms_gateway # HA notify service for SMS
      max_retries: 3
      cooldown_s: 60
```

_Binding to actual Home Assistant services/entities is implementation‑specific and will be defined when integrating with your current app._

### 4.6 WAN‑Loss Delivery Options (recommendations)

When **WAN is down** (see §3, M4 Local‑Only), prefer delivery vectors that do **not** require the internet:

**A) Local vectors (no WAN):**

- **Siren / alert light / info light** — immediate, in‑home signaling.
- **On‑prem displays** (tablets, panels) — offline dashboards if available.

**B) Cellular/SMS fallback (optional):**

- Attach a **USB LTE modem** or gateway and expose an **HA `notify.sms_gateway`** service for L1 messages.
- Use **SMS only for L1** and limit repeats to avoid cost/abuse.

**C) Cellular router failover (optional):**

- If using a **4G/LTE router with failover**, WAN loss may be brief; keep queue + fast retry.

**Policy:**

- On entering **M4 Local‑Only**, immediately execute local vectors; attempt **cellular/SMS** if configured. Queue regular mobile pushes and flush on WAN recovery.
- Never block safety decisions on notification success.

**Resulting requirement stubs (for later §SYS‑SR):**

- _SYS‑SR‑N1:_ On WAN loss, the system **shall** deliver L1 locally (siren/light) and, if configured, via **cellular/SMS** within **T_notify ≤ 10 s**; queued IP notifications **shall** be sent on recovery.
- _SYS‑SR‑N2:_ Cellular/SMS fallback **shall** be rate‑limited and logged with correlation IDs; failures **shall** trigger local repeats only.

## 5 Item Definition (lean)

**Item:** Safety Monitoring & Recovery for temperature‑controlled rooms (multi‑hazard).

**Primary Purpose:** Detect, forecast, and mitigate environmental hazards (undercooling/overheating, indoor air quality, fire/gas/CO, water leaks) and system/comms failures to maintain safe operation and inform occupants.

**Operating Modes:** per §3 — Startup (M1), Normal (M2), Sleep/Quiet (M3), Local‑Only/WAN‑Lost (M4), Maintenance/Debug (M5), Shutdown (M6).

**Environmental Conditions:** Ambient **−20…+50 °C**; supply voltage per platform; timebase accuracy per host.

**System Boundaries:** as defined in §2 — Inputs (sensors & cloud feeds) → Safety logic → Actuation/Notifications → Evidence/UI. Fault manager behavior is part of the internal processing.

**Assumptions of Use (AoU):**

- **A1.** Sensors are calibrated and provide updates ≥ **f_sensor_min** Hz; communication error rate ≤ **p_comm_max**.
- **A2.** System timebase accuracy ≤ **Δt_max** ms; persistent storage is available for evidence.
- **A3.** Operator response to **L2/L3** notifications within **T_op_resp** minutes (household policy).
- **A4.** Actuation available within **T_act** seconds to effect temperature/AQ changes or shutoff valves.
- **A5.** Occupancy is **an input to some safety goals** but **does not control system modes** (see §3).

---

## 6 Safety Goals (provisional ASIL & FTTI)

> Derived from HARA; ASIL/FTTI values are provisional and will be confirmed during HARA review. Safe states use shorthand (SS‑1…SS‑5, SS‑Alarm). Occupancy is an **input** to some goals but **does not drive modes** (see §3).

| ID         | Safety Goal                                                                                                              | Hazard(s) Ref                          | **ASIL**                    | **FTTI**          | Safe State                                             |
| ---------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- | --------------------------- | ----------------- | ------------------------------------------------------ |
| **SG‑001** | Prevent sustained **undercooling** (< **T_min**) for longer than **T_crit** in occupied rooms.                           | HZ‑UNDERTEMP‑01                        | **ASIL B**                  | **10 min**        | **SS‑1:** Fallback heating + L3                        |
| **SG‑002** | Provide timely **prediction** of approaching undercooling to enable preventive action.                                   | HZ‑UNDERTEMP‑02                        | **QM/ASIL A**               | **10 min**        | **SS‑1**                                               |
| **SG‑003** | Detect **sensor/communication faults** that could mask hazards; transition to safe state.                                | HZ‑SYSTEM‑FAIL‑01                      | **ASIL B**                  | **60 s**          | **SS‑2:** Isolate faulty channel + L3                  |
| **SG‑004** | Prevent sustained **overheating** (> **T_max**) for longer than **T_crit_hot** in occupied rooms.                        | HZ‑OVERTEMP‑01                         | **ASIL B**                  | **5 min**         | **SS‑1:** Emergency cooling/ventilation + L2/L3        |
| **SG‑005** | Maintain acceptable **indoor air quality**; detect/forecast breach and mitigate.                                         | HZ‑AQ‑01                               | **ASIL A**                  | **10 min**        | **SS‑1:** Ventilate/purify + L2                        |
| **SG‑006** | Detect **smoke/fire** promptly; alert occupants; enter alarm safe state.                                                 | HZ‑FIRE‑01                             | **ASIL C**                  | **10 s**          | **SS‑Alarm:** Siren/lighting + L1                      |
| **SG‑007** | Detect **flammable gas** accumulation; alert and ventilate safely.                                                       | HZ‑GAS‑01                              | **ASIL C**                  | **10 s**          | **SS‑Alarm:** Ventilate + L1                           |
| **SG‑008** | Detect **CO** accumulation; alert and ventilate; escalate alarms.                                                        | HZ‑CO‑01                               | **ASIL C**                  | **10 s**          | **SS‑Alarm:** Ventilate + L1                           |
| **SG‑009** | Detect **water leak/flood**; alert and shut off supply if available.                                                     | HZ‑WATER‑01                            | **QM/ASIL A**               | **60 s**          | **SS‑3:** Close valve + L2                             |
| **SG‑010** | Detect **HVAC failures** affecting temperature control; prompt maintenance before exposure.                              | HZ‑HVAC‑01                             | **QM/ASIL A**               | **30 min**        | **SS‑4:** Degraded mode + L3                           |
| **SG‑011** | Prevent **weather ingress** via open windows/doors during rain/storm.                                                    | HZ‑WEATHER‑01                          | **QM**                      | **120 s**         | **SS‑5:** Prompt secure closure + L2                   |
| **SG‑012** | Mitigate **loss of heating/cooling** to maintain safe temperatures; alert and apply failover/backup strategies.          | HZ‑HVAC‑LOSS‑01                        | **QM/ASIL A**               | **30 min**        | **SS‑4:** Degraded mode + L3                           |
| **SG‑013** | Reduce **electrical shock** risk via RCD self‑test/reminders and wet‑zone interlocks.                                    | HZ‑ELECT‑01                            | **ASIL A**                  | **24 h**          | **SS‑4:** Degraded mode + L2/L3                        |
| **SG‑014** | Prevent **privacy invasion** by enforcing AV device quiet hours/masking and alerting on unexpected access.               | HZ‑PRIV‑01                             | **QM**                      | **60 s**          | **SS‑5:** Mask/disable AV + L2                         |
| **SG‑015** | Deter and respond to **unauthorized access** (unexpected movement/entry) when home declared unoccupied or during Sleep.  | HZ‑UNAUTH‑01                           | **QM/ASIL A**               | **30 s**          | **SS‑5:** Secure posture (lock/close) + L1/L2          |
| **SG‑016** | Maintain **cybersecurity posture** sufficient to protect safety functions (auth, RBAC, signed config, audit, integrity). | HZ‑CYBER‑SPOOF‑01 / HZ‑CYBER‑DENIAL‑01 | **ASIL‑influencing (QM/A)** | **Policy‑driven** | **SS‑2/SS‑5:** Isolate channel / restrict control + L3 |

> Life‑threatening hazards (Fire, Gas, CO, Electrical Shock) must not be reduced below **Level 2** post‑mitigation even if formulas suggest lower risk.

**Note:** Requirements under your original “1.3 Safety goals” narrative (Unauthorized Access, Cybersecurity, Electrical Shock, Privacy, Loss of Heating/Cooling) are now covered explicitly by **SG‑012…SG‑016** and will be decomposed into **interface contracts (§7)** and **SYS‑SRs (§8)** next.

## 7 Interface Requirements (contracts)

_Interfaces turn §2 elements into **testable contracts**: freshness, latency, accuracy, semantics, retries, and read‑back. IDs use `IR-xxx`. All timestamps must be monotonic and include a source identifier._

### 7.1 Input — Hardware Sensors

**IR-001 Window/Door Contact**

- Shall publish `state ∈ {open, closed}` with update on each transition; **freshness**: heartbeat every **≥ 10 min**.
- **Latency:** state change reflected in the system **≤ 500 ms**.
- **Quality:** battery level exposed; low‑battery warning when **< 15%**.
- **Verification:** simulated open/close yields two evidence records with correct order.

**IR-002 Smoke Detector**

- Shall publish `alarm ∈ {on, off}` and `fault ∈ {ok, fault}`.
- **Latency:** alarm edge visible **≤ 1 s**; **freshness:** heartbeat or supervised link **≤ 60 s**.
- **Self‑test:** capability or maintenance reminder interval **≤ 6 months**.
- **Verification:** inject alarm → L1 notify path triggered; evidence contains `rule_id=SYS‑SR‑120`.

**IR-003 Gas Detector**

- Same structure as IR‑002; **ventilation** actuation must be possible (see OR‑003).
- **Latency:** alarm edge **≤ 1 s**.

**IR-004 CO Detector**

- Same structure as IR‑002; **Latency:** alarm edge **≤ 1 s**; bedroom entities flagged for repeat policy.

**IR-005 Leak Sensor**

- Shall publish `state ∈ {dry, wet}` with debounce supported in SW; **Latency:** wet edge **≤ 1 s**.

**IR-006 Room Climate (Temp/Humidity)**

- **Accuracy:** temp ±0.5 °C; humidity ±3 %RH.
- **Rate:** updates **≥ 0.5 Hz**; **freshness:** drop sample if `age > 90 s`.
- **Semantics:** payload `{ts, value, unit, src}`; reject if unit mismatch.

**IR-007 Indoor Air Quality (CO₂/PM/VOC)**

- **Accuracy:** CO₂ ±(50 ppm + 3%); PM2.5 per sensor spec; VOC relative index.
- **Rate:** **≥ 0.2 Hz**; **freshness:** drop if `age > 120 s`.

**IR-008 Boiler Signals/Measurements**

- Expose flow temperature, burner state, error codes.
- **Rate:** flow temp **≥ 0.2 Hz**; **freshness:** drop if `age > 120 s`.
- **Semantics:** discrete errors as enumerations with code table.

### 7.2 Input — Cloud/Data Feeds

**IR-020 Weather (Current & Forecast)**

- Provide temperature, pressure, wind speed, clouds; **forecast horizon ≥ 12 h**.
- **Freshness:** current `age ≤ 10 min`; forecast updated **≥ 2 h**.
- **Hazard flags:** storm, blizzard, wind, rain, heatwave, tornado as booleans with start/end times.

**IR-021 Occupancy Status**

- Publish household states (Sleep, Leave <1 day, Vacation >1 day, Home Alone, Guests, Kids, Occupied) as inputs **only**; must include source and confidence if applicable.
- **Freshness:** `age ≤ 5 min`. _(Does not control modes; see §3.)_

**IR-022 Outdoor Air Quality**

- Provide PM2.5/CO₂ or AQI; **Freshness:** `age ≤ 30 min`.

**IR-023 System Health & Updates**

- Provide platform update availability and advisories; **Freshness:** `age ≤ 24 h`.

**IR-024 Network Telemetry**

- Ethernet port status, router link, WAN link, latency ms, packet loss %.
- **Freshness:** metrics every **≥ 60 s**; **Thresholds:** configurable alert limits.

### 7.3 Output — Hardware Actuators

**OR-001 Smart Locks**

- Command set: `lock`, `unlock`.
- **Latency:** command executed **≤ 2 s**; **verification:** read‑back state within **≤ 2 s**; retry **N_retry** with **T_cooldown**.
- **Fail‑safe:** if verification fails → escalate L2.

**OR-002 Siren**

- Commands: `on`, `off`, optional patterns; **Latency:** **≤ 1.5 s** to sound on L1.

**OR-003 Ventilation / Gas Valve**

- Commands: `vent_on/off`; `gas_valve_open/close`; **Latency:** **≤ 5 s** close valve; verify end‑state.

**OR-004 Water Shutoff Valve**

- Command: `close`; **Latency:** **≤ 5 s**; **verification** required; failures → L2.

**OR-005 Information / Alert Lights**

- Commands: set color (info/alert yellow), brightness, on/off; **Latency:** **≤ 1 s**; restoration to previous state on clear.

**OR-006 HVAC Mode/Setpoint**

- Commands: `heat`, `cool`, `auto`, setpoint; **Latency:** **≤ 2 s** to accept command; read‑back mandatory.

**OR-007 Window Actuators**

- Commands: `close`; **Latency:** **≤ 2 s** to start motion; verify closed or report fault.

### 7.4 Output — Cloud/UI Actuators

**OR-020 Phone Application Notification**

- Profiles per §4 (L1–L4); **Deadline:** L1 **≤ 10 s**, L2/L3 **≤ 30 s**; repeat policy for L1 (configurable).
- **Queueing:** in Local‑Only, queue and flush on WAN recovery.

**OR-021 Dashboard Main Safety Card**

- Must support **HAZARD/WARNING/INFO** badges; **acknowledge** action that silences repeats but does not clear fault.

**OR-022 User Action Scheduler/Prompts**

- Provide actionable reminders (e.g., maintenance tests); must log acknowledgements.

**OR-023 Cellular/SMS Gateway (optional)**

- When configured, shall dispatch L1 as SMS; **deadline ≤ 10 s**; **rate‑limit** to avoid spam; log correlation IDs.

### 7.5 Data Semantics & Quality

**IR-040 Timestamps & Freshness**

- Each input includes `ts` (UTC), `src`, optional `seq`. Drop samples with `now − ts > T_stale` or `seq` gaps > **Δseq_max**.

**IR-041 Units & Ranges**

- Temp °C; humidity %RH; CO₂ ppm; PM2.5 µg/m³; wind m/s; pressure hPa. Reject invalid units/ranges.

**IR-042 Plausibility**

- Apply per‑sensor checks (range, rate‑of‑change, stuck‑at, timeout). On failure, mark channel **Degraded** and prefer conservative actions.

### 7.6 Timing Contracts (derived from SG FTTI)

- **Actuation verification** must complete within **2 s** of command where specified.
- **Decision loop** must ensure `T_detection + T_decision + T_recovery + T_effect ≤ FTTI` per SG (see §6).
- **Notification deadlines** per §4.

### 7.7 Interface Evidence & Logging

- For each command or hazard transition, emit an **evidence record** including `{ts, entity/service, inputs summary, thresholds, decision, action list, result, latency_ms}`.
- Evidence write failures must not block safety decisions; retry asynchronously.

### 7.8 Verification Methods (per interface)

- **State transition tests** for contacts/sensors with clock skew injection.
- **HIL (hardware‑in‑loop)** for valves, siren, locks, window actuators.
- **Network emulation** for WAN loss and latency/packet‑loss thresholds.
- **Load tests** to validate decision latency and notification deadlines.

## 8 System Requirements (component‑based)

_We model the system as **decoupled Safety Components**, each implementing one or more **Safety Mechanisms (SMx)**. Components raise **Prefaults** (granular, per‑room/per‑sensor) that are **aggregated** into higher‑level **Faults** (user‑visible with attributes). All requirements are **parameterized** (no hard numbers), referencing §7 interfaces and §6 safety goals._

### 8.1 Component Model & Aggregation Rules

- **Prefault (PR‑xxx):** Early warning for a specific subject (e.g., a room). Multiple prefaults may exist simultaneously.
- **Fault (F‑xxx):** Aggregation of one or more related prefaults into a single user‑visible condition with **attributes** (e.g., list of affected rooms). UX shows **Faults**; Prefaults appear only in logs/evidence.
- **Aggregation policy:**

  - When ≥1 prefaults of the same family are active, raise one Fault with `attributes.subjects = {subjects of PR}`.
  - Fault **clears** when no prefault in the family remains active for **T_clear** (hysteresis/suppression apply).
  - Updates to the prefault set **patch** Fault attributes (add/remove subjects) without re‑notifying unless severity level changes.

---

### 8.2 Temperature Safety Component (C‑TEMP)

**Scope:** SG‑001 (Undercooling), SG‑002 (Prediction), SG‑004 (Overheating), SG‑003 (Diagnostics linkage).
**Safety Mechanisms:** **SM1 LowTemperatureMonitoring**, **SM2 LowTemperatureForecasting**, **SM3 HighTemperatureMonitoring**.

#### 8.2.1 Inputs (from §7)

- **IR‑006 Room Climate (Temp/Humidity)** per room.
- **IR‑001 Window/Door Contacts** (for context, optional).
- **IR‑020 Weather** (outside temperature & forecast) — optional for forecasting.
- **IR‑008 Boiler/flow temp** (health heuristic, optional).

#### 8.2.2 Outputs (to §7)

- **OR‑006 HVAC Mode/Setpoint** (fallback heat/cool).
- **OR‑020/021** Notifications (L2/L3 as per §4).

#### 8.2.3 Parameters (from `safety.yaml`)

- **T_min, T_max** — comfort/safety thresholds per room.
- **T_det, T_det_hot** — detection windows.
- **H, H_hot** — hysteresis bands.
- **S, S_hot** — suppression windows (alert storm control).
- **H_pred** — forecast horizon.
- **C_min** — minimum forecast confidence.
- **T_escalate** — prefault→fault escalation time.
- **T_stable** — time to hold stable conditions before clearing.
- **T_decision_max, T_notify** — per §7/§4.
- **Rooms\[]** — mapping room→sensor entity IDs.

#### 8.2.4 States & Events

- **Prefaults:**

  - `PR_TEMP_UNDER[room]` — `T_room < T_min` sustained **T_det** (with **H**, **S**).
  - `PR_TEMP_OVER[room]` — `T_room > T_max` sustained **T_det_hot** (with **H_hot**, **S_hot**).
  - `PR_TEMP_UNDER_FORECAST[room]` — forecast breach within **H_pred** with `confidence ≥ C_min` and `ΔT ≥ ΔT_min`.

- **Faults (aggregated):**

  - `F_UNDERTEMP` — any `PR_TEMP_UNDER[*]` active; attributes: `{rooms:[...]}`.
  - `F_OVERTEMP` — any `PR_TEMP_OVER[*]` active; attributes: `{rooms:[...]}`.
  - `F_UNDERTEMP_RISK` — any `PR_TEMP_UNDER_FORECAST[*]` active; attributes: `{rooms:[...]}`.

#### 8.2.5 Requirements (C‑TEMP → SYS‑SR‑TEMP‑xxx)

**Detection & Escalation**

- **SYS‑SR‑TEMP‑001 (Under‑detect):** The component **shall** detect `T_room < T_min` sustained for **T_det** with hysteresis **H** and suppression **S**, and raise `PR_TEMP_UNDER[room]` within **T_decision_max**.
- **SYS‑SR‑TEMP‑002 (Under‑escalate):** If `PR_TEMP_UNDER[room]` persists for **T_escalate**, the system **shall** assert `F_UNDERTEMP` (if not active) or update its attributes to include `room`.
- **SYS‑SR‑TEMP‑003 (Over‑detect):** The component **shall** detect `T_room > T_max` sustained for **T_det_hot** with hysteresis **H_hot** and suppression **S_hot**, and raise `PR_TEMP_OVER[room]` within **T_decision_max**.
- **SYS‑SR‑TEMP‑004 (Over‑escalate):** If `PR_TEMP_OVER[room]` persists for **T_escalate**, the system **shall** assert `F_OVERTEMP` (or update attributes).
- **SYS‑SR‑TEMP‑005 (Forecast‑detect):** The component **shall** forecast room temperature **H_pred** ahead; when predicted `< T_min` with `confidence ≥ C_min` and `ΔT ≥ ΔT_min`, it **shall** raise `PR_TEMP_UNDER_FORECAST[room]`. Forecasting runs in **shadow** until precision ≥ **C_target**.
- **SYS‑SR‑TEMP‑006 (Clear rules):** A prefault **shall clear** only after conditions are inside thresholds for **≥ T_stable**; faults clear when **no prefault** remains active for **≥ T_stable**.

**Recovery & Control**

- **SYS‑SR‑TEMP‑010 (Fallback heat):** On `F_UNDERTEMP`, the system **shall** command heating via **OR‑006** (idempotent, with `N_retry`/`T_cooldown`) and verify read‑back; failures escalate to **L3**.
- **SYS‑SR‑TEMP‑011 (Emergency cool/vent):** On `F_OVERTEMP`, the system **shall** command cooling/ventilation via **OR‑006** and verify read‑back; failures escalate to **L3**.
- **SYS‑SR‑TEMP‑012 (Advisories):** On `F_UNDERTEMP_RISK`, the system **shall** suggest mitigations (e.g., close windows, open doors to mix air) in the notification payload; no actuation unless **policy flag** enables pre‑heat.

**Notifications**

- **SYS‑SR‑TEMP‑020:** On `F_UNDERTEMP` and `F_OVERTEMP`, send **L2** within **T_notify**; include `{rooms, current_temp, thresholds}` in payload.
- **SYS‑SR‑TEMP‑021:** On `F_UNDERTEMP_RISK`, send **L3** within **T_notify**; include forecast summary `{H_pred, confidence, ΔT}`.

**Diagnostics & Evidence**

- **SYS‑SR‑TEMP‑030:** Each decision **shall** emit an evidence record with `{room, rule_id, inputs(min/max/avg), thresholds, debounce/suppression, decision, latency_ms}`; evidence failures must not block the loop.
- **SYS‑SR‑TEMP‑031:** Reject/stamp stale samples where `now − ts > T_stale` per **IR‑040**; record channel degradation events.

**Performance & FTTI**

- **SYS‑SR‑TEMP‑040:** Ensure `T_detection + T_decision + T_recovery + T_effect ≤ FTTI` for **SG‑001/004**.
- **SYS‑SR‑TEMP‑041:** Decision path p95 **≤ T_decision_max** under peak sensor rate.

**Aggregation/UX**

- **SYS‑SR‑TEMP‑050:** The UI **shall** present a single `F_UNDERTEMP`/`F_OVERTEMP` card with an attribute list of affected rooms; per‑room prefaults are visible only in logs.

**Dependencies & Conflicts**

- **SYS‑SR‑TEMP‑060:** When in **M3 Sleep**, suppress non‑life‑safety noisy actions; temperature control commands remain allowed.
- **SYS‑SR‑TEMP‑061:** When in **M4 Local‑Only**, continue local HVAC control; queue cloud notifications per §4.

#### 8.2.6 Mapping

- **SG‑001:** SYS‑SR‑TEMP‑001/002/010/020/030/040/041/050/060/061
- **SG‑002:** SYS‑SR‑TEMP‑005/012/021/030
- **SG‑004:** SYS‑SR‑TEMP‑003/004/011/020/030/040/041/050/060/061
- **SG‑003:** SYS‑SR‑TEMP‑031 (diagnostics linkage)

#### 8.2.7 Verification

- **Unit tests:** threshold/hysteresis/suppression logic; forecast shadow accuracy ≥ **C_target** before activation.
- **Integration:** per‑room sensor playback; HVAC actuation with read‑back and retries.
- **E2E drills:** scripted under/over‑temperature scenarios across multiple rooms; verify aggregation and notifications.

---

### 8.3 Door/Window Security Component (C-SEC)

**Scope:** SG-015 (Unauthorized Access / Entry left open).
**Safety Mechanisms:** **SM1 DoorOpenTimeout**, **SM2 WindowOpenSafety**.

#### 8.3.1 Inputs (from section 7)

- **IR-001 Window/Door Contact** for external doors and critical windows.
- **IR-021 Occupancy Status** (uses `Unoccupied` and `Kids` states).

#### 8.3.2 Outputs (to section 7)

- **OR-001 Smart Locks** (lock-on-timeout if configured).
- **OR-007 Window Actuators** (auto-close if configured).
- **OR-020/021** Notifications.
- **OR-022** User prompts/reminders.

#### 8.3.3 Parameters (from `safety.yaml`)

- **ExternalDoors[]** - list of door contact entities to enforce.
- **CriticalWindows[]** - list of window contact entities to enforce.
- **T_door_close_timeout** - max allowed open duration before action.
- **T_window_close_timeout** - max allowed open duration in gated conditions.
- **T_escalate** - prefault-to-fault escalation time.
- **T_stable** - time to hold closed before clearing.
- **AutoLockEnabled** - enable lock attempts on external doors.
- **AutoCloseWindowsEnabled** - enable actuator close attempts.
- **OccupancyGateStates** - states that require closure (`Unoccupied`, `Kids`).

#### 8.3.4 States & Events

- **Prefaults:**
  - `PR_DOOR_OPEN_TIMEOUT[door]` - door open longer than **T_door_close_timeout**.
  - `PR_WINDOW_OPEN_UNSAFE[window]` - critical window open while occupancy is in **OccupancyGateStates**.

- **Faults (aggregated):**
  - `F_DOOR_OPEN` - any `PR_DOOR_OPEN_TIMEOUT[*]` active; attributes: `{doors:[...]}`.
  - `F_WINDOW_OPEN_UNSAFE` - any `PR_WINDOW_OPEN_UNSAFE[*]` active; attributes: `{windows:[...]}`.

#### 8.3.5 Requirements (C-SEC -> SYS-SR-SEC-xxx)

**Detection & Escalation**

- **SYS-SR-SEC-001 (Door timeout detect):** The component **shall** detect an external door open longer than **T_door_close_timeout** and raise `PR_DOOR_OPEN_TIMEOUT[door]` within **T_decision_max**.
- **SYS-SR-SEC-002 (Door escalate):** If `PR_DOOR_OPEN_TIMEOUT[door]` persists for **T_escalate**, the system **shall** assert `F_DOOR_OPEN` (or update attributes to include `door`).
- **SYS-SR-SEC-003 (Window unsafe detect):** When occupancy state is in **OccupancyGateStates**, the component **shall** detect any critical window open longer than **T_window_close_timeout** and raise `PR_WINDOW_OPEN_UNSAFE[window]` within **T_decision_max**.
- **SYS-SR-SEC-004 (Window escalate):** If `PR_WINDOW_OPEN_UNSAFE[window]` persists for **T_escalate**, the system **shall** assert `F_WINDOW_OPEN_UNSAFE` (or update attributes).

**Recovery & Control**

- **SYS-SR-SEC-010 (Auto-lock):** On `PR_DOOR_OPEN_TIMEOUT` or `F_DOOR_OPEN`, if **AutoLockEnabled** and a lock actuator is configured, the system **shall** command **OR-001** and verify read-back within **T_verify_actuation**; failures trigger **L2** with `{door, reason}`.
- **SYS-SR-SEC-011 (Auto-close window):** On `PR_WINDOW_OPEN_UNSAFE` or `F_WINDOW_OPEN_UNSAFE`, if **AutoCloseWindowsEnabled** and a window actuator is configured, the system **shall** command **OR-007** and verify closure; otherwise it **shall** issue a user prompt via **OR-022**.

**Notifications**

- **SYS-SR-SEC-020:** On `F_DOOR_OPEN` or `F_WINDOW_OPEN_UNSAFE`, send **L2** within **T_notify** with `{subjects, occupancy_state, duration}`.

**Diagnostics & Evidence**

- **SYS-SR-SEC-030:** Each decision **shall** emit an evidence record with `{subject, occupancy_state, timeout, decision, latency_ms}`.

**Performance & FTTI**

- **SYS-SR-SEC-040:** Ensure `T_detection + T_decision + T_recovery + T_effect <= FTTI` for **SG-015**.

**Aggregation/UX**

- **SYS-SR-SEC-050:** The UI **shall** present a single `F_DOOR_OPEN` and `F_WINDOW_OPEN_UNSAFE` card with an attribute list of affected doors/windows; prefaults are visible only in logs.

**Dependencies & Conflicts**

- **SYS-SR-SEC-060:** In **M3 Sleep**, continue enforcement but apply quiet notification profiles.
- **SYS-SR-SEC-061:** In **M4 Local-Only**, queue cloud notifications; prefer local vectors per section 4.

#### 8.3.6 Mapping

- **SG-015:** SYS-SR-SEC-001/002/003/004/010/011/020/030/040/050/060/061

#### 8.3.7 Verification

- **Unit tests:** door/window open timeout logic; occupancy gating for `Unoccupied` and `Kids`.
- **Integration:** contact sensor replay with lock/window actuator read-back.
- **E2E drills:** unoccupied scenario with external door left open; verify escalation, notifications, and fault aggregation.

---

> **Next components to define (same pattern):** Fire/CO/Gas (C‑ALARM), Water Leak (C‑LEAK), Air Quality (C‑AQ), HVAC Health (C‑HVAC), Privacy (C‑PRIV), Network/Platform Health (C‑NET), Weather Ingress (C‑WX). Say which one you want next and I’ll add it.

## 9 Non‑Functional Requirements (NFR)

_Non‑functional constraints that apply across all components. IDs use `NFR‑xxx`._

### 9.1 Performance & Timing

- **NFR‑001 Decision latency:** Safety decision path **p95 ≤ T_decision_max** and **p99 ≤ T_decision_max_p99** under peak input rate.
- **NFR‑002 FTTI compliance:** For each SG, `T_detection + T_decision + T_recovery + T_effect ≤ FTTI` (see §6). Budget tracked per component.
- **NFR‑003 Notification deadlines:** Deliver **L1 ≤ T_notify_L1**, **L2/L3 ≤ T_notify_L23**; **L4** best‑effort (§4).
- **NFR‑004 Actuation verification:** Read‑back state within **T_verify_actuation**; on mismatch → retry **N_retry** with cooldown **T_cooldown**.

### 9.2 Reliability & Availability

- **NFR‑010 Watchdog:** A software watchdog **shall** detect loop stalls ≥ **T_watchdog** and log **EVT_WATCHDOG**; optional auto‑recover per policy.
- **NFR‑011 Data integrity:** Inputs lacking `ts/src` or failing CRC/format checks **shall** be rejected and logged as **Degraded**.
- **NFR‑012 Persistence:** Evidence and config **shall** survive process restarts and power cycles (durable writes or journal).
- **NFR‑013 UPS posture:** On power failure detection, prefer local safe states (e.g., close valve, unlock door for fire) when feasible.

### 9.3 Security (safety‑relevant)

- **NFR‑020 AuthN/AuthZ:** Administrative actions require **strong auth**; runtime actuation restricted by **RBAC**; audit all privileged operations.
- **NFR‑021 Config integrity:** `safety.yaml` changes must be **signed or checksum‑verified**; on failure → refuse load, remain in last known good with **L3** notice.
- **NFR‑022 Secrets handling:** Credentials stored via platform secrets; never in evidence logs.
- **NFR‑023 Network posture:** Prefer **local control paths** for life‑safety; cloud paths treated as best‑effort.

### 9.4 Maintainability & Modularity

- **NFR‑030 Component isolation:** Safety components (C‑TEMP, C‑ALARM, …) **shall** expose clear inputs/outputs and not share mutable state (except via evidence/metrics).
- **NFR‑031 Freedom from interference:** Non‑safety automations **shall not** preempt or delay safety decisions/actuations beyond **T_fi_max**.
- **NFR‑032 Feature flags:** New mechanisms (e.g., forecasting) start in **shadow mode** and only activate when **C_target** is met.

### 9.5 Observability & Evidence

- **NFR‑040 Evidence schema:** Each decision/command emits evidence `{ts, rule_id, inputs(min/max/avg), thresholds, debounce/suppression, action, result, latency_ms}` (§7.7).
- **NFR‑041 Metrics:** Export counters/gauges for `decisions_total{rule,decision}`, `suppression_active`, `decision_latency_ms` (p50/p95/p99), and per‑interface freshness.
- **NFR‑042 Retention:** Keep evidence for **T_evidence_retention** (rolling); rotate files daily; protect against unbounded growth.

### 9.6 Usability & UX

- **NFR‑050 Acknowledgement:** L1–L3 notifications **shall** be acknowledgeable from UI; ack silences repeats but does not clear faults.
- **NFR‑051 Accessibility:** Visual alerts (lights/UI) must be paired with audible alerts for L1 to support different user needs.

### 9.7 Portability & Configurability

- **NFR‑060 Config‑only tuning:** All thresholds/timers are parameters (no hard‑coding). Per‑room/zone overrides supported.
- **NFR‑061 Hardware‑agnostic:** Interfaces adhere to §7 contracts so any compliant sensor/actuator can be used.

### 9.8 Compliance & Testing

- **NFR‑070 Testability:** Each requirement maps to unit/integration/HIL tests; fault injection covers timeout, stuck‑at, stale, comms loss.
- **NFR‑071 Drills:** Periodic household drills for L1 scenarios (fire/CO/gas) logged as **TEST** with opt‑out window.

---

## 10 Glossary

- **HARA:** Hazard Analysis and Risk Assessment used to derive SGs and FTTIs.
- **Safety Goal (SG):** Top‑level safety objective linked to a hazard with a required **FTTI** and **Safe State**.
- **FTTI:** Fault Tolerant Time Interval — max allowed time from fault occurrence to reaching the safe state.
- **Safe State (SS‑x):** Predefined state that reduces risk to an acceptable level (e.g., SS‑Alarm, SS‑1…SS‑5).
- **Prefault (PR‑xxx):** Early warning for a specific subject (room/sensor) prior to raising a consolidated Fault.
- **Fault (F‑xxx):** Aggregated, user‑visible condition comprising one or more prefaults with attributes.
- **Suppression window (S):** Minimum time between repeated alerts to avoid storming.
- **Hysteresis (H):** Band around a threshold preventing chatter.
- **Shadow mode:** Mechanism runs without actuation to measure precision before activation.
- **Read‑back verification:** Check that an actuator achieved the commanded state within **T_verify_actuation**.
- **Freedom from interference:** Assurance that non‑safety code cannot degrade safety behavior beyond **T_fi_max**.
- **Local‑Only mode:** Operation when WAN is down; use local actuations and queue cloud notifications.
- **Evidence:** Immutable log of decisions/commands enabling traceability and audits.
- **ROC:** Rate of Change check used in plausibility diagnostics.

---

## 11 Parameter Table (Proposed Defaults)

> Defaults are **non‑binding** and exist to bootstrap configuration; tune per installation/HARA.

| Name                     | Description                                  | Proposed Default |
| ------------------------ | -------------------------------------------- | ---------------- |
| **T_min**                | Minimum safe room temperature                | 17 °C (per room) |
| **T_max**                | Maximum safe room temperature                | 29 °C (per room) |
| **T_crit**               | Max duration below **T_min** (SG‑001)        | 10 min           |
| **T_crit_hot**           | Max duration above **T_max** (SG‑004)        | 5 min            |
| **T_det**                | Cold‑side detection window                   | 120–360 s        |
| **H**                    | Cold hysteresis band                         | 0.5–1.5 °C       |
| **S**                    | Cold suppression window                      | 60–180 s         |
| **T_det_hot**            | Hot‑side detection window                    | 60–180 s         |
| **H_hot**                | Hot hysteresis band                          | 0.5–1.5 °C       |
| **S_hot**                | Hot suppression window                       | 60–180 s         |
| **H_pred**               | Temperature forecast horizon                 | 5–15 min         |
| **C_min**                | Min forecast confidence (temp)               | 0.7–0.8          |
| **ΔT_min**               | Min forecast delta                           | 0.5–1.0 °C       |
| **H_pred_aq**            | AQ forecast horizon                          | 10–30 min        |
| **C_min_aq**             | Min forecast confidence (AQ)                 | 0.7–0.8          |
| **T_timeout**            | Sensor/comm timeout (general)                | 30–60 s          |
| **dT/dt_max**            | Max allowed temp ROC                         | 2–5 °C/min       |
| **Δt_max**               | Max timebase error                           | 20–100 ms        |
| **f_sensor_min**         | Min sensor frequency (general)               | 0.2–1 Hz         |
| **T_stable**             | Stable time before clearing prefault/fault   | 5–15 min         |
| **T_notify_L1**          | L1 delivery deadline                         | ≤ 10 s           |
| **T_notify_L23**         | L2/L3 delivery deadline                      | ≤ 30 s           |
| **T_decision_max**       | Max decision compute time (p95)              | ≤ 100 ms         |
| **T_decision_max_p99**   | Max decision compute time (p99)              | ≤ 250 ms         |
| **C_target**             | Shadow precision KPI to activate forecasting | ≥ 70 %           |
| **T_timeout_aq**         | AQ stale timeout                             | 60–120 s         |
| **T_act_aq**             | AQ actuation deadline                        | ≤ 30 s           |
| **Leak_debounce**        | Debounce for leak sensors                    | 0.2–1.0 s        |
| **Valve_close_s**        | Water/gas valve close verification time      | ≤ 5 s            |
| **Window_close_start_s** | Start motion after close command             | ≤ 2 s            |
| **ExternalDoors**        | External door contact entity list            | user-defined     |
| **CriticalWindows**      | Critical window contact entity list          | user-defined     |
| **T_door_close_timeout** | Door open timeout before enforcement         | 30-120 s         |
| **T_window_close_timeout** | Window open timeout in gated conditions    | 30-300 s         |
| **OccupancyGateStates**  | Occupancy states that require closure        | Unoccupied, Kids |
| **AutoLockEnabled**      | Enable auto-lock attempts on external doors  | false            |
| **AutoCloseWindowsEnabled** | Enable auto-close attempts on windows     | false            |
| **N_retry**              | Retries for actuation/notify                 | 1–3              |
| **T_cooldown**           | Cooldown between retries                     | 30–120 s         |
| **T_watchdog**           | Loop stall detection interval                | 2–5 s            |
| **T_evidence_retention** | Evidence retention period                    | 30–90 days       |
| **WAN_loss_threshold**   | Condition to enter Local‑Only (M4)           | WAN link = down  |
| **SMS_enabled**          | Enable SMS/cellular fallback                 | false            |
| **SMS_max_retries**      | Max SMS send retries                         | 3                |
| **SMS_cooldown_s**       | Cooldown between SMS retries                 | 60 s             |

_All parameters live in `safety.yaml` (see §4.5 and §8.2.3). Per‑room overrides apply to temperature parameters; per‑zone overrides may be added for AQ._
