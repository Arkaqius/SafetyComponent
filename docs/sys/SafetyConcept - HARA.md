# ISO 26262 Inspired Safety Strategy for Home Automation Systems

## 1. Hazard analysis and risk assessment

### 1.1 Hazard identification

This process identifies and analyzes potential hazards to the home automation system and its occupants.
By assessing the system, components, and external factors, all hazards are identified for a comprehensive understanding of risks.
This involves examining security vulnerabilities, safety concerns, environmental factors, and system malfunctions.
Identified hazards inform risk assessment and guide the development of safety measures.

---

#### 1.1.1 Identified hazards

---

**Unauthorized Access:**

This could occur if a door or window is left open or unlocked, or if a security system is disabled.

**Fire:**

This could be caused by a malfunctioning device, such as a heater, stove, or electrical equipment.

**Gas Leak:**

Gas appliances could leak, leading to potential poisoning or explosion.

**Carbon Monoxide Poisoning:**

This is another risk associated with gas appliances, particularly if they are not properly
ventilated.

**Water Leak/Flood:**

This could occur if a pipe bursts or a faucet is left running.

**Electrical Shock:**

This could be caused by a faulty device, or by water coming into contact with electrical equipment.

**Poor Air Quality:**

This could be caused by a lack of ventilation, leading to a buildup of pollutants or allergens.

**Loss of Heating/Cooling:**

This could occur if the HVAC system fails, leading to uncomfortable or even dangerous indoor temperatures.
For heating, failure can occur at any stage between room heat need, controller
request, boiler response, and heat distribution. A running controller or an
available temperature entity alone does not establish delivery of heat.

**Failure of Safety or Monitoring Devices:**

Devices like smoke detectors, CO detectors, or security cameras could fail to operate correctly.

**Privacy Invasion:**

Unauthorized access to the system could lead to privacy concerns, such as surveillance through security cameras.

**System Failure:**

A failure in the home automation system itself could lead to various problems, such as lights not working, doors not unlocking, etc.

**Unsafe Cold Exposure:**

This can occur if a room's temperature falls below the safe threshold for the situation or occupants. For example, the bathroom temperature might need to be at least 22°C during a child's bath.

**Unsafe Heat Exposure:**

Similarly, a room's temperature could rise above the safe threshold for the situation or occupants. For example, the living room might become uncomfortably or unsafely hot during a summer heatwave if the cooling system isn't functioning properly.

**Rain Entering Window:**

This hazard arises when rain enters through an open window, potentially causing water damage to the home's interior and electrical systems. The system monitors weather and warns residents; automatic closure is outside the scope of External Hazard Monitoring.

**Frost Exposure Through Openings:**

An external door or window left open during frost can cause rapid heat loss,
localized freezing, increased energy consumption, and in extreme cases damage
to water-bearing installations. This is distinct from unsafe occupant cold
exposure because the initiating condition is an external hazard combined with
an open building aperture.

**Wind Damage to Openings:**

Strong wind or gusts can slam or damage an open window or door and can carry
rain or debris into the building. Forecast wind alone is advisory; an official
warning or current/forecast gust threshold combined with an open aperture
creates the monitored exposure condition.

**Outdoor Air Pollution Entering the Home:**

Opening windows or external doors while outdoor particulate or gaseous
pollution is elevated can worsen indoor air quality and can conflict with
otherwise valid ventilation advice from indoor temperature or air-quality
mechanisms.

---

### 1.2 Hazards assessment and risk classification

This process evaluates identified hazards based on severity, exposure, and controllability.
By quantifying these factors and calculating risk scores, hazards are prioritized.
The assigned priorities guide the development of safety measures and risk mitigation strategies.

Based on the hazard assessment, each identified hazard is assigned a risk level. This risk level is typically determined by factors such as the potential severity of the hazard, the likelihood of the hazard occurring, and the ability of the user or system to control the hazard.

---

#### 1.2.1 Definitions

**Severity** refers to the potential harm that could be caused by the hazard. High severity hazards could cause serious harm, such as injury or significant property damage, while medium severity hazards might cause discomfort or minor damage.

**Exposure** refers to the likelihood of the hazard occurring. High exposure hazards could occur regularly, while medium exposure hazards might only occur occasionally.

**Controllability** refers to the user's ability to prevent or mitigate the hazard. High controllability hazards can be easily managed by the user, while medium controllability hazards might require more effort or specialized knowledge to manage.

---

#### 1.2.2 Numerical values

High=3, Medium=2, and Low=1 for _Severity_, _Exposure_  
High=1, Medium=2, and Low=3 for _Controllability_

---

#### 1.2.3 Formula Risk

Risk score = (2 x _Severity_) x _Exposure_ x _Controllability_ to calculate risk.

---

#### 1.2.4 Categories

**Level 1:** High Risk (Risk score 24 and above)  
**Level 2:** Medium Risk (Risk score between 12 and 23)  
**Level 3:** Low Risk (Risk score between 6 and 11)  
**Level 4:** Very Low Risk (Risk score 5 or below)

---

#### 1.2.5 Risk assessment rules

**Severity:**  
_High_: These hazards pose immediate threats to health or life. They require instant action to mitigate. Examples include a fire, gas leak, or carbon monoxide poisoning.

_Medium_: These hazards could lead to potential costs if not addressed promptly. They might not directly threaten health or life but can cause significant damage or inconvenience. For instance, unauthorized access could lead to theft, while a water leak could cause property damage.

_Low_: These hazards might cause minor costs if repeated over time, or could potentially impact health if the exposure is sustained or repeated. For example, poor air quality might not pose a direct threat but can lead to health issues over time. Similarly, a slight loss of heating or cooling might be uncomfortable but is not immediately dangerous.

**Exposure:**  
_Low:_ These hazards are very unlikely to occur. There might be very specific or rare conditions that could lead to these hazards, but under normal circumstances, the chances are minimal.

_Medium:_ These hazards are possible under certain circumstances. They might not happen regularly, but there are known situations or conditions where these hazards could materialize.

_High:_ These hazards occur often or under a wide range of common conditions. They are part of the routine or daily operation and therefore have a higher likelihood of happening.

**Controllability:**  
_Low:_ These hazards are beyond the control of the residents or can only be mitigated in a limited way. They often require the involvement of specialists or emergency services to manage. For example, a gas leak would be considered a low controllability hazard, as it requires professional assistance to mitigate.

_Medium:_ Residents can mitigate these hazards, but it may take time and the recovery may not be complete. These are situations that may not be easily managed remotely. For example, a water leak could be considered a medium controllability hazard, as a resident could potentially stop the leak, but may not be able to repair the damage without professional help.

_High:_ These hazards can be easily mitigated if residents are notified in time, and many of these situations can be managed remotely. For instance, an open window could be considered a high controllability hazard, as it can be simply closed if a resident is notified and still in the house, or potentially even remotely via an automated system.

---

#### 1.2.6 Risk assessment table

| Hazard                    | Severity   | Exposure   | Controllability | Risk Score     | Level   |
| ------------------------- | ---------- | ---------- | --------------- | -------------- | ------- |
| Unauthorized Access       | High (3)   | Medium (2) | Low (3)         | (2x3)x2x3 = 36 | Level 1 |
| Cybersecurity             | High (3)   | High (3)   | High (1)        | (2x3)x3x1 = 18 | Level 2 |
| Fire                      | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak                  | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Carbon Monoxide Poisoning | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Electrical Shock          | High (3)   | Medium (2) | Low (3)         | (2x3)x2x3 = 36 | Level 1 |
| Poor Air Quality          | Low (1)    | High (3)   | Medium (2)      | (2x1)x3x2 = 12 | Level 3 |
| Unsafe Cold Exposure      | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| Unsafe Heat Exposure      | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| System Failure            | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood          | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| Loss of Heating/Cooling   | Medium (2) | Low (1)    | Low (3)         | (2x2)x1x3 = 12 | Level 3 |
| Privacy Invasion          | Medium (2) | Medium (2) | Low (3)         | (2x2)x2x3 = 24 | Level 1 |
| Rain Entering Window      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| Frost Exposure Through Openings | Medium (2) | Medium (2) | High (1) | (2x2)x2x1 = 8 | Level 3 |
| Wind Damage to Openings   | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| Outdoor Air Pollution Ingress | Low (1) | High (3) | High (1)       | (2x1)x3x1 = 6  | Level 3 |

> Life-threatening hazards (Fire, Gas Leak, CO Poisoning, Electrical Shock) should never drop below Level 2 after mitigation, even if the formula suggests Level 3 or 4.  
> Certainly, it's important to note that the initial risk assessment you have conducted takes into consideration the basic safety measures that are commonly found in homes, even without the presence of a home automation system. These traditional safety measures form the baseline upon which the home automation system's additional safety features are built. (ie. RCD, door locks or manual window locks)

---

### 1.3 Safety goals

#### 1.3.1 Unauthorized Access

- The system shall continuously monitor for indications of unauthorized access or unexpected movement when the home is declared unoccupied.
- The system shall immediately issue alerts to the occupants upon detection of unauthorized access or unexpected movement.
- The system shall communicate an alert signal to a pre-defined security company upon detection of unauthorized access or unexpected movement.
- The system shall monitor configured doors and gates for continuous open
  duration under an optional installation-defined condition such as household
  occupancy.
- The system shall warn occupants when a configured door or gate remains open
  beyond its applicable timeout; this monitoring shall not automatically close
  or lock the opening.
- Open-duration monitoring alone shall not be treated as evidence of intrusion,
  unexpected entry, or lock integrity.
- The system shall ascertain the closure of critical windows in the absence of occupants or presence of minors.
- The system shall ensure external doors are locked when the house is unoccupied or all occupants are asleep.
- The system shall ensure critical windows are closed when the house is unoccupied or all occupants are asleep.

#### 1.3.2 Cybersecurity

- The system shall enforce secure authentication (multi-factor where possible) for all users and administrators.
- The system shall ensure all data in transit and at rest is encrypted using industry-standard protocols.
- The system shall perform regular integrity checks and vulnerability scans.
- The system shall monitor for suspicious login attempts and unusual network activity, alerting administrators of potential breaches.
- The system shall provide automatic security updates and patches to all connected components.
- The system shall implement role-based access control to limit exposure of sensitive functions.
- The system shall maintain audit logs for all administrative and remote access actions.

#### 1.3.3 Fire

- The system shall actively detect the presence of smoke.
- A valid smoke-detector alarm shall independently trigger an L1 notification
  through `InternalEnvironmentalHazardMonitorComponent`; normal readings from
  other detectors or air-quality sensors shall not suppress it.
- The system shall promptly alert the occupants in the event of a fire.
- The system shall schedule and issue reminders for maintenance of fire sensors.
- The system shall unlock external doors to expedite evacuation in case of fire.

#### 1.3.4 Gas Leak

- The system shall alert the occupants promptly upon detection of a gas leak.
- The system shall automatically disengage the main gas supply when a gas leak is detected.
- Flammable-gas detection shall be distinct from carbon monoxide, CO2 and VOC
  measurements. The internal monitor shall report the detector's alarm without
  controlling ventilation, gas valves, relays or ordinary lights. Gas cutoff
  and any safe ventilation response shall have a separate installation-approved
  emergency-response allocation; the monitoring allocation does not execute it.
- The system shall schedule and issue reminders for maintenance of gas sensors.

#### 1.3.5 Carbon Monoxide Poisoning

- The system shall alert occupants when hazardous levels of carbon monoxide are detected.
- The internal monitor shall propagate the CO detector's asserted alarm without
  replacing its manufacturer concentration/time alarm logic with a generic
  software threshold. An absent numeric CO measurement shall not inhibit a
  valid binary CO alarm.
- The system shall schedule and issue reminders for maintenance of CO sensors.

#### 1.3.6 Water Leak/Flood

- The system shall promptly alert the occupants upon detecting a leak.
- The system shall disengage the water supply upon detection of a leak.

#### 1.3.7 Electrical Shock

- The system shall schedule and notify for maintenance of the Residual Current Device (RCD).

#### 1.3.8 Poor Air Quality

- The system shall promptly notify residents when the air quality within the home deteriorates below a predefined standard.
- The system shall anticipate potential deterioration of indoor air quality and take preventive actions.
- The system shall interface with air purifiers within the home to maintain air quality.
- Indoor PM2.5 shall be monitored independently from smoke, flammable gas and CO
  alarms. Concentration thresholds shall identify their units, averaging period,
  coverage, persistence and recovery hysteresis. Long-term exposure guidelines
  shall not be treated as instantaneous emergency alarm thresholds.
- Purification or ventilation advice shall account for concurrent life-safety
  incidents and outdoor hazards. The internal monitor shall not actuate an air
  purifier, fan or opening; mitigation execution shall be separately allocated.

#### 1.3.8.1 Internal environmental hazard monitoring allocation

`InternalEnvironmentalHazardMonitorComponent` shall implement the logical
C-ALARM allocation for smoke, flammable gas and CO, and the indoor PM2.5 subset
of C-AQ. It shall create independent per-detector symptoms and aggregate faults
per hazard. Monitoring loss shall be separate from a detected environmental
hazard. These functions support SG-003 and SG-005..008 without claiming that
Home Assistant replaces an autonomous alarm or its native protection.

| Scenario | Hazardous sequence | Required supervision |
| --- | --- | --- |
| IEHM-H01 | Smoke is detected but transport, processing or a quiet mode delays the warning | Propagate one valid alarm immediately; preserve L1 priority and all contributing detectors |
| IEHM-H02 | Flammable gas is detected and generic automation switches electrical equipment | Emit an L1 gas-specific warning; prohibit unapproved switching, including through shared notification adapters |
| IEHM-H03 | CO is detected but software waits for a numeric threshold or confuses CO with CO2 | Use the detector's independent alarm output; retain distinct pollutant and hazard identities |
| IEHM-H04 | Elevated indoor PM2.5 is missed, averaged across missing data, or confused with a fire alarm | Use validated time-aware concentration policy with coverage and separate fault identity; do not infer smoke or CO from PM2.5 |
| IEHM-H05 | Detector malfunction, silence, warmup or missing input is reported as no hazard | Expose supervision loss and affected coverage; never treat invalid input as positive clear evidence |
| IEHM-H06 | A second healthy sensor, acknowledgement, restart or brief clear closes an active incident | Preserve per-detector latches and incident state; require positive recovery evidence for every active contributor |
| IEHM-H07 | Generic ventilation/purification advice conflicts with fire, gas, CO or external hazards | Apply hazard-specific advice and output eligibility; life-safety incidents take precedence over comfort/PM guidance |

- Binary alarm processing shall bypass slow availability debounce and PM
  averaging. Ten-second interface response budgets shall account for reception,
  processing and notification, while detector intrinsic response to physical
  exposure shall remain a separately verified assumption.
- A fresh valid alarm shall remain actionable despite a simultaneous detector
  trouble or battery warning. One detector shall suffice; healthy peers shall
  not vote away another detector's alarm.
- Alarm clearance shall mean only that the applicable detector/concentration
  condition has cleared. It shall not authorize re-entry or assert that a room
  is safe. Acknowledgement shall not clear the hazard or remotely silence/reset
  its detector.
- Automatic annunciation shall use only outputs assessed for the specific
  hazard and installation. Unapproved ordinary lights, fans or relays shall
  not be switched on, off or restored during a flammable-gas incident, including
  unresolved incidents awaiting fresh evidence.
- Gas switching inhibition shall remain independently latched after detector
  clearance until a reviewed installation policy accepts explicit authorized
  output-clearance evidence; alarm HEAL alone shall not release it.

Traceability: [SYS section 8.7](<SafetyConcept - SYS.md#87-internal-environmental-hazard-monitoring-c-alarm-and-c-aq>),
[SSRD section 4.11](<SafetyComponent - SSRD.md#411-internal-environmental-hazard-monitoring>),
and [Internal Environmental Hazard Monitoring architecture](<../features/Internal Environmental Hazard Monitoring - Architecture.md>).

#### 1.3.9 Unsafe Cold Exposure

- The system shall alert the occupants if the temperature drops below a certain threshold.
- The system shall interface with the home heating system to mitigate cold exposure hazards.
- The system shall perform proactive actions and issue user notifications based on available data to prevent cold exposure and maintain comfortable indoor conditions.

#### 1.3.10 Unsafe Heat Exposure

- The system shall alert the occupants if the temperature rises above a certain threshold.
- The system shall interface with the home heating system and AC to mitigate heat exposure hazards.
- The system shall take proactive actions and issue notifications to prevent heat exposure and maintain comfortable conditions.

#### 1.3.11 System Failure

- The system shall consistently monitor the activity of all sensors and actuators to detect timeouts and failures.
- The system shall monitor explicitly selected safety-relevant Home Assistant
  entities and every entity dependency declared by a Safety Component, including
  shared entities consumed across components.
- The system shall distinguish safety-relevant entity-health failures from an
  informational inventory of other Home Assistant entities and devices.
- The system shall remind the users about updates periodically.
- The system shall provide a backup power supply to ensure continuous operation in the event of a power outage.
- The system shall perform regular self-checks or diagnostics to identify and alert users to potential failures or malfunctions.
- The system shall monitor network connectivity and performance, including Ethernet port status, system latency, and packet loss.
- The system shall monitor the health of the Zigbee network.
- The system shall integrate with the existing Home Automation (HA) fault manager.

#### 1.3.12 Loss of Heating/Cooling

- The system shall continuously monitor the current flow temperature and compare it against the expected temperature range to detect any potential heater errors or anomalies.
- The system shall provide proactive measures such as alerts, redundancy mechanisms, or automated failover strategies to maintain safe temperatures.

Heating supervision shall be allocated to `HeatingSystemMonitorComponent`
(C-HVAC), with entity input quality supplied by C-ENT and independent room
temperature hazard detection retained by C-TEMP. The heating allocation supports
SG-010 and SG-012 and shall not replace the shorter response requirements for
room cold/heat exposure or sensor failures. Cooling-system supervision remains
outside this heating-specific allocation.

| Scenario | Hazardous sequence / operating context | Required monitoring and response |
| --- | --- | --- |
| HSM-H01 | Room heating is permitted and needed, but controller failure prevents a heat request | Compare independently established room need with controller demand; warn about missing demand without using boiler activity as the gate |
| HSM-H02 | A valid heat request is present, but the boiler does not start or delivers insufficient heat | Observe bounded startup, flow-temperature rise, and tracking of the requested flow temperature; issue a loss-of-heating warning |
| HSM-H03 | Boiler communication, input quality, or interpretation is lost while heating cannot be assessed | Report loss of supervision, retain active incidents, and inhibit only conclusions that require the lost evidence |
| HSM-H04 | Burner/pump operation or the flow/return response suggests impaired heat distribution | Detect mode-dependent inconsistencies and sustained room cooling; report observed effects without asserting an unmeasured mechanical cause |
| HSM-H05 | Flow temperature exceeds a mode-specific or manufacturer absolute limit | Distinguish central heating, domestic hot water (DHW), hysteresis, and overrun; report excess temperature independently of heating-demand gating |
| HSM-H06 | Normal standby, DHW priority, anti-cycle inhibition, or pump overrun is misclassified, or prolonged inhibition conceals heating loss | Recognize valid operating phases, bound permissible inhibition, and preserve a total heating-loss deadline |
| HSM-H07 | Restart, stale observations, acknowledgement, or vanished demand falsely resolves an existing incident | Preserve incident identity and deadlines; require fresh rule-specific recovery evidence before HEAL |

- Heating supervision shall distinguish room heat need, controller request,
  boiler operating response, and room heat delivery using independently
  identified inputs and installation-specific applicability conditions.
- C-HVAC shall observe and notify; it shall not reset the boiler, alter
  setpoints, force pumps, bypass interlocks, or register heating recovery
  actions. Any system-level backup/failover strategy shall have a separate
  explicit safety allocation and authorization. An alert shall not be claimed
  as proof that room temperature has recovered.
- Entity quality failures shall remain visible per entity while C-HVAC
  correlates their impact into heating incidents without duplicate C-ENT
  notifications for the same owned failure.
- Manufacturer thermal limits, hydraulic configuration, operating modes, and
  calibrated timing shall constrain heating checks. Diagnostics such as
  short cycling shall not be used as substitutes for heating-loss detection.
- HSM-H05 shall produce an L2 excess-temperature warning using a reviewed
  equipment-specific allocation `HSM-H05/<EquipmentProfileKey>` that records
  thermal limits, maximum response time and supporting manufacturer/hydraulic
  evidence. It shall not inherit the heating-loss 30-minute budget or the
  occupied-room overheating budget. Native thermal protection shall remain
  independent of this supervisory warning.
- A cleared heating incident shall require evidence of restored capability;
  absent demand or unavailable inputs shall not be positive recovery evidence.
- Boiler telemetry shall not substitute for independent smoke, gas, CO, leak,
  or room-temperature safety monitoring or for the boiler's native protection.

Traceability: [SYS section 8.6](<SafetyConcept - SYS.md#86-heating-system-monitoring-component-c-hvac>),
[SSRD section 4.10](<SafetyComponent - SSRD.md#410-heating-system-monitoring>),
and [Heating System Monitoring architecture](<../features/Heating System Monitoring - Architecture.md>).

#### 1.3.13 Privacy Invasion

- The system shall notify residents when cameras or microphones are accessed outside of expected usage times.
- The system shall log and alert users of any remote access attempts to cameras or microphones.
- The system shall enforce secure authentication and encryption for all audio-visual devices.
- The system shall provide the option to disable or mask cameras/microphones when not in use.

#### 1.3.14 Rain Entering Window

- The system shall monitor weather data and predict potential rain events.
- The system shall alert occupants when windows or external doors are left open during rain, a storm, or an applicable official warning.
- External Hazard Monitoring shall not automatically close an opening. It may
  command an explicitly configured garage or external gate cover only after an
  authenticated resident confirms the current close proposal in SafetyHome.
- The system shall log open/close events for audit and maintenance purposes.

#### 1.3.15 Frost Exposure Through Openings

- The system shall monitor current and forecast external temperature.
- The system shall alert occupants when a configured window or external door is
  open while the frost warning policy is met.
- The alert shall identify the affected openings, current/forecast temperature,
  source, source timestamp, and recommended manual action.
- External Hazard Monitoring shall not actuate windows, ordinary doors, heating,
  or ventilation. Gate closure requires the resident-confirmation boundary.

#### 1.3.16 Wind Damage to Openings

- The system shall monitor current and forecast wind gusts and applicable
  official wind or storm warnings.
- The system shall alert occupants when a configured window or external door is
  open while the wind warning policy is met.
- The alert shall identify the affected openings, gust value or warning level,
  validity interval, source, and recommended manual action.
- External Hazard Monitoring shall not actuate windows, ordinary doors, or
  blinds. An allowlisted gate may close only after resident confirmation and
  shall be verified from its configured contact.

#### 1.3.17 Outdoor Air Pollution Ingress

- The system shall monitor current outdoor air quality using
  independent provider inputs.
- The system shall alert occupants when a configured window or external door is
  open while outdoor air quality exceeds the configured policy threshold.
- Outdoor pollution shall inhibit conflicting manual advice to open windows;
  External Hazard Monitoring shall not control ventilation or air purifiers.
- Any garage or external gate close proposal shall remain non-actuating until a
  resident confirms it in SafetyHome.
- The system shall report the current measurement or model input controlling
  the decision and preserve its provider semantics.

---

### 1.4 Risk Evaluation

In this stage, you compare the risk levels from your risk assessment with your predetermined risk acceptance criteria. Risk acceptance criteria can be defined based on factors such as legal requirements, industry standards, and the risk tolerance of the stakeholders involved.

#### 1.4.1 Priority rules

**Level 1 Risks:** Level 1 must be addressed immediately due to its high severity, high exposure, and low controllability. These risks are the top priority and should be mitigated before moving forward with the implementation. However, if additional measures cannot be implemented, Level 1 risks should be clearly stated.

**High Severity Risks:** Regardless of their exposure or controllability, risks with a high severity level should be next in line for mitigation. These risks can cause significant harm and, therefore, should be addressed promptly to protect the occupants and the property.

**Low Controllability Risks:** After high exposure risks, focus on risks with low controllability. These are risks that occupants have little to no control over and, thus, require an effective mitigation strategy to prevent potential harm.

---

### 1.5 Risk Mitigation

For risks that need further mitigation, you'll need to develop a risk mitigation strategy. This strategy should outline specific actions to reduce the likelihood and/or impact of each risk. The strategy can include a variety of measures such as:

- _Mitigation:_ Reducing the impact or likelihood of the risk. This is often the main focus in the context of home automation systems.
- _Acceptance:_ Acknowledging the risk and preparing contingency plans.
- _Avoidance:_ Changing plans or strategies to entirely avoid the risk.
- _Transfer:_ Shifting the risk to another party, such as purchasing insurance.

#### 1.5.1 Risk assessment after implementing safety goals

| Hazard                    | Severity   | Exposure   | Controllability | Risk Score     | Level   |
| ------------------------- | ---------- | ---------- | --------------- | -------------- | ------- |
| Unauthorized Access       | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Cybersecurity             | High (3)   | Medium (2) | High (1)        | (2x3)x2x1 = 12 | Level 3 |
| Fire                      | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak                  | High (3)   | Low (1)    | Medium (2)      | (2x3)x1x2 = 12 | Level 2 |
| Carbon Monoxide Poisoning | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Electrical Shock          | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Poor Air Quality          | Low (1)    | Medium (2) | High (1)        | (2x1)x2x1 = 4  | Level 4 |
| Unsafe Cold Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 4 |
| Unsafe Heat Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 4 |
| System Failure            | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood          | Medium (2) | Medium (2) | Medium (2)      | (2x2)x2x2 = 16 | Level 3 |
| Loss of Heating/Cooling   | Medium (2) | Low (1)    | Low (3)         | (2x2)x1x3 = 12 | Level 3 |
| Privacy Invasion          | Medium (2) | Low (1)    | Medium (2)      | (2x2)x1x2 = 8  | Level 4 |
| Rain Entering Window      | Medium (2) | Low (1)    | High (1)        | (2x2)x1x1 = 4  | Level 4 |
| Frost Exposure Through Openings | Medium (2) | Low (1) | High (1)     | (2x2)x1x1 = 4  | Level 4 |
| Wind Damage to Openings   | Medium (2) | Low (1)    | High (1)        | (2x2)x1x1 = 4  | Level 4 |
| Outdoor Air Pollution Ingress | Low (1) | Medium (2) | High (1)      | (2x1)x2x1 = 4  | Level 4 |

---

### 1.6 Risk Monitoring

To ensure the effectiveness of mitigation measures and detect emerging risks, the system shall implement continuous risk monitoring across all hazards:

#### 1.6.1 KPIs & Metrics

- Track mean time to detect (MTTD) and mean time to respond (MTTR) for all hazards.
- Monitor number of false alarms vs. true hazard detections.
- Record uptime and availability of all critical safety devices.

#### 1.6.2 Maintenance Intervals

- Schedule regular testing of sensors (smoke, gas, CO, water leak, motion) at least every 6 months.
- Enforce periodic calibration of temperature, humidity, and air quality sensors.
- Verify cybersecurity updates and patches monthly.
- Test system backups and failover power supplies quarterly.

#### 1.6.3 Automated Logging & Alerts

- Maintain detailed logs of hazard detections, mitigation actions, and user responses.
- Provide automated user notifications for overdue maintenance or repeated anomalies.
- Enable secure remote diagnostics and reporting to administrators.

#### 1.6.4 Adaptive Monitoring

- Adjust thresholds dynamically based on user behavior and seasonal/environmental patterns.
- Integrate anomaly detection using machine learning for early identification of new hazards.

#### 1.6.5 Audit & Compliance

- Generate periodic reports for stakeholders on safety performance and risk status.
- Ensure traceability from hazards → safety goals → mitigations → monitoring results.

This monitoring framework applies to **all hazards** (physical, environmental, system, and cybersecurity).

## 2. Traceability Matrix

The following table provides audit-ready traceability from each hazard through safety goals, mitigation strategies, monitoring activities, and risk levels.

| Hazard                  | Safety Goal Ref. | Mitigation Measures                                 | Monitoring Approach                                    | Risk Level (Before) | Risk Level (After) |
| ----------------------- | ---------------- | --------------------------------------------------- | ------------------------------------------------------ | ------------------- | ------------------ |
| Unauthorized Access     | 1.3.1            | Alerts, door/window lock enforcement, security link | Door/lock sensors, intrusion logs, audit reports       | Level 1             | Level 2            |
| Cybersecurity           | 1.3.2            | Authentication, encryption, patches, RBAC           | Network activity logs, vulnerability scans, audit logs | Level 2             | Level 3            |
| Fire\*                  | 1.3.3            | Smoke detection, alerts, evacuation support         | Smoke sensor status, maintenance reminders             | Level 2             | Level 2            |
| Gas Leak\*              | 1.3.4            | Hazard-specific alerts, separately allocated gas cutoff, maintenance | Independent alarm and detector-health diagnostics | Level 2 | Level 2 |
| CO Poisoning\*          | 1.3.5            | CO detection, alerts, maintenance reminders         | CO sensor logs, periodic calibration                   | Level 2             | Level 2            |
| Water Leak/Flood        | 1.3.6            | Automatic water cutoff, alerts                      | Water sensor status, usage logs                        | Level 1             | Level 3            |
| Electrical Shock\*      | 1.3.7            | RCD maintenance reminders                           | RCD self-test logs, inspection intervals               | Level 1             | Level 2            |
| Poor Air Quality        | 1.3.8            | Alerts, interface with purifiers, proactive control | Air quality sensor trends, anomaly detection           | Level 3             | Level 4            |
| Unsafe Cold Exposure    | 1.3.9            | Alerts, heating integration, proactive prevention   | Temperature logs, HVAC health monitoring               | Level 1             | Level 4            |
| Unsafe Heat Exposure    | 1.3.10           | Alerts, cooling integration, proactive prevention   | Temperature logs, AC system diagnostics                | Level 1             | Level 4            |
| System Failure          | 1.3.11           | Backup power, self-checks, diagnostics              | Safety-entity freshness, device uptime, network health monitoring | Level 2             | Level 2            |
| Loss of Heating/Cooling | 1.3.12           | C-HVAC heating warnings; separately allocated backup/failover measures | Need/request/response/delivery, communication, thermal limits, and positive recovery evidence | Level 3 | Level 3 |
| Privacy Invasion        | 1.3.13           | Secure auth/encryption, disable/mask options        | Access logs, AV device monitoring                      | Level 1             | Level 4            |
| Rain Entering Window    | 1.3.14           | Weather-based manual closure warning                 | Weather forecasts/warnings, contact states, event logs | Level 3             | Level 4            |
| Frost Exposure Through Openings | 1.3.15 | Manual closure warning | Weather observations/forecasts, contact states, event logs | Level 3 | Level 4 |
| Wind Damage to Openings | 1.3.16 | Manual closure warning | Gust forecasts, official warnings, contact states | Level 3 | Level 4 |
| Outdoor Air Pollution Ingress | 1.3.17 | Manual closure warning and advice conflict inhibition | Measured/forecast AQ, contact states, event logs | Level 3 | Level 4 |

\* Life-threatening hazards must **not** be reduced below **Level 2** after mitigation, even if formulas suggest a lower level.
