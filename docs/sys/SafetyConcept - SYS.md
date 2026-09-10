# Lean SYS + TSC — Safety Architecture & Requirements (v1.2.0)

**Item:** Home Automation Safety Monitoring & Recovery (multi-hazard)

**Date:** 2025-09-18
**Owner:** System/Safety (SYS)
**Scope:** Blend **ASPICE SYS.x** with **ISO 26262-3/4/6** work products; align with provided **HARA** and **SYS v0.2** inputs.

---

## 1 Purpose and Audience

**Why this document exists (HARA-linked):**

- Provide a **single, lean specification** that turns the existing **HARA** (hazards, S/E/C, initial risk levels) into actionable **Safety Goals, System Requirements, Technical Safety Requirements, Safe States, and FTTI budgets**.
- Maintain **end‑to‑end traceability** from _hazard → safety goal → requirement → verification_, while minimizing work products for a **hobby/semiprofessional, open‑source** effort (no formal certification claim).
- Serve as the **source of truth** for the concept phase and subsequent implementation/validation; any YAML/CSV/config artifacts are generated from this document.

**Intended readers:**

- **Developers** — implement safety logic and interfaces across supported runtimes.
- **Testers** — design and execute unit, integration, HIL, and household drills per the V\&V guidance.
- **Contributors** — propose changes to thresholds/FTTI, add sensors/actuators, improve documentation.
- **Maintainers** — govern releases, parameter changes, evidence retention, and issue triage.
- **Safety reviewer (you)** — resolve open points (ASIL/FTTI confirmation, safe‑state policies, decomposition choices).

**Scope of this document:**

- Covers the **safety‑critical logic** of the _Home Automation Safety App_ (currently running atop **Home Assistant + AppDaemon**), specifically: detection, decision, notification, and where explicitly permitted **actuation** for hazards identified in HARA (Fire/Smoke, Gas, CO, Water Leak, **Undercooling/Overheating**, Air Quality, System/Comms failure, HVAC degradation, Unauthorized Access/Privacy, weather ingress, frost, wind, and outdoor pollution).
- Defines **safety goals, SYS‑level requirements (blended with FSR), TSRs, safe states, timing (FTTI), parameters, and V\&V** at the **system level**. Software requirements and component designs refine this contract in the SSRD and feature architecture documents.

**Out of scope (for clarity):**

- General home‑automation conveniences (scenes, presence lighting, media, non‑safety automations).
- The informational inventory may expose health metadata for entities used by
  those conveniences, but it shall not evaluate or control their automation
  behavior.
- Brand‑specific hardware design/certification and regulatory approvals (this is a best‑effort, non‑certified project).
- Provider payload schemas and class-level software design, which are specified in the SSRD and feature architecture documents.

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
- Entity-health registry and evaluation for explicit safety dependencies,
  component-declared dependencies, and the information-only Home Assistant
  inventory.

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
- Weather/air‑quality feeds and alerting services are reasonably accurate within their stated contracts; free feeds may provide no availability SLA and shall be diagnosed accordingly.
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
- **Retries:** If submission to Home Assistant fails, attempt **N_retry** with
  **T_cooldown** between attempts (configurable). Absence of individual-phone
  delivery confirmation is reported diagnostically and does not by itself
  trigger duplicate pushes. In _Local‑Only_, queue cloud/mobile and prefer
  local lights/siren.
- **Repeat policy (optional):** For persistent L1 events (e.g., CO at night), repeat phone alerts every **T_repeat ≤ 60 s** until acknowledged.

### 4.3 Mode‑Aware Behavior

- **Sleep:** L1 plays sound alarm + lights; L2/L3 use quiet profiles where possible (noisy actions suppressed).
- **Local‑Only:** WAN lost → deliver local lights/siren immediately; queue phone/UI pushes and flush on recovery.
- **Maintenance/Debug:** L1 still delivered; L2/L3 may be tagged as test if event is user‑initiated.

### 4.4 UI/UX Rules

- Dashboard “Main Safety Card” shows **current level badge** (HAZARD/WARNING/INFO) and supports **acknowledge** for L1–L3. Acknowledgement does **not** clear hazards; it silences repeats.
- Lights used for signaling should restore to previous state when the event clears.

### 4.5 Configuration sources and generated contract

`backend/config/system_config.yml` owns software policy, calibration, stable
fault-to-Safety-Mechanism mappings, provider lifecycle, MQTT behavior, and
system health checks. `backend/config/user_config.yml` owns only installation
bindings and operator choices. `backend/build_app_config.py` merges both sources
into the deployable `backend/app_cfg.yaml` contract:

```yaml
app_config:
  faults:
    ExampleFault:
      name: "Human-readable fault name"
      level: 3
      related_sms:
        - "sm_example"

user_config:
  notification:
    mobile:
      services:
        - "notify/all_phones"
      default_url: "https://ha.kojbito.org/5c36e1c9_hakit"
    local:
      light_entity: "light.info"
  localization:
    language: "pl"
```

The generated file shall not be edited directly. API credentials or other
secrets shall remain in the deployment platform's secret store and shall not be
committed to either source file.

Every component section in §8 defines its exact `app_config` and `user_config`
bindings. Configuration fields that are not represented by a validated schema
shall not influence a safety decision.

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

**WAN-loss notification requirements:**

- **SYS-SR-NOT-001:** On WAN loss, the system **shall** deliver L1 locally
  (siren/light) and, if configured, via **cellular/SMS** within
  **T_notify ≤ 10 s**; queued IP notifications **shall** be sent on recovery.
- **SYS-SR-NOT-002:** Cellular/SMS fallback **shall** be rate-limited and logged
  with correlation IDs; failures **shall** trigger local repeats only.

## 5 Item Definition (lean)

**Item:** Safety Monitoring, Notification & Recovery for the home (multi‑hazard).

**Primary Purpose:** Detect, forecast, and mitigate environmental hazards (undercooling/overheating, indoor and outdoor air quality, fire/gas/CO, water leaks, severe weather, frost, and wind) and system/comms failures to maintain safe operation and inform occupants.

**Operating Modes:** per §3 — Startup (M1), Normal (M2), Sleep/Quiet (M3), Local‑Only/WAN‑Lost (M4), Maintenance/Debug (M5), Shutdown (M6).

**Environmental Conditions:** Ambient **−20…+50 °C**; supply voltage per platform; timebase accuracy per host.

**System Boundaries:** as defined in §2 — Inputs (sensors & cloud feeds) → Safety logic → Actuation/Notifications → Evidence/UI. Fault manager behavior is part of the internal processing.

**Assumptions of Use (AoU):**

- **A1.** Sensors are calibrated and provide updates ≥ **f_sensor_min** Hz; communication error rate ≤ **p_comm_max**.
- **A2.** System timebase accuracy ≤ **Δt_max** ms; persistent storage is available for evidence.
- **A3.** Operator response to **L2/L3** notifications within **T_op_resp** minutes (household policy).
- **A4.** Actuation available within **T_act** seconds to effect temperature/AQ changes or shutoff valves.
- **A5.** Occupancy is **an input to some safety goals** but **does not control system modes** (see §3).
- **A6.** External cloud data is advisory and non-certified. External Hazard
  Monitoring shall never actuate from provider data alone; only an authenticated
  resident confirmation of a current allowlisted gate-close proposal may
  authorize a command.

---

## 6 Safety Goals and FTTI

> Classifications are derived from HARA for engineering prioritization; this
> project makes no certification claim. Safe states use shorthand
> (SS‑1…SS‑5, SS‑Alarm). Occupancy is an **input** to some goals but **does not
> drive modes** (see §3).

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
| **SG‑011** | Warn about **weather ingress** via open windows/doors during rain/storm.                                                | HZ‑WEATHER‑01                          | **QM**                      | **120 s after usable input** | **SS‑5:** Prompt manual secure closure + L2      |
| **SG‑012** | Mitigate **loss of heating/cooling** to maintain safe temperatures; alert and apply failover/backup strategies.          | HZ‑HVAC‑LOSS‑01                        | **QM/ASIL A**               | **30 min**        | **SS‑4:** Degraded mode + L3                           |
| **SG‑013** | Reduce **electrical shock** risk via RCD self‑test/reminders and wet‑zone interlocks.                                    | HZ‑ELECT‑01                            | **ASIL A**                  | **24 h**          | **SS‑4:** Degraded mode + L2/L3                        |
| **SG‑014** | Prevent **privacy invasion** by enforcing AV device quiet hours/masking and alerting on unexpected access.               | HZ‑PRIV‑01                             | **QM**                      | **60 s**          | **SS‑5:** Mask/disable AV + L2                         |
| **SG‑015** | Deter and respond to **unauthorized access** (unexpected movement/entry) when home declared unoccupied or during Sleep.  | HZ‑UNAUTH‑01                           | **QM/ASIL A**               | **30 s**          | **SS‑5:** Secure posture (lock/close) + L1/L2          |
| **SG‑016** | Maintain **cybersecurity posture** sufficient to protect safety functions (auth, RBAC, signed config, audit, integrity). | HZ‑CYBER‑SPOOF‑01 / HZ‑CYBER‑DENIAL‑01 | **ASIL‑influencing (QM/A)** | **Policy‑driven** | **SS‑2/SS‑5:** Isolate channel / restrict control + L3 |
| **SG‑017** | Warn when an open window or external door exposes the home to **frost**.                                                | HZ‑EXT‑FROST‑01                        | **QM**                      | **10 min after usable input** | **SS‑5:** Prompt manual closure + L3          |
| **SG‑018** | Warn when an open window or external door is exposed to damaging **wind/gusts**.                                       | HZ‑EXT‑WIND‑01                         | **QM**                      | **120 s after usable input** | **SS‑5:** Prompt manual closure + L2/L3        |
| **SG‑019** | Warn when open external apertures may admit hazardous **outdoor air pollution** and inhibit conflicting advice.        | HZ‑EXT‑AQ‑01                           | **QM/ASIL A**               | **10 min after usable input** | **SS‑5:** Prompt manual closure + L3           |

> Life‑threatening hazards (Fire, Gas, CO, Electrical Shock) must not be reduced below **Level 2** post‑mitigation even if formulas suggest lower risk.

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

**IR-009 Home Assistant Entity Health**

- Every monitored record shall identify the Home Assistant entity, its source
  group, current state, availability, last-change time, last-update time, and
  associated device and area when available.
- Explicit safety entities shall use installation-configured freshness and
  validation policies. Component dependencies shall use contracts owned by the
  consuming Safety Component or application core.
- Safety-relevant entity health shall distinguish `healthy`, `degraded`,
  `stale`, and `unavailable`; a failed or unevaluable check shall never be
  treated as positive healthy evidence.
- The information-only inventory shall expose native Home Assistant state and
  metadata without creating a Safety System symptom, fault, notification, or
  recovery action.

### 7.2 Input — Cloud/Data Feeds

**IR-020 Weather (Current & Forecast)**

- Provide temperature, apparent temperature, pressure, wind speed, wind gust,
  precipitation/rain, weather code, and clouds; **forecast horizon ≥ 12 h**.
- Include provider name, requested and resolved coordinates, source timestamp,
  retrieval timestamp, units, and forecast validity timestamps.
- **Freshness:** retrieval `age ≤ 10 min`; forecast source update interval and
  model age shall be exposed separately and shall not be represented as a local
  real-time observation.

**IR-021 Occupancy Status**

- Publish household states (Sleep, Leave <1 day, Vacation >1 day, Home Alone, Guests, Kids, Occupied) as inputs **only**; must include source and confidence if applicable.
- **Freshness:** `age ≤ 5 min`. _(Does not control modes; see §3.)_

**IR-022 Outdoor Air Quality**

- Provide at least PM2.5, PM10, NO₂, O₃, SO₂, and a named AQI standard when
  available. CO₂ shall not be used as the primary outdoor-pollution indicator.
- Each sample shall identify whether it is a station measurement or model
  forecast and shall include station/grid identity, units, source timestamp,
  retrieval timestamp, and validity time.
- **Freshness:** measured/retrieved data `age ≤ 30 min`; forecast horizon
  **≥ 12 h** and model update age exposed separately.

**IR-023 System Health & Updates**

- Provide platform update availability and advisories; **Freshness:** `age ≤ 24 h`.

**IR-024 Network Telemetry**

- Ethernet port status, router link, WAN link, latency ms, packet loss %.
- **Freshness:** metrics every **≥ 60 s**; **Thresholds:** configurable alert limits.

**IR-025 Official Weather Warnings**

- Provide stable warning ID, event name, authority severity/degree,
  probability, publication time, valid-from, valid-to, authoritative text,
  source, and affected administrative region codes.
- Warnings shall be filtered by configured TERYT codes before entering the
  hazard-decision path.
- A warning update with the same stable ID shall patch the existing condition;
  expiry or explicit withdrawal shall clear it.
- **Freshness:** poll interval `≤ 5 min`; late retrieval shall preserve the
  authority validity interval and expose provider degradation.

**IR-027 External API Provider Health**

- Every external API component shall publish `ok`, `stale`, `unavailable`, or
  `schema_error` together with last attempt, last success, HTTP/status summary,
  schema version/fingerprint, and consecutive failure count.
- Provider health shall be independent: failure of one API shall not stop or
  overwrite the state of another API.

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
- **Routing:** use an explicit configured mobile group or device-service list;
  `notify.notify` shall not be used as a safety-delivery target.
- **Result semantics:** distinguish acceptance by Home Assistant from confirmed
  display or delivery by an individual phone.
- **Lifecycle:** a new alarm may alert; same-fault context changes shall refresh
  quietly; shadowing shall use the Companion `clear_notification` command.
- **Persistence:** active, acknowledged, repeated, and queued delivery state
  shall survive AppDaemon reload and restart.

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

- **Safety Mechanism (`sm_name`):** Stable logic-family identifier used by
  `FaultManager.related_sms`. Each mechanism ID shall map to exactly one fault.
- **Symptom (`Symptom.name`):** Stable per-subject runtime condition, such as a
  room or door. Multiple symptoms may be active simultaneously.
- **Fault:** Stable configured catalog key that aggregates all active symptoms
  whose Safety Mechanism IDs occur in its `related_sms` list. The UX shows
  faults; individual symptoms remain diagnostic context.
- **Aggregation policy:**

  - When at least one related symptom is active, set one fault and aggregate the
    active subjects into its attributes.
  - A fault clears only after every related symptom has cleared.
  - Updates to the symptom set patch fault attributes and refresh the existing
    notification tag without discarding still-active subjects.
  - Fault catalog keys, Safety Mechanism IDs, symptom ID patterns, raw states,
    and entity IDs are stable machine contracts.

---

### 8.2 Temperature Safety Component (C‑TEMP)

**Scope:** SG‑001 (Undercooling), SG‑002 (Prediction), and SG‑004
(Overheating).

**Safety Mechanisms:** `sm_tc_1` direct low temperature, `sm_tc_2` forecast
low temperature, `sm_tc_3` direct high temperature, and `sm_tc_4` forecast high
temperature.

#### 8.2.1 Inputs (from §7)

- **IR‑006 Room Climate** numeric temperature per configured room.
- `DerivativeMonitor` first derivative `<temperature_sensor>_rate` for forecast
  mechanisms.
- **IR‑001 Window Contacts** and a supported cover actuator for an optional
  low-temperature recovery proposal.
- A configured common outside-temperature entity for deciding whether the
  recovery proposal is to open or close the window.

#### 8.2.2 Outputs (to §7)

- Symptom events for FaultManager aggregation.
- **OR‑020/021** fault notifications and dashboard state.
- Optional `ManipulateWindow<Room>` recovery proposals routed through
  RecoveryManager. C‑TEMP does not command HVAC or climate services.
- Diagnostic MQTT sensors for each room's low/high thresholds and derivative
  measurements.

#### 8.2.3 Parameters (from `backend/app_cfg.yaml`)

- Per-room bindings: `area_id`, `temperature_sensor`, optional `window_sensor`,
  and optional cover `actuator`.
- Thresholds and forecast horizon: `CAL_LOW_TEMP_THRESHOLD`,
  `CAL_HIGH_TEMP_THRESHOLD`, and `CAL_FORECAST_TIMESPAN`, inherited from
  component defaults unless overridden for the room.
- Direct-mechanism debounce:
  `SM_TC_1_DEBOUNCE_LIMIT` and `SM_TC_1_REEVAL_DELAY_SECONDS`.
- Forecast-mechanism debounce and derivative sampling:
  `SM_TC_2_DEBOUNCE_LIMIT`, `SM_TC_2_REEVAL_DELAY_SECONDS`, and
  `SM_TC_2_DERIVATIVE_SAMPLE_MINUTES`.
- Plausibility bounds: `SM_TC_MIN_VALID_TEMPERATURE_C`,
  `SM_TC_MAX_VALID_TEMPERATURE_C`, `SM_TC_MAX_ABS_RATE_C_PER_MIN`, and
  `SM_TC_MAX_FORECAST_DELTA_C`.

#### 8.2.4 Runtime identifier contract

| System mechanism | Runtime ID | Positive condition | Symptom ID | Fault ID |
| --- | --- | --- | --- | --- |
| Direct low temperature | `sm_tc_1` | current temperature `< CAL_LOW_TEMP_THRESHOLD` | `RiskyTemperature{Room}` | `RiskyTemperature` |
| Forecast low temperature | `sm_tc_2` | projected temperature `< CAL_LOW_TEMP_THRESHOLD` | `RiskyTemperature{Room}ForeCast` | `RiskyTemperatureForecast` |
| Direct high temperature | `sm_tc_3` | current temperature `> CAL_HIGH_TEMP_THRESHOLD` | `RiskyTemperatureHigh{Room}` | `RiskyTemperature` |
| Forecast high temperature | `sm_tc_4` | projected temperature `> CAL_HIGH_TEMP_THRESHOLD` | `RiskyTemperatureHigh{Room}ForeCast` | `RiskyTemperatureForecast` |

`ForeCast` capitalization is retained as part of the existing runtime contract.

| Fault ID | Level | `related_sms` | Shadowing |
| --- | ---: | --- | --- |
| `RiskyTemperature` | 2 | `sm_tc_1`, `sm_tc_3` | Shadows `RiskyTemperatureForecast` while active |
| `RiskyTemperatureForecast` | 3 | `sm_tc_2`, `sm_tc_4` | None |

#### 8.2.5 Requirements (C-TEMP → SYS-SR-TEMP-xxx)

- **SYS-SR-TEMP-001:** For every configured room, C‑TEMP shall instantiate
  `sm_tc_1`, `sm_tc_2`, `sm_tc_3`, and `sm_tc_4` using the stable symptom ID
  patterns in §8.2.4.
- **SYS-SR-TEMP-002:** Direct mechanisms shall compare the current numeric room
  temperature with the configured low or high threshold using strict `<` and
  `>` comparisons.
- **SYS-SR-TEMP-003:** Forecast mechanisms shall calculate a linear projection
  from current temperature, the first derivative expressed in degrees Celsius
  per minute, and the configured forecast timespan. The projection shall be
  rejected when its rate, delta, or resulting temperature exceeds calibrated
  plausibility bounds.
- **SYS-SR-TEMP-004:** Missing, non-numeric, non-finite, `unknown`,
  `unavailable`, or otherwise invalid temperature or derivative input shall not
  constitute positive evidence to set or clear an active temperature symptom.
- **SYS-SR-TEMP-005:** Each mechanism shall apply its configured debounce limit
  before changing symptom state and shall schedule reevaluation using its
  configured delay while debouncing remains incomplete.
- **SYS-SR-TEMP-006:** `DerivativeMonitor` shall publish first- and second-order
  diagnostic derivatives. C‑TEMP shall consume only the first derivative for
  forecast decisions and shall retain ownership of all temperature thresholds.
- **SYS-SR-TEMP-007:** C‑TEMP shall expose separate diagnostic MQTT sensors for
  each room's low and high thresholds as `<source>_low_threshold` and
  `<source>_high_threshold`.
- **SYS-SR-TEMP-008:** Threshold diagnostics shall expose source entity,
  threshold type, `area_id`, and the resolved Home Assistant area name.
- **SYS-SR-TEMP-009:** Low-temperature mechanisms may create a
  `ManipulateWindow{Room}` recovery proposal using the configured window sensor
  or cover actuator and the indoor/outdoor temperature relation. High-temperature
  mechanisms shall create no recovery action. C‑TEMP shall not issue HVAC or
  climate commands.
- **SYS-SR-TEMP-010:** Direct low/high symptoms shall aggregate into
  `RiskyTemperature`; forecast low/high symptoms shall aggregate into
  `RiskyTemperatureForecast`; the direct fault shall shadow the forecast fault
  while active. A fault shall remain active until every related symptom clears.

#### 8.2.6 Mapping

- **SG‑001:** SYS-SR-TEMP-001/002/004/005/007/008/009/010
- **SG‑002:** SYS-SR-TEMP-001/003/004/005/006/009/010
- **SG‑004:** SYS-SR-TEMP-001/002/003/004/005/006/007/008/010

#### 8.2.7 Verification

- **Unit tests:** strict low/high comparisons, low/high forecasting, invalid and
  non-finite inputs, debounce set/clear behavior, and stable symptom IDs.
- **Integration:** per-room state playback, derivative publication, threshold
  MQTT diagnostics, fault aggregation/shadowing, and low-temperature recovery
  proposals.
- **Negative control tests:** high-temperature paths create no recovery action,
  and C‑TEMP makes no HVAC or climate service call.

---

### 8.3 External Hazard Monitoring Component (C-EXT)

**Scope:** SG-011 (Rain/Storm Ingress), SG-017 (Frost), SG-018
(Wind), SG-019 (Outdoor Pollution), and SG-003 (Diagnostics linkage).

**Safety Mechanisms:** **SM-EXT-1 WeatherExposureMonitoring**,
**SM-EXT-2 OutdoorPollutionExposureMonitoring**, and
**SM-EXT-4 ExternalProviderDiagnostics**.

#### 8.3.1 Component boundaries

- `ExternalHazardComponent` is the only Safety Component in this feature. It
  owns household policy, contact correlation, symptom lifecycle, aggregation,
  notification context, and advice-inhibition state.
- Each remote API has a separate API Component. API Components perform
  transport, provider-schema validation, provider-specific unit mapping, and
  publication of normalized observations. They do not create symptoms, faults,
  notifications, or recovery actions.
- The API Components are:
  `OpenMeteoWeatherApiComponent`, `ImgwWarningsApiComponent`, and
  `OpenMeteoAirQualityApiComponent`.
- API Components may share an injected HTTP transport and common immutable data
  types, but shall not share polling schedules, failure counters, cached
  payloads, or provider health.

#### 8.3.2 Inputs (from §7)

- **IR-001 Window/Door Contacts** for configured external apertures.
- **IR-020 Weather (Current & Forecast)** from the dedicated Open-Meteo weather
  API component.
- **IR-022 Outdoor Air Quality** from the current Open-Meteo model API
  component for the configured home coordinates.
- **IR-025 Official Weather Warnings** from the dedicated IMGW warning API
  component.
- **IR-027 External API Provider Health** from every API component.

#### 8.3.3 Outputs (to §7)

- **OR-020/021** notification and dashboard outputs for every exposure.
- **OR-006/007** only for closing the explicitly configured garage and external
  gate covers after authenticated SafetyHome confirmation.
- Diagnostic MQTT entities for normalized hazard state and per-provider health.
- An advice policy that can inhibit contradictory recommendations
  such as opening windows during external pollution, damaging wind, or storm.
- C-EXT shall not use locks, HVAC, ventilation, raw relay/pulse buttons, or any
  actuator other than the two configured directional gate covers.

#### 8.3.4 Parameters

- Site identity: latitude, longitude, timezone, country, and configured TERYT
  codes.
- Opening registry: stable opening name, `entity_id`, `area_id`, opening kind,
  applicable hazard types, execution policy, and optional allowlisted
  `cover.*` actuator.
- Weather policy: frost watch/warning temperature, wind/gust thresholds,
  rain/precipitation policy, forecast horizon, hysteresis, persistence, and
  clear delay.
- Outdoor AQ policy: European AQI standard and warning threshold.
- Per-provider base URL, poll interval, request timeout, retry count, stale
  timeout, and enablement. Provider defaults belong to application policy;
  location and station selection belong to installation configuration.

#### 8.3.5 Normalized events and states

- API Components publish `external_observation` with a typed observation:
  `{provider, observation_id, hazard_type, provider_level, measured_values,
  observed_at, valid_from, valid_to, retrieved_at, region_codes, confidence,
  authority_confirmed, source_reference}`.
- API Components publish `external_provider_health` independently of data
  observations.
- `ExternalHazardComponent` maintains a latest-valid observation set keyed by
  provider and observation ID. Repeated retrieval of unchanged input is
  idempotent.
- Normalized hazard state is `clear`, `watch`, `warning`, `severe`, or
  `unavailable`. Provider levels are inputs to policy and are not automatically
  equal to Safety System notification levels.
- Opening state is `open`, `closed`, or `unavailable`. An unavailable contact
  shall not be treated as closed.

**Runtime identifier contract:**

| Fault ID | Safety Mechanism ID | Symptom ID contract | Level |
| --- | --- | --- | ---: |
| `ExternalWeatherExposure` | `sm_ext_weather_exposure` | `ExternalWeatherExposure{HazardId}{OpeningId}` | 2 |
| `OutdoorAirQualityExposure` | `sm_ext_outdoor_air_quality_exposure` | `OutdoorAirQualityExposure{OpeningId}` | 3 |
| `ExternalHazardDataUnavailable` | `sm_ext_provider_unavailable` | `ExternalHazardDataUnavailable{CapabilityId}` | 3 |

Each Safety Mechanism ID occurs in exactly one fault's `related_sms` list.
`ExternalWeatherExposure` aggregates affected hazards and openings;
`OutdoorAirQualityExposure` aggregates affected openings and pollutant/AQI
context; and `ExternalHazardDataUnavailable` aggregates capabilities for which every required
provider is unusable beyond its stale timeout.

#### 8.3.6 Requirements (C-EXT → SYS-SR-EXT-xxx)

**API isolation and normalization**

- **SYS-SR-EXT-001:** Each external API shall be implemented by a separate API
  Component with an independent configuration schema, polling lifecycle,
  cache, diagnostics, and contract tests.
- **SYS-SR-EXT-002:** API Components shall not inherit from `SafetyComponent`
  and shall not publish `symptom` or `fault` events. They shall publish only
  normalized observations and provider-health events.
- **SYS-SR-EXT-003:** Remote polling shall not start in constructors. It shall
  start only after configuration validation, EventBus subscriptions, FaultManager,
  NotificationManager, and MQTT diagnostics are ready.
- **SYS-SR-EXT-004:** Provider payload validation shall be fail-closed for the
  affected capability: unknown enum values, missing timestamps/units, or schema
  changes produce `schema_error` and shall not be interpreted as `clear`.
- **SYS-SR-EXT-005:** One provider failure shall not delay another provider's
  schedule or replace another provider's last valid observation.

**Weather and opening correlation**

- **SYS-SR-EXT-010:** When a configured frost, wind, rain, or storm policy is
  active and a relevant opening is open, C-EXT shall raise or update
  `ExternalWeatherExposure{HazardId}{OpeningId}` through
  `sm_ext_weather_exposure` within `T_ext_decision`.
- **SYS-SR-EXT-011:** Official IMGW warnings shall be applicable only when at
  least one configured TERYT code is present in the warning region set and the
  current time is within its validity interval.
- **SYS-SR-EXT-012:** Forecast-only weather evidence shall be labeled as a
  forecast. It shall not be represented as a local real-time measurement.
- **SYS-SR-EXT-013:** Closing an opening shall clear only that opening's
  prefault after `T_ext_clear`; other affected openings and the underlying
  external hazard state shall remain visible.
- **SYS-SR-EXT-014:** The IMGW provider diagnostic output shall expose every
  current warning returned by the provider with sanitized authority context,
  validity, region codes, and a local-applicability flag. Household safety
  policy shall continue to consume only warnings satisfying SYS-SR-EXT-011.

**Outdoor air quality**

- **SYS-SR-EXT-020:** The Open-Meteo AQ component shall retain the current
  European AQI value, model timestamp, grid coordinates, units, validity, and
  retrieval time for the configured home coordinates.
- **SYS-SR-EXT-021:** Open-Meteo shall be the sole outdoor-air-quality input to
  household exposure policy. Unavailable, malformed, or stale provider data
  shall not be interpreted as positive clear evidence.
- **SYS-SR-EXT-022:** When outdoor AQ policy is active and a relevant opening
  is open, C-EXT shall raise or update
  `OutdoorAirQualityExposure{OpeningId}` through
  `sm_ext_outdoor_air_quality_exposure` and identify the controlling
  AQI/pollutant input.
- **SYS-SR-EXT-023:** While outdoor AQ, damaging wind, storm, or a confirmed
  sheltering policy is active, C-EXT shall expose an advice inhibition for
  `open_external_opening`. C-EXT may filter manual advice. A close command is
  permitted only through SYS-SR-EXT-040 through SYS-SR-EXT-044.

**Recommended-action and confirmed-actuation boundary**

- **SYS-SR-EXT-040:** C-EXT shall register close recommendations for exposure
  symptoms. Windows and ordinary doors shall remain manual actions.
- **SYS-SR-EXT-041:** Every warning shall include hazard type, human-readable
  opening/area names when applicable, observed or forecast value, threshold or
  authority level, validity, source, freshness, and recommended manual action.
- **SYS-SR-EXT-042:** Repeated observations for the same active fault shall
  refresh the existing notification and aggregate newly affected hazards or
  openings without creating duplicate notification tags.
- **SYS-SR-EXT-043:** Clearing shall require positive valid evidence or expiry
  according to provider semantics. Network failure, stale data, or parse error
  shall not clear an active condition.
- **SYS-SR-EXT-044:** Only `cover.brama_garazowa` and `cover.gate`, when bound
  to their configured closed contacts, may be commanded, and only with
  `cover.close_cover` after an authenticated SafetyHome user confirms a current
  one-time proposal. Raw pulse buttons shall not be used.
- **SYS-SR-EXT-045:** Before command execution RecoveryManager shall reject an
  expired, replayed, shadowed, cleared, policy-inhibited, or actuator-mismatched
  proposal. It shall publish executing, confirmed, failed, or timed-out state
  and verify closure from the configured contact.

**Diagnostics and evidence**

- **SYS-SR-EXT-050:** Each API Component shall expose provider health per
  IR-027 through MQTT diagnostics. When every provider required for an enabled
  capability remains unusable beyond its stale timeout, C-EXT shall set
  `ExternalHazardDataUnavailable{CapabilityId}` through
  `sm_ext_provider_unavailable`.
- **SYS-SR-EXT-051:** C-EXT shall emit evidence for each decision containing
  `{rule_id, provider, source_ts, retrieved_at, freshness, values, thresholds,
  opening_states, decision, authority_confirmed, latency_ms}`.
- **SYS-SR-EXT-052:** C-EXT shall publish one normalized external-hazard entity
  containing active hazards, affected openings, provider health summary, and
  the most recent successful evaluation time.

#### 8.3.7 Mapping

- **SG-011:** SYS-SR-EXT-001/010/011/012/013/040/041/042/043/051
- **SG-017:** SYS-SR-EXT-010/012/013/040/041/042/043/051
- **SG-018:** SYS-SR-EXT-010/011/012/013/040/041/042/043/051
- **SG-019:** SYS-SR-EXT-020/021/022/023/040/041/042/043/051
- **SG-003:** SYS-SR-EXT-004/005/043/050/052

#### 8.3.8 Verification

- **Contract tests:** stored sanitized payload fixtures for every API, including
  valid, empty, changed-schema, missing-unit, stale, withdrawn, and malformed
  responses.
- **Unit tests:** threshold/hysteresis/expiry, TERYT filtering, contact
  correlation, multi-opening aggregation, and advice inhibition.
- **Integration tests:** independent polling schedules, timeout/retry isolation,
  EventBus ordering, FaultManager aggregation, same-tag notification refresh,
  MQTT provider diagnostics, and restart followed by immediate provider refresh
  without an intermediate false-clear transition.
- **Negative-actuation tests:** assert no actuator call occurs before valid
  confirmation and no lock, switch, raw pulse button, fan, climate, or
  non-allowlisted cover service is called by C-EXT paths.
- **Failure injection:** WAN loss, HTTP timeout, partial provider outage,
  rate-limit response, clock skew, duplicate warning ID, provider withdrawal,
  and stale data that must not clear an active fault.

---

### 8.4 Safety Doors Component (C-DOOR)

**Scope:** C-DOOR contributes door/gate open-duration detection and warning to
SG-015. It does not determine intrusion, unexpected entry, armed state, lock
integrity, or security-company response; those responsibilities belong to
C-SEC. Diagnostic handling of unavailable inputs supports SG-003.

**Safety Mechanism:** `sm_safety_door_open_timeout`.

#### 8.4.1 Inputs and outputs

- **IR-001 Window/Door Contact** for every configured door or gate.
- An optional Home Assistant condition entity whose configured pass and blocked
  states gate monitoring independently for one door.
- Symptom events for FaultManager aggregation and **OR-020/021** notification
  and dashboard output.
- One diagnostic MQTT sensor per door. C-DOOR registers no recovery action and
  uses no lock, cover, gate, or other actuator output.

#### 8.4.2 Parameters

- Component default `timeout_seconds` and an optional positive per-door
  override.
- Per door: stable door key, `area_id`, contact `entity_id`, and optional
  condition with `entity_id`, non-empty `pass_states`, and non-empty
  `blocked_states`.
- Pass and blocked states are normalized to lowercase and shall be disjoint.

#### 8.4.3 Runtime identifier contract

| Element | Stable ID |
| --- | --- |
| Component | `SafetyDoorsComponent` |
| Safety Mechanism | `sm_safety_door_open_timeout` |
| Per-door symptom | `SafetyDoorOpenTimeout{DoorName}` |
| Aggregated fault | `SafetyDoorOpenTimeout` |
| Fault level | 2 |
| Diagnostic entity | `sensor.safety_door_<door_name>` |
| Recovery actions | None |

#### 8.4.4 Requirements (C-DOOR → SYS-SR-DOOR-xxx)

- **SYS-SR-DOOR-001:** Every configured door or gate shall define `area_id`,
  contact `entity_id`, and a positive `timeout_seconds`; the component default
  shall apply only when the door has no override.
- **SYS-SR-DOOR-002:** C-DOOR shall monitor each configured door independently
  and shall start or resume timing only while the contact is open and the
  optional condition is passing.
- **SYS-SR-DOOR-003:** When a door remains continuously open for at least its
  applicable timeout, C-DOOR shall set
  `SafetyDoorOpenTimeout{DoorName}`.
- **SYS-SR-DOOR-004:** Closing the door shall cancel its pending timer, reset
  elapsed time, and clear its per-door symptom.
- **SYS-SR-DOOR-005:** An optional condition shall contain one monitored entity
  plus non-empty, normalized, disjoint `pass_states` and `blocked_states`. Pass
  states enable monitoring; blocked states cancel timing, reset elapsed time,
  and clear the symptom.
- **SYS-SR-DOOR-006:** An unavailable or unsupported contact or condition state
  shall publish diagnostic state `unavailable`, cancel pending timing, and
  shall neither create a new fault nor clear an already active symptom.
- **SYS-SR-DOOR-007:** When an already-open door becomes eligible for
  monitoring, elapsed time shall start from the later of the door's open
  transition and the condition's pass transition.
- **SYS-SR-DOOR-008:** Each diagnostic entity shall publish `active`,
  `inactive`, `blocked`, or `unavailable` plus door state, source entity,
  timeout, elapsed/remaining time, opening timestamp, condition details,
  `area_id`, and resolved area name.
- **SYS-SR-DOOR-009:** All active per-door symptoms shall aggregate into the
  single level-2 fault `SafetyDoorOpenTimeout`, which shall remain active until
  every related door symptom clears.
- **SYS-SR-DOOR-010:** C-DOOR shall register no recovery action and shall not
  close, lock, unlock, or otherwise actuate a door or gate.
- **SYS-SR-DOOR-011:** C-DOOR shall not infer unauthorized entry, lock
  integrity, or intrusion state; those responsibilities belong to C-SEC.

#### 8.4.5 Installation calibration

| Door key | Area | Timeout | Condition |
| --- | --- | ---: | --- |
| `GarageGate` | `garage` | 180 s | None |
| `ExternalGate` | `frontyard` | 180 s | None |
| `LivingRoomTerraceDoor` | Configured living-room area | 120 s | `sensor.home_monitor_occupancy`: pass `empty`, blocked `occupied` |
| `GarageDoor` | `garage` | 900 s | None |

#### 8.4.6 Mapping and verification

- **SG-015:** SYS-SR-DOOR-001/002/003/004/005/007/009/010/011.
- **SG-003:** SYS-SR-DOOR-006/008.
- **Unit tests:** independent timeouts, restart/reload timing, transition-based
  elapsed time, pass/blocked conditions, unavailable inputs, timer cancellation,
  and stable runtime IDs.
- **Integration tests:** FaultManager aggregation, same-tag notification
  refresh, resolved Home Assistant area names, MQTT diagnostic attributes, and
  zero recovery/actuator calls.

---

### 8.5 Entity Health Monitoring Component (C-ENT)

**Scope:** C-ENT supports SG-003 by detecting failures of Home Assistant
entities whose loss could mask or prevent a safety function. It also exposes a
separate information-only inventory of other Home Assistant entities and
devices. C-ENT observes health and shall not command an entity or actuator.

#### 8.5.1 Monitoring groups

| Group | Stable source code | Membership | Policy owner | Safety effect |
| --- | --- | --- | --- | --- |
| A — Explicit safety entities | `explicit` | Entity IDs selected by the installation because they participate in important external automations or safety dependencies | `user_config` | Failed checks may create symptoms and one C-ENT fault for that entity |
| B — Component dependencies | `component` | Inputs, common entities, and required diagnostic outputs declared by Safety Components or the application core | Owning component or core | Failed checks use the declared fault owner and shall not create duplicate faults |
| C — Entity/device inventory | `inventory` | All Home Assistant entities and devices visible to the frontend connection | Home Assistant metadata; frontend filters | Information only; no safety effect |

An entity may belong to more than one group. Its runtime record shall preserve
all source memberships. Group B policy shall not be weakened by Group A
configuration, and Group C shall remain information-only even when the same
entity is safety-relevant through Group A or B.

#### 8.5.2 Inputs and outputs

- **IR-009 Home Assistant Entity Health** state and registry metadata.
- Group A configuration supplied by system calibration for explicitly selected
  installation dependencies, including health outputs from other applications.
- Group B dependency contracts registered by Safety Components and the
  application core, including every configured `common_entities` binding.
- Per-entity diagnostic MQTT sensors and an aggregate C-ENT summary for Groups
  A and B.
- Symptom events for FaultManager aggregation when C-ENT owns the failure.
- A frontend entity/device inventory obtained through the authenticated Home
  Assistant connection rather than an unbounded MQTT attribute payload.

#### 8.5.3 Checks and calibration

- Availability is mandatory for every Group A and Group B record.
- Freshness is enabled only when the entity contract identifies a trustworthy
  heartbeat or source timestamp and defines `max_silence_seconds`. The check
  evaluates the age of the latest valid confirmation from that source.
- Optional checks are allowed for required state/attribute values, allowed
  values, finite numeric values, numeric range, and rate of change.
- Numeric-range checks shall define at least one inclusive bound.
  Rate-of-change checks shall define a sample window, minimum sample count, and
  at least one permitted rise or fall bound.
- Failure and recovery debounce govern state transitions independently for each
  check result. C-ENT shall apply a startup grace period before evaluating
  freshness.
- For a safety-relevant dependency, availability failure debounce shall not
  exceed the detection budget allocated from its applicable FTTI. When
  freshness is enabled, freshness timeout plus failure debounce shall also fit
  that budget.
- Calibration is per entity for Group A and per stable dependency key for Group
  B. A Group B override may replace debounce, detection budget, and optional
  check thresholds without changing the component-owned entity binding.

#### 8.5.4 Runtime identifier contract

| Element | Stable ID |
| --- | --- |
| Component | `EntityMonitorComponent` |
| Per-entity Safety Mechanism | `sm_entity_health_<entity_key>` |
| Per-check symptom | `EntityHealthFailure{EntityKey}{CheckKey}` |
| Per-entity fault | `EntityHealth{EntityKey}` |
| Fault level | 3 |
| Per-entity diagnostic | `sensor.entity_health_<entity_key>` |
| Aggregate diagnostic | `sensor.entity_monitor_summary` |
| Recovery actions | None |

#### 8.5.5 Requirements (C-ENT → SYS-SR-ENT-xxx)

- **SYS-SR-ENT-001:** The feature shall distinguish the three monitoring groups
  defined in §8.5.1. The backend registry shall maintain Groups A/B, and the
  frontend shall join those records with the Group C inventory while preserving
  every applicable source membership.
- **SYS-SR-ENT-002:** Group A shall contain only explicitly configured entity
  IDs and shall validate every configured check and calibration before safety
  monitoring is enabled.
- **SYS-SR-ENT-003:** Group B shall be derived from validated component and core
  dependency declarations, including all configured common entities, without
  duplicating those entity IDs in installation configuration.
- **SYS-SR-ENT-003A:** System calibration shall support a validated override by
  stable Group B dependency key for failure debounce, recovery debounce,
  detection budget, and optional check thresholds; unknown keys shall invalidate
  startup configuration.
- **SYS-SR-ENT-004:** Availability shall be evaluated for every Group A and
  Group B entity. Freshness shall be evaluated only when the applicable
  calibration declares a trustworthy heartbeat or timestamp source and
  `max_silence_seconds`. For a safety-relevant dependency, freshness timeout
  plus failure debounce shall fit its allocated FTTI detection budget, and the
  availability failure debounce shall independently fit that budget.
- **SYS-SR-ENT-005:** Optional required-value, allowed-values, finite-number,
  numeric-range, and rate-of-change checks shall run only when their complete
  calibration is present and the current input is valid for that check.
- **SYS-SR-ENT-006:** A failed, stale, unavailable, malformed, or unevaluable
  observation shall not provide positive evidence to clear a C-ENT symptom.
- **SYS-SR-ENT-007:** When C-ENT owns a Group A or Group B failure, it shall set
  `EntityHealthFailure{EntityKey}{CheckKey}` after failure debounce and clear it
  only after fresh valid observations pass recovery debounce.
- **SYS-SR-ENT-008:** When an owning component already defines fault semantics
  for a Group B dependency, C-ENT shall expose and aggregate its health without
  creating a duplicate `EntityHealthFailure` symptom.
- **SYS-SR-ENT-009:** All C-ENT-owned check symptoms for one entity shall
  aggregate into that entity's level-3 `EntityHealth{EntityKey}` fault. A
  different unhealthy entity shall have a different fault. The fault shall
  retain every failed check in diagnostic context.
- **SYS-SR-ENT-010:** Group C shall include all entities and devices visible to
  the authenticated Home Assistant frontend connection and support filtering by
  at least domain, device, area, availability, source group, and last-change or
  last-update time.
- **SYS-SR-ENT-011:** Group C data shall not create symptoms, faults,
  notifications, recovery actions, or application-health degradation.
- **SYS-SR-ENT-012:** C-ENT shall publish bounded Group A/B diagnostics and
  shall not copy the complete Group C inventory into MQTT attributes.
- **SYS-SR-ENT-013:** C-ENT shall use Home Assistant friendly names, device
  names, and area names for operator presentation while retaining entity IDs and
  raw state codes as diagnostic data.
- **SYS-SR-ENT-014:** C-ENT shall register no recovery action and shall not call
  a Home Assistant actuator service.

#### 8.5.6 Mapping and verification

- **SG-003:** SYS-SR-ENT-001..009/012/014.
- **Unit tests:** group membership and deduplication, configuration validation,
  startup grace, availability, freshness, optional check validation, failure
  and recovery debounce, fault ownership, stable IDs, and no false clear.
- **Integration tests:** component dependency registration, common-entity
  inclusion, FaultManager aggregation, bounded MQTT diagnostics, frontend
  inventory filtering, and zero recovery/actuator calls.

---

**Other component allocations:** Fire/CO/Gas is owned by C-ALARM, Water Leak by
C-LEAK, Indoor Air Quality by C-AQ, HVAC Health by C-HVAC, intrusion/lock
security by C-SEC, Privacy by C-PRIV, and Network/Platform Health by C-NET.

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
- **NFR‑014 External isolation:** External API calls shall use bounded timeouts and independent schedules; no external call may block the AppDaemon decision path or another provider beyond `T_api_block_max`.
- **NFR‑015 Last-known semantics:** Provider loss shall preserve the last observation with explicit age until its policy expiry; it shall never convert stale data into a false `clear` state.

### 9.3 Security (safety‑relevant)

- **NFR‑020 AuthN/AuthZ:** Administrative actions require **strong auth**; runtime actuation restricted by **RBAC**; audit all privileged operations.
- **NFR‑021 Config integrity:** `backend/app_cfg.yaml` shall pass complete schema,
  component, entity, and area validation before safety mechanisms are enabled.
  A deployment shall hash-verify transferred application and configuration files;
  validation failure shall publish `invalid_cfg` and leave safety mechanisms
  disabled while diagnostics remain available.
- **NFR‑022 Secrets handling:** Credentials stored via platform secrets; never in evidence logs.
- **NFR‑023 Network posture:** Prefer **local control paths** for life‑safety; cloud paths treated as best‑effort.

### 9.4 Maintainability & Modularity

- **NFR‑030 Component isolation:** Safety components (C‑TEMP, C‑ALARM, …) **shall** expose clear inputs/outputs and not share mutable state (except via evidence/metrics).
- **NFR‑031 Freedom from interference:** Non‑safety automations **shall not** preempt or delay safety decisions/actuations beyond **T_fi_max**.
- **NFR‑032 Feature flags:** New mechanisms (e.g., forecasting) start in **shadow mode** and only activate when **C_target** is met.
- **NFR‑033 Provider isolation:** Each external API Component shall be replaceable and testable without importing provider-specific schemas into C-EXT or other API Components.

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

## 11 System Parameter Reference

> Reference values are non-binding system policy inputs. Exact validated keys
> for C-TEMP, C-EXT, and C-DOOR are defined in §8.2.3, the C-EXT architecture,
> and §8.4.2 respectively.

| Name                     | Description                                  | Reference Value |
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
| **N_retry**              | Retries for actuation/notify                 | 1–3              |
| **T_cooldown**           | Cooldown between retries                     | 30–120 s         |
| **T_watchdog**           | Loop stall detection interval                | 2–5 s            |
| **T_evidence_retention** | Evidence retention period                    | 30–90 days       |
| **WAN_loss_threshold**   | Condition to enter Local‑Only (M4)           | WAN link = down  |
| **SMS_enabled**          | Enable SMS/cellular fallback                 | false            |
| **SMS_max_retries**      | Max SMS send retries                         | 3                |
| **SMS_cooldown_s**       | Cooldown between SMS retries                 | 60 s             |
| **T_ext_decision**       | External observation/contact decision budget | ≤ 1 s            |
| **T_ext_clear**          | Stable positive evidence before exposure clear | 2–10 min       |
| **T_api_block_max**      | Maximum blocking time of one provider call   | ≤ 10 s           |
| **T_poll_weather**       | Open-Meteo weather poll interval             | 10 min           |
| **T_poll_imgw**          | IMGW warnings poll interval                  | 5 min            |
| **T_poll_aq_model**      | Open-Meteo current AQ model poll interval    | 30 min           |
| **T_stale_weather**      | Weather capability stale timeout             | 20 min           |
| **T_stale_warning**      | Official weather warning provider stale timeout | 15 min        |
| **T_stale_aq**           | Outdoor AQ capability stale timeout          | 45 min           |
| **T_frost_watch**        | Configurable external frost watch threshold  | 2 °C             |
| **T_frost_warning**      | Configurable external frost warning threshold | 0 °C            |
| **V_gust_watch**         | Configurable wind-gust watch threshold       | 15 m/s           |
| **V_gust_warning**       | Configurable wind-gust warning threshold     | 20 m/s           |

_All deployable parameter bindings live under `SafetyFunctions.app_config` or
`SafetyFunctions.user_config` in `backend/app_cfg.yaml` (see §4.5). A parameter
shall not affect runtime behavior until its owning component defines and
validates the corresponding configuration key._
