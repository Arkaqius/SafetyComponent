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
- Heating-system supervision by C-HVAC across room heat need, controller
  request, boiler response, and heat delivery, independent of normal heating
  control and of C-TEMP room-temperature hazard decisions.
- Internal environmental monitoring through one component implementing the
  smoke/gas/CO C-ALARM allocation and indoor PM2.5 C-AQ allocation, with separate
  environmental alarm and detector-health state.

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
- Such outputs shall be explicitly approved for the hazard and installation;
  flammable-gas incidents shall not cause unapproved electrical switching,
  including shared-light activation or restoration. Generic severity-based
  output selection shall not bypass this eligibility rule.
- Once required detector bindings are validated, a valid asserted smoke/gas/CO
  alarm shall bypass M1 observation grace and M3/M5 quiet policies. Invalid
  configuration shall still follow the application initialization contract;
  autonomous detector protection remains independent of application readiness.
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

- Dashboard shows the **current level badge** (HAZARD/WARNING/INFO), and each
  active L1–L3 fault card supports **acknowledge** through the authenticated
  Home Assistant connection. Acknowledgement does **not** clear hazards; it
  silences repeats.
- Lights used for signaling should restore to previous state when the event clears.

### 4.5 Configuration sources and generated contract

`backend/config/system_config.yml` owns software policy, calibration, stable
fault-to-Safety-Mechanism mappings, provider lifecycle, MQTT behavior, and
system health checks. The ignored `backend/config/user_config.yml` owns only
the normalized installation registry, component-specific overrides, and
operator choices; the repository contains `user_config.example.yml` as its
public template. `backend/build_app_config.py` resolves system defaults,
component settings, and per-asset overrides into the ignored deployable
`backend/app_cfg.yaml` contract:

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
        - "notify/mobile_app_example_phone"
      default_url: "/"
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
| **SG‑007** | Detect **flammable gas** accumulation; alert and apply separately validated hazard-specific emergency response. | HZ‑GAS‑01 | **ASIL C** | **10 s** | **SS‑Alarm:** L1 + approved emergency response |
| **SG‑008** | Detect **CO** accumulation; alert and provide hazard-specific emergency guidance. | HZ‑CO‑01 | **ASIL C** | **10 s** | **SS‑Alarm:** L1 + approved emergency response |
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
- Alarm and detector-health channels shall have separate typed mappings. A
  valid alarm assertion shall not wait for a second detector, a numeric reading
  or healthy ancillary diagnostics. Startup retained state shall be identified
  as historical/unverified until authoritative source confirmation.
- `SYS-SR-IEHM-003` shall provide the smoke-alarm requirement; the existing
  `SYS‑SR‑120` evidence identifier shall remain a compatibility alias.

**IR-003 Gas Detector**

- Same structure as IR‑002; the equipment profile shall identify the detected
  flammable gas and current alarm semantics. Any OR-003 emergency response shall
  require a separate hazard-specific installation approval; detection shall
  not depend on actuator availability.
- **Latency:** alarm edge **≤ 1 s**.

**IR-004 CO Detector**

- Same structure as IR‑002; **Latency:** alarm edge **≤ 1 s**; bedroom entities flagged for repeat policy.
- CO shall remain distinct from CO2 and combustible-gas channels. Numeric ppm
  telemetry shall supplement, not replace or gate, the detector's alarm output.

**IR-005 Leak Sensor**

- Shall publish `state ∈ {dry, wet}` with debounce supported in SW; **Latency:** wet edge **≤ 1 s**.

**IR-006 Room Climate (Temp/Humidity)**

- **Accuracy:** temp ±0.5 °C; humidity ±3 %RH.
- **Rate:** updates **≥ 0.5 Hz**; **freshness:** drop sample if `age > 90 s`.
- **Semantics:** payload `{ts, value, unit, src}`; reject if unit mismatch.

**IR-007 Indoor Air Quality (CO₂/PM/VOC)**

- **Accuracy:** CO₂ ±(50 ppm + 3%); PM2.5 per sensor spec; VOC relative index.
- **Rate:** **≥ 0.2 Hz**; **freshness:** drop if `age > 120 s`.
- Indoor PM2.5 shall use µg/m³ with identified indoor location, observation and
  receipt times, quality and sensor/profile identity. AQI, PM10, CO2, VOC and
  outdoor model values shall not be accepted as equivalent PM2.5 inputs.
- Concentration averages shall declare their period, actual covered duration,
  maximum gaps and sample provenance; absent data shall not contribute zeros.
  Source-health timeouts shall be tighter where required by SG-003.

**IR-008 Boiler Signals/Measurements**

- Expose flow temperature, burner state, error codes.
- **Rate:** flow temp **≥ 0.2 Hz**; **freshness:** drop if `age > 120 s`.
- **Semantics:** discrete errors as enumerations with code table.
- Every enabled C-HVAC rule shall identify its required signals: flow/return
  temperatures, requested flow temperature, burner/pump state, central heating
  (CH)/domestic hot water (DHW) mode,
  permitted inhibition, and active device codes as applicable. Optional
  maintenance and cycle counters shall declare their own quality contracts.
- Boiler communication shall be evidenced by a trustworthy device-observation
  timestamp or sequence/heartbeat and transport state. HA entity availability,
  unchanged `last_updated`, and a retained `connected` value alone shall not
  establish recent receipt of boiler measurements.
- The adapter shall normalize units, quality, observation time, receipt time,
  source identity, and model-specific codes. Last-error history shall remain
  separate from active error state. Unmapped codes shall be explicitly unknown.
- Room heating permission/need and controller demand shall use independently
  identified inputs, including effective room targets and declared schedule or
  inhibition state; they shall not be inferred solely from burner activity.
- Freshness and total fault-detection budgets shall be distinct. C-HVAC
  calibration shall allocate sampling, timeout, evaluation and debounce so
  detection meets the applicable SG budget; IR-008 does not relax SG-003.

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
- These are separately allocated emergency-response capabilities, not outputs
  of internal environmental monitoring. Eligibility shall be assessed for the
  specific hazard and equipment; a gas alarm shall not automatically energize
  an ordinary fan, light or relay. A source clear shall not automatically reopen
  a gas valve or approve re-entry.

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
- **Submission confirmation:** wait for a bounded Home Assistant service result;
  missing, failed, or timed-out results enter the retry policy.
- **Lifecycle:** a new alarm may alert; same-fault context changes shall refresh
  quietly; shadowing shall use the Companion `clear_notification` command.
- **Persistence:** active, acknowledged, repeated, and queued delivery state
  shall survive AppDaemon reload and restart.

**OR-021 Dashboard Safety Status and Fault Cards**

- Must support **HAZARD/WARNING/INFO** badges and a per-fault **acknowledge**
  action that silences repeats but does not clear the fault.

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
- Thresholds: `default_low_temperature_c` and
  `default_high_temperature_c`, inherited by the installation and exposed as
  `low_temperature_c` and `high_temperature_c` overrides. The
  `forecast_horizon_hours` parameter is fixed in system configuration.
- Direct-mechanism debounce:
  `sm_tc_1_debounce_limit` and `sm_tc_1_reeval_delay_seconds`.
- Forecast-mechanism debounce and derivative sampling:
  `sm_tc_2_debounce_limit`, `sm_tc_2_reeval_delay_seconds`, and
  `sm_tc_2_derivative_sample_minutes`.
- Plausibility bounds: `sm_tc_min_valid_temperature_c`,
  `sm_tc_max_valid_temperature_c`, `sm_tc_max_abs_rate_c_per_min`, and
  `sm_tc_max_forecast_delta_c`.

#### 8.2.4 Runtime identifier contract

| System mechanism | Runtime ID | Positive condition | Symptom ID | Fault ID |
| --- | --- | --- | --- | --- |
| Direct low temperature | `sm_tc_1` | current temperature `< low_temperature_c` | `RiskyTemperature{Room}` | `RiskyTemperature` |
| Forecast low temperature | `sm_tc_2` | projected temperature `< low_temperature_c` | `RiskyTemperature{Room}ForeCast` | `RiskyTemperatureForecast` |
| Direct high temperature | `sm_tc_3` | current temperature `> high_temperature_c` | `RiskyTemperatureHigh{Room}` | `RiskyTemperature` |
| Forecast high temperature | `sm_tc_4` | projected temperature `> high_temperature_c` | `RiskyTemperatureHigh{Room}ForeCast` | `RiskyTemperatureForecast` |

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

- Site identity: latitude and longitude from Home Assistant Core at each App
  start, plus configured timezone, country, and TERYT codes.
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
- **SYS-SR-EXT-044:** Only explicitly configured `cover` entities, when bound
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

Every installation shall define its opening keys, Home Assistant areas, entity
bindings, and safety-door roles in the private `user_config.yml` installation
registry. A safety-door role may inherit the public system timeout, an
installation-wide timeout, or define its own positive timeout. Optional
condition bindings shall define explicit, disjoint pass and blocked states; the
public repository shall not contain bindings or calibration copied from a real
installation.

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

### 8.6 Heating System Monitoring Component (C-HVAC)

**Allocation:** `HeatingSystemMonitorComponent` shall own heating-system
supervision under SG-010 and SG-012, contribute to SG-003 input supervision,
and supply evidence to room cold/heat exposure diagnosis without replacing
C-TEMP. HARA section 1.3.12 defines the stakeholder-level
loss-of-heating/cooling safety goal.
The detailed contract is defined in the
[Heating System Monitoring architecture](<../features/Heating System Monitoring - Architecture.md>).

#### 8.6.1 Boundaries and interfaces

C-HVAC shall consume normalized IR-008 measurements, room need/controller
demand evidence, and C-ENT quality for its declared Group B dependencies.
The EMS-ESP adapter shall own provider/model interpretation and communication
health; C-HVAC shall own household policy and incidents. SmartHeating and the
boiler controller shall retain normal control. C-TEMP shall retain existing
room-temperature mechanisms and faults.

C-HVAC shall publish per-installation phase, supervision coverage, rule
results, heating faults and bounded diagnostic evidence through the existing
fault/MQTT/notification interfaces. It shall not perform boiler, pump, climate,
gas-valve or other heating actuator calls or register recovery actions.

#### 8.6.2 Functional requirements

| ID | Requirement |
| --- | --- |
| SYS-SR-HSM-001 | C-HVAC shall distinguish independent room heat need, controller request, boiler response, and room heat delivery; a failed controller request shall not gate off need-to-request monitoring. |
| SYS-SR-HSM-002 | C-HVAC shall register all enabled-rule inputs as component dependencies with entity identity, owner, purpose, units, quality, freshness source where trustworthy, and failure ownership. Shared inputs shall retain every consumer and its applicable contract. |
| SYS-SR-HSM-003 | The adapter shall normalize telemetry and model-specific current codes separately from historical errors; unknown code meanings and inconsistent signals shall produce explicit interpretation/coverage diagnostics rather than a fabricated healthy or faulty boiler state. |
| SYS-SR-HSM-004 | Operating phase shall be one of `idle`, `starting`, `heating`, `dhw`, `pump_overrun`, `inhibited`, or `unknown`, separate from supervision health and fault lifecycle; phase transitions shall use fresh coherent evidence and bounded mode-specific delays. |
| SYS-SR-HSM-005 | Communication loss, invalid required measurements, or unavailable phase interpretation shall diagnose loss of supervision. C-HVAC-owned failures shall not create duplicate C-ENT faults; only dependent performance checks shall become unevaluable. |
| SYS-SR-HSM-006 | C-HVAC shall detect permitted room heating need without controller demand, and controller demand without boiler response, accounting for effective targets, explicit schedule/inhibition and bounded DHW priority and anti-cycle delays. |
| SYS-SR-HSM-007 | With valid heating demand and suitable operating conditions, C-HVAC shall detect insufficient flow-temperature rise and sustained failure to track the requested flow temperature using calibrated sample coverage, startup allowance, tolerances and durations. |
| SYS-SR-HSM-008 | C-HVAC shall detect configured pump-state and flow/return inconsistencies and sustained room cooling despite requested heat delivery; it shall describe evidence as a suspected distribution problem rather than prove a particular failed mechanical part. |
| SYS-SR-HSM-009 | C-HVAC shall detect excess temperature against validated mode-specific limits and manufacturer absolute limits independently of heating-demand gating for the absolute-limit rule. Normal hysteresis, DHW and overrun shall not be treated as excess CH temperature. Enablement shall require the reviewed `HSM-H05/<EquipmentProfileKey>` thermal response allocation; plausibility checks shall not mask valid dangerous temperatures. |
| SYS-SR-HSM-010 | Active blocking/device faults shall be classified using a versioned manufacturer/model code table; maintenance and short-cycling diagnostics shall remain distinct from current device faults and heating-loss incidents. |
| SYS-SR-HSM-011 | Each rule shall expose applicability, input quality, pending/active/recovering state and reasons. Missing evidence, removed demand, mode changes, acknowledgement and restart shall not positively clear active faults; HEAL shall require fresh rule-specific evidence. |
| SYS-SR-HSM-012 | Detection, decision and notification budgets shall meet SG-003 (60 s for allocated sensor/communication failures) and SG-010/012 (30 min for heating loss). Startup, freshness, evaluation cadence, observation, debounce, allowed inhibition and notification allowance shall be budgeted without double counting parallel intervals; repeated inhibition or restart shall not indefinitely postpone detection. Notification acceptance shall not establish thermal recovery. |
| SYS-SR-HSM-013 | C-HVAC shall preserve active incident IDs, qualifying onset/deadlines and evidence across restart using bounded versioned atomic storage. Untrusted persistence or a clock discontinuity shall expose degraded supervision and shall not reset an active incident into healthy state. |
| SYS-SR-HSM-014 | Each incident shall use stable fault/mechanism identities, retain all contributing symptoms and distinguish observations from inferred causes. Communication recovery shall not clear performance faults; independent room-temperature alarms shall remain eligible. |
| SYS-SR-HSM-015 | SET and HEAL shall include dated evidence, installation/room identity, phase, demand, relevant measurements, thresholds, elapsed duration, code interpretation and recovery evidence. Notification attempts shall preserve configured target/result semantics, quiet updates and bounded history; acceptance by HA shall not be represented as confirmed phone delivery. |
| SYS-SR-HSM-016 | SafetyHome shall display phase, coverage, active faults, failed and unevaluable checks, evidence ages and reason-specific inhibition. History shall correlate SET/HEAL evidence with actual notification attempts. EN/PL/DE presentation shall preserve language-independent raw codes and IDs. |
| SYS-SR-HSM-017 | Software calibration shall own thresholds, timings, code profiles, severities and rule enablement; installation configuration shall own entity/area bindings and equipment identity. Validation shall reject incomplete enabled rules, ambiguous hydraulics/code profiles, invalid recovery bands and timing combinations outside allocated budgets. |
| SYS-SR-HSM-018 | C-HVAC shall be observation-only, with deterministic bounded evaluation and no boiler reset, heating setpoint writes, pump forcing, safety interlock bypass or recovery actions. Any backup/failover function shall require its own allocation and authorization. |

#### 8.6.3 Severity, timing and safe-state contribution

Heating-loss, device-fault and supervision-loss incidents shall contribute L3
warnings. Excess temperature shall contribute L2. Maintenance and cycling shall
contribute L4 information. Native boiler protection and independent C-TEMP,
C-ALARM and C-LEAK decisions shall retain their own authority and severity.

C-HVAC's contribution to SS-4 is explicit degraded supervision/operation and
timely notification with manual guidance. Its timing evidence shall establish
this contribution; it shall not assert that manual intervention or restored
room temperature occurred within the notification deadline. The broader
SG-012 backup/failover objective shall remain separately allocated.

SG-003 supervision paths shall use a tighter timeout than the IR-008 maximum
sample age where required to meet the 60 s total budget. Slow-provider paths
shall expose unmet coverage rather than silently enlarge that budget. The
architecture defines allocation examples and timing tests.

#### 8.6.4 Traceability and verification

- HZ‑HVAC‑01 and HZ‑HVAC‑LOSS‑01 / SG‑010 and SG‑012:
  SYS-SR-HSM-001..018.
- HZ‑SYSTEM‑FAIL‑01 / SG‑003 supervision contribution:
  SYS-SR-HSM-002/003/005/011/012/013.
- Cross-cutting delivery, presentation and boundary: SYS-SR-HSM-015..018.
- Verification shall cover signal/counter normalization, independent need,
  normal phases, prolonged inhibition, false-clear prevention, code profiles,
  transient and sustained failures, timing boundaries, restart/clock faults,
  C-ENT fault ownership, notification correlation and zero heating actuation.

---

### 8.7 Internal Environmental Hazard Monitoring (C-ALARM and C-AQ)

`InternalEnvironmentalHazardMonitorComponent` shall implement smoke,
flammable-gas and CO alarm supervision under C-ALARM and measured indoor PM2.5
supervision under C-AQ. Logical allocations and SG identifiers shall remain
distinct even though they share one component. Other C-AQ pollutants and
outdoor exposure policy shall retain separate scope.

The component shall consume IR-002/003/004/007 and C-ENT dependency quality,
emit symptoms to FaultManager, and supply notification/diagnostic evidence.
It shall observe and notify without registering recovery actions or controlling
detectors, fans, purifiers, valves, openings, locks or HVAC. Shared notification
outputs shall obey the same hazard-specific eligibility boundary.
See the [Internal Environmental Hazard Monitoring architecture](<../features/Internal Environmental Hazard Monitoring - Architecture.md>).

| ID | Requirement |
| --- | --- |
| SYS-SR-IEHM-001 | The component shall keep smoke, flammable gas, CO, indoor PM2.5 and detector health as separate semantic channels, each bound to an identified detector and indoor area. |
| SYS-SR-IEHM-002 | All enabled inputs shall be Group B dependencies with explicit state/unit/quality contracts and compatible fault ownership. An asserted alarm shall not be modeled as a generic required-value failure or suppressed by another sensor's clear state. |
| SYS-SR-IEHM-003 | A fresh valid smoke alarm shall immediately assert its detector symptom and the L1 smoke fault without averaging, multi-detector voting or general availability debounce. |
| SYS-SR-IEHM-004 | A fresh valid flammable-gas alarm shall immediately assert a distinct L1 fault, retain gas identity and use hazard-specific emergency guidance and output eligibility. |
| SYS-SR-IEHM-005 | A fresh valid CO alarm shall immediately assert a distinct L1 fault without substituting generic software ppm thresholds for manufacturer alarm logic. |
| SYS-SR-IEHM-006 | PM2.5 checks shall validate concentration units and input quality, apply declared short-window concentration policy and recovery hysteresis, and optionally report separately defined long-term exposure. Neither PM2.5 nor an AQI shall be interpreted as smoke, CO or flammable gas. |
| SYS-SR-IEHM-007 | Averaging shall be time-aware, bounded and explicit about sample coverage, skew, gaps and source age. Long-term reference values shall retain their averaging periods and shall not become instantaneous emergency thresholds. |
| SYS-SR-IEHM-008 | Detector trouble, expired required heartbeat, missing channels and invalid/saturated measurements shall expose lost or degraded coverage separately from environmental alarms. Valid alarm assertions shall remain actionable despite ancillary battery/trouble faults. |
| SYS-SR-IEHM-009 | A single detector shall suffice to activate its hazard fault; all contributing detector symptoms shall be retained. One detector clearing or going offline shall not clear another detector's active symptom or the aggregate hazard. |
| SYS-SR-IEHM-010 | SET shall persist until fresh authoritative clear evidence satisfies the rule-specific recovery duration. Acknowledgement, unknown/unavailable inputs, removal of a configured detector, restart, hush/test state or receipt of old data shall not constitute HEAL. |
| SYS-SR-IEHM-011 | Binary alarm interface response shall fit the 10 s SG-006/007/008 budget, including reception, component processing and notification allocation; default 10 s transport allowance shall not be added after another 10 s of detection. Intrinsic detector response to physical exposure and absent transport shall remain explicit assurance limits. |
| SYS-SR-IEHM-012 | Required supervision paths shall fit SG-003's 60 s budget and short-window PM response shall fit SG-005's 10 min budget. Sampling, averaging, qualification, scheduler latency, decision and notification shall be included; long-term exposure diagnostics shall not substitute for the short-window path. |
| SYS-SR-IEHM-013 | Active incident identity, contributing symptoms, qualifying evidence, authoritative clear ordering and consumed deadlines shall survive reload/restart in bounded atomic storage. Retained assertions shall be reconciled on startup, reconnect and coverage recovery. Corruption, clock uncertainty or missing state shall produce explicit unknown/degraded supervision rather than an authoritative clear. |
| SYS-SR-IEHM-014 | Alarm, PM exposure, detector health and per-rule evaluability shall be separately visible in SafetyHome. Missing coverage shall not be labeled safe air or no hazard; cleared alarm presentation shall not imply permission to re-enter. |
| SYS-SR-IEHM-015 | SET/HEAL notifications shall carry localizable hazard/detector/area names, timestamps, evidence, thresholds where applicable and incident correlation. Existing raw fault and journal states, bounded per-target attempts and HA-acceptance semantics shall remain unchanged. |
| SYS-SR-IEHM-016 | Hazard-specific advice shall prioritize life safety and avoid generic ventilation/purifier/open-window instructions during smoke/gas/CO incidents or unresolved life-safety evidence. Optional PM ventilation advice shall require compatible current outdoor-hazard policy. |
| SYS-SR-IEHM-017 | Neither the component nor shared notification adapters shall switch unapproved electrical outputs during a flammable-gas incident, including light restoration after another fault clears. A separately persisted switching-inhibition latch shall survive detector HEAL and require explicit authorized clearance under a reviewed installation policy. Native alarms shall remain independent; approved local annunciation shall remain independent of mobile delivery. |
| SYS-SR-IEHM-018 | System policy shall own alarm profiles, calibration, severity, timers, evidence limits and output eligibility; installation configuration shall own detector/entity/area bindings and equipment profile selection. Incomplete or timing-incompatible enabled contracts shall be rejected. |
| SYS-SR-IEHM-019 | User-facing text shall have EN/PL/DE parity, preserving machine IDs and raw states. Simulated fixtures and explicit test reports shall remain distinguishable from live alarms; maintenance mode shall not suppress an unambiguously live alarm. |
| SYS-SR-IEHM-020 | Provider I/O, averaging, storage and delivery shall be isolated from the immediate alarm path, bounded and deterministic; the component shall register no recovery actions or actuator/reset calls. |

The component shall map smoke/gas/CO to L1, short-window PM2.5 hazard to L2,
optional long-term PM exposure to L3 and detector supervision loss to L3.
Fault severity shall not be inferred from a health state or silently reduced
by an unrelated active fault. C-ALARM and C-AQ contributions do not establish
completion of separately allocated ventilation, evacuation or gas cutoff.

HARA HZ‑FIRE‑01 / SG‑006, HZ‑GAS‑01 / SG‑007, HZ‑CO‑01 / SG‑008,
HZ‑AQ‑01 / SG‑005 and HZ‑SYSTEM‑FAIL‑01 / SG‑003 shall trace to
SYS-SR-IEHM-001..020 and SWR-IEHM-001..025.
Verification shall cover immediate independent alarms, source quality,
PM units/windows, multi-detector latches, positive HEAL, restart/time faults,
bounded deadlines, guidance/output conflicts, persistence and notification/UI
contracts as detailed in the feature architecture.

---

### 8.8 Functional Safety and Platform Health Monitoring (C-FSM)

**Scope:** C-FSM supports HARA `HZ‑SYSTEM‑FAIL‑01` / `SG‑003` by supervising
whether the SafetyFunctions application, Home Assistant, and their host can
continue to observe, evaluate, and report safety conditions. It is distinct
from the household hazard state and from C-ENT's per-entity quality checks.
The [Safety Monitoring Responsibility Boundaries architecture](<../features/Safety Monitoring Responsibility Boundaries.md>)
defines monitor ownership and observer placement.

| ID | Requirement |
| --- | --- |
| SYS-SR-FSM-001 | The system shall present hazard/fault state, safety-function coverage, and reporting-channel health separately. `no_faults` shall not assert that all functions were evaluated or that all reporting paths work. |
| SYS-SR-FSM-002 | SafetyFunctions shall expose startup and configuration validity, and the last completed evaluation and result for each enabled Safety Component. Periodic components shall additionally expose their deadline and missed-deadline count; event-driven components shall identify their trigger mode and rely on declared input-health supervision during idle periods. A component with no completed evaluation or an overdue periodic evaluation shall not be presented as healthy. Application and MQTT heartbeats alone shall not establish component coverage. |
| SYS-SR-FSM-003 | In-process checks shall not claim to detect complete loss of SafetyFunctions, Home Assistant, or the host. Such failures require an independent observer and reporting path; when neither is installed, the system shall identify this boundary as uncovered rather than claim continued monitoring. |
| SYS-SR-FSM-004 | The platform monitor shall use validated Home Assistant or Supervisor telemetry for available memory, memory pressure, CPU, disk, swap, host temperature, restart history, and connectivity. The observation shall identify whether it measures the HA host or only an App container; container-only memory shall not be accepted as host-memory evidence. A missing, stale, malformed, or wrong-unit metric shall produce unknown coverage, not positive host-health evidence. |
| SYS-SR-FSM-005 | Sustained insufficient memory available to Home Assistant, confirmed by memory pressure/PSI, shall produce a level-2 platform-health fault after calibrated qualification. Both measurements are required; if either is unsupported or unavailable the rule shall be reported as uncovered, not silently reduced to one signal. Clearing shall require fresh valid recovery evidence beyond a separate hysteresis margin; an isolated high-use sample shall not assert or clear the fault. |
| SYS-SR-FSM-006 | Sustained CPU, storage, swap, and thermal pressure shall be diagnosed separately and correlated with missed safety-evaluation deadlines. Resource pressure alone shall not be presented as proof that a safety decision was missed. |
| SYS-SR-FSM-007 | Confirmed Internet/WAN loss shall create a level-3 network fault, separately from local Home Assistant or MQTT loss and from failure of one cloud provider. Local safety evaluation shall remain available when only the WAN is lost, and outbound delivery shall follow the Local-Only policy in §3 and §4.6. WAN monitoring shall establish reachability, not infer latency or packet-loss quality. |
| SYS-SR-FSM-008 | The system shall monitor update information separately for Home Assistant Core, Operating System, Supervisor, and the SafetyComponent App when their update sources are available, retaining installed/offered versions, observation time, and source freshness. A confirmed available update shall be level-4 informational and shall not by itself mean that the running safety function has failed; monitoring shall not install an update or restart a service. |
| SYS-SR-FSM-009 | A low battery in a still-functioning remote device shall be a level-4 informational maintenance condition, associated with one device identity even when several battery entities represent it. An unavailable safety input shall retain the severity and owner of its separate coverage fault; battery status shall neither suppress nor clear that fault. |
| SYS-SR-FSM-010 | Each underlying failure shall have one fault owner. C-ENT shall retain entity-quality diagnostics and its existing per-entity faults; C-FSM shall own qualified platform and maintenance policy without duplicating a component-owned symptom. |
| SYS-SR-FSM-011 | System configuration shall own thresholds, qualification and recovery timing, severity, freshness, and fault policy; installation configuration shall own site-specific source bindings and exclusions. Invalid configuration bindings shall be rejected before enabling the affected contract. Missing or incompatible runtime sources shall be visibly marked as uncovered, never silently reported healthy or used to disable unrelated safety mechanisms. |
| SYS-SR-FSM-012 | Platform and maintenance monitors shall be observation-only: no restart, update installation, device control, or other recovery action shall be registered without a separately assessed policy. Diagnostics and user-facing text shall preserve stable machine codes and equivalent EN/PL/DE meaning. |
| SYS-SR-FSM-013 | The system shall present notification-route health and recovery-effect evidence separately from safety decisions. Home Assistant service acceptance shall not be described as delivery to a physical recipient, and an issued actuator command shall not be described as an achieved effect without the owning component's postcondition evidence. C-FSM shall aggregate these results without duplicating the notification or recovery owner's fault. |
| SYS-SR-FSM-014 | The system shall track due dates and recorded outcomes of periodic tests for smoke, flammable-gas, and carbon-monoxide detectors. A test shall count as completed only after a device-reported result or an explicit operator attestation; absence of an alarm is not test evidence. An overdue or failed test shall be visible as a maintenance condition without suppressing a live detector alarm. Test intervals and maintenance severity shall be system policy, while detector binding and operator attestation are installation data. |

C-NET remains the network/connectivity subdomain of C-FSM. C-ENT remains the
quality owner for declared Home Assistant input entities, including C-FSM's
telemetry dependencies where applicable. An unavailable safety input can coexist
with a host-resource or battery condition; neither state implies that a
household hazard has cleared.

---

**Other component allocations:** Water Leak is owned by C-LEAK; C-AQ retains
indoor-air-quality responsibilities beyond the PM2.5 allocation above;
intrusion/lock security by C-SEC, and Privacy by C-PRIV.

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
