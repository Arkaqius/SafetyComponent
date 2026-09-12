# ISO 26262 Inspired Safety Strategy for Home Automation Systems

## 1. Hazard analysis and risk assessment

### 1.1 Hazard identification

This process identifies and analyzes potential hazards to the home automation system and its occupants.
By assessing the system, components, and external factors, all hazards are identified for a comprehensive understanding of risks.
This involves examining security vulnerabilities, safety concerns, environmental factors, and system malfunctions.
Identified hazards inform risk assessment and guide the development of safety measures.

This document defines hazards, risk classifications, and stakeholder-level
safety goals. Component allocations, interface contracts, algorithms, runtime
identifiers, and software behavior are refined in the SYS, SSRD, and feature
architecture documents.

---

#### 1.1.1 Identified hazards

---

**Unauthorized Access (HZ‑UNAUTH‑01):**

This could occur if a door or window is left open or unlocked, or if a security system is disabled.

**Cybersecurity Compromise (HZ‑CYBER‑SPOOF‑01 / HZ‑CYBER‑DENIAL‑01):**

Unauthorized manipulation, denial of service, or loss of trustworthy data could
prevent a safety function from detecting, warning about, or responding to a
hazard.

**Fire (HZ‑FIRE‑01):**

This could be caused by a malfunctioning device, such as a heater, stove, or electrical equipment.

**Gas Leak (HZ‑GAS‑01):**

Gas appliances could leak, leading to potential poisoning or explosion.

**Carbon Monoxide Poisoning (HZ‑CO‑01):**

This is another risk associated with gas appliances, particularly if they are not properly
ventilated.

**Water Leak/Flood (HZ‑WATER‑01):**

This could occur if a pipe bursts or a faucet is left running.

**Electrical Shock (HZ‑ELECT‑01):**

This could be caused by a faulty device, or by water coming into contact with electrical equipment.

**Poor Air Quality (HZ‑AQ‑01):**

This could be caused by a lack of ventilation, leading to a buildup of pollutants or allergens.

**Loss of Heating/Cooling (HZ‑HVAC‑01 / HZ‑HVAC‑LOSS‑01):**

This could occur if the HVAC system fails, leading to uncomfortable or even dangerous indoor temperatures.
A heating or cooling system may appear operational while still failing to
deliver the indoor conditions needed to protect occupants.

**Privacy Invasion (HZ‑PRIV‑01):**

Unauthorized access to the system could lead to privacy concerns, such as surveillance through security cameras.

**System Failure (HZ‑SYSTEM‑FAIL‑01):**

A failure of the home automation system or a safety-relevant monitoring device
could prevent hazard detection, warning, or an authorized protective response.

**Unsafe Cold Exposure (HZ‑UNDERTEMP‑01 / HZ‑UNDERTEMP‑02):**

This can occur if a room's temperature falls below the safe threshold for the situation or occupants. For example, the bathroom temperature might need to be at least 22°C during a child's bath.

**Unsafe Heat Exposure (HZ‑OVERTEMP‑01):**

Similarly, a room's temperature could rise above the safe threshold for the situation or occupants. For example, the living room might become uncomfortably or unsafely hot during a summer heatwave if the cooling system isn't functioning properly.

**Rain Entering Window (HZ‑WEATHER‑01):**

This hazard arises when rain enters through an open window or door, potentially
causing water damage to the home's interior and electrical systems.

**Frost Exposure Through Openings (HZ‑EXT‑FROST‑01):**

An external door or window left open during frost can cause rapid heat loss,
localized freezing, increased energy consumption, and in extreme cases damage
to water-bearing installations. This is distinct from unsafe occupant cold
exposure because the initiating condition is an external hazard combined with
an open building aperture.

**Wind Damage to Openings (HZ‑EXT‑WIND‑01):**

Strong wind or gusts can slam or damage an open window or door and can carry
rain or debris into the building. The hazardous exposure occurs when damaging
wind coincides with an open building aperture.

**Outdoor Air Pollution Entering the Home (HZ‑EXT‑AQ‑01):**

Opening windows or external doors while outdoor particulate or gaseous
pollution is elevated can worsen indoor air quality and can conflict with
otherwise valid ventilation or comfort advice.

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
| Poor Air Quality          | Low (1)    | High (3)   | Medium (2)      | (2x1)x3x2 = 12 | Level 2 |
| Unsafe Cold Exposure      | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| Unsafe Heat Exposure      | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| System Failure            | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood          | Medium (2) | High (3)   | Medium (2)      | (2x2)x3x2 = 24 | Level 1 |
| Loss of Heating/Cooling   | Medium (2) | Low (1)    | Low (3)         | (2x2)x1x3 = 12 | Level 2 |
| Privacy Invasion          | Medium (2) | Medium (2) | Low (3)         | (2x2)x2x3 = 24 | Level 1 |
| Rain Entering Window      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| Frost Exposure Through Openings | Medium (2) | Medium (2) | High (1) | (2x2)x2x1 = 8 | Level 3 |
| Wind Damage to Openings   | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| Outdoor Air Pollution Ingress | Low (1) | High (3) | High (1)       | (2x1)x3x1 = 6  | Level 3 |

> Life-threatening hazards (Fire, Gas Leak, CO Poisoning, Electrical Shock) should never drop below Level 2 after mitigation, even if the formula suggests Level 3 or 4.  
> Certainly, it's important to note that the initial risk assessment you have conducted takes into consideration the basic safety measures that are commonly found in homes, even without the presence of a home automation system. These traditional safety measures form the baseline upon which the home automation system's additional safety features are built. (ie. RCD, door locks or manual window locks)

---

### 1.3 Safety goals

The goals below state the required safety outcomes without allocating them to a
particular component, interface, or implementation. Corresponding system
safety-goal IDs are referenced in the traceability matrix.

Safety monitoring supplements rather than replaces autonomous device
protection. An acknowledgement does not establish that a hazard has cleared or
that re-entry is safe.

#### 1.3.1 Unauthorized Access

- The system shall continuously monitor for indications of unauthorized access or unexpected movement when the home is declared unoccupied.
- The system shall immediately issue alerts to the occupants upon detection of unauthorized access or unexpected movement.
- The system shall support escalation appropriate to the household's security
  policy.
- The system shall warn occupants when an opening or lock state is inconsistent
  with the security needs of the current household situation.
- An opening remaining open shall not by itself be treated as proof of
  intrusion, unexpected entry, or lock integrity.
- Any automatic securing action shall be separately assessed and authorized.

#### 1.3.2 Cybersecurity

- The system shall prevent unauthorized access to or manipulation of
  safety-relevant functions and information.
- The system shall preserve the confidentiality, integrity, authenticity, and
  availability required for safety-relevant operation.
- The system shall detect and report suspected compromise of safety-relevant
  functions.
- Security maintenance and recovery shall not introduce an unacceptable loss of
  safety capability.

#### 1.3.3 Fire

- The system shall actively detect the presence of smoke.
- The system shall promptly alert the occupants in the event of a fire.
- A valid alarm from any smoke detector shall remain effective and shall not be
  suppressed by unrelated normal observations.
- The system shall support maintenance of effective fire detection.
- The system shall support safe evacuation without creating a conflicting
  security hazard.

#### 1.3.4 Gas Leak

- The system shall distinguish a flammable-gas hazard from carbon monoxide and
  general air-quality conditions.
- The system shall alert the occupants promptly upon detection of a gas leak.
- The system shall not initiate a response that could introduce an ignition
  source during a flammable-gas hazard.
- Automatic gas isolation or ventilation shall be used only when the response
  has been separately assessed and approved for the installation.
- The system shall support maintenance of effective gas detection.

#### 1.3.5 Carbon Monoxide Poisoning

- The system shall alert occupants when hazardous levels of carbon monoxide are detected.
- The system shall preserve the authority of a valid carbon-monoxide detector
  alarm and shall not suppress it because supplementary measurements are absent
  or contradictory.
- The system shall support maintenance of effective carbon-monoxide detection.

#### 1.3.6 Water Leak/Flood

- The system shall promptly alert the occupants upon detecting a leak.
- The system shall support separately assessed measures that limit water damage.

#### 1.3.7 Electrical Shock

- The system shall reduce the risk of electrical shock and warn occupants when
  required electrical protection is unavailable or requires attention.

#### 1.3.8 Poor Air Quality

- The system shall promptly notify residents when the air quality within the home deteriorates below a predefined standard.
- The system shall provide timely information that enables occupants to prevent
  or limit harmful indoor air-quality exposure.
- The system shall support separately assessed air-quality mitigation measures.
- The system shall distinguish poor indoor air quality from smoke, flammable
  gas, and carbon-monoxide hazards.
- Air-quality mitigation and advice shall not conflict with a concurrent
  life-safety hazard or unsafe outdoor conditions.

#### 1.3.9 Unsafe Cold Exposure

- The system shall prevent prolonged occupant exposure to unsafe indoor cold.
- The system shall warn occupants early enough to take protective action.
- Any automatic mitigation shall be separately assessed for the installation.

#### 1.3.10 Unsafe Heat Exposure

- The system shall prevent prolonged occupant exposure to unsafe indoor heat.
- The system shall warn occupants early enough to take protective action.
- Any automatic mitigation shall be separately assessed for the installation.

#### 1.3.11 System Failure

- The system shall supervise safety-relevant sensors, actuators, communication,
  and processing functions for loss or degradation.
- Loss of safety monitoring shall be reported separately from the absence of a
  detected hazard.
- The system shall retain an appropriate safe capability during reasonably
  foreseeable power or communication failures.
- The system shall support maintenance and periodic verification of its
  safety-relevant capabilities.

#### 1.3.12 Loss of Heating/Cooling

- The system shall detect loss or degradation of heating or cooling when it
  could result in an unsafe indoor temperature.
- The system shall warn occupants and support separately assessed measures for
  maintaining safe indoor temperatures.
- Loss of monitoring shall not be presented as normal operation, and restoration
  shall not be reported without current evidence of restored capability.

#### 1.3.13 Privacy Invasion

- The system shall prevent unauthorized observation or recording of occupants.
- The system shall notify occupants of suspected unauthorized access to
  audio-visual monitoring functions.
- Occupants shall be able to place audio-visual monitoring functions into an
  appropriate privacy-preserving state.

#### 1.3.14 Rain Entering Window

- The system shall monitor weather data and predict potential rain events.
- The system shall alert occupants when windows or external doors are left open during rain, a storm, or an applicable official warning.
- The system shall not automatically close an ordinary window or door solely
  because of advisory environmental information. Any automatic closure shall
  require a separately assessed and authorized safety response.

#### 1.3.15 Frost Exposure Through Openings

- The system shall monitor current and forecast external temperature.
- The system shall alert occupants when an open window or external door creates
  hazardous frost exposure.
- The warning shall provide enough context for occupants to identify the
  affected opening and take appropriate action.
- Advisory frost information alone shall not authorize automatic control of
  openings, heating, or ventilation.

#### 1.3.16 Wind Damage to Openings

- The system shall monitor current and forecast wind gusts and applicable
  official wind or storm warnings.
- The system shall alert occupants when an open window or external door is
  exposed to damaging wind.
- The warning shall provide enough context for occupants to identify the
  affected opening and take appropriate action.
- Advisory wind information alone shall not authorize automatic control of
  openings or blinds.

#### 1.3.17 Outdoor Air Pollution Ingress

- The system shall monitor current and forecast outdoor air quality.
- The system shall alert occupants when an open window or external door creates
  hazardous outdoor-pollution exposure.
- Outdoor pollution warnings shall prevent conflicting advice to open windows.
- Advisory air-quality information alone shall not authorize automatic control
  of openings, ventilation, or air purifiers.
- The warning shall provide enough context for occupants to understand the
  hazardous condition and take appropriate action.

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
| Cybersecurity             | High (3)   | Medium (2) | High (1)        | (2x3)x2x1 = 12 | Level 2 |
| Fire                      | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak                  | High (3)   | Low (1)    | Medium (2)      | (2x3)x1x2 = 12 | Level 2 |
| Carbon Monoxide Poisoning | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Electrical Shock          | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Poor Air Quality          | Low (1)    | Medium (2) | High (1)        | (2x1)x2x1 = 4  | Level 4 |
| Unsafe Cold Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| Unsafe Heat Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 3 |
| System Failure            | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood          | Medium (2) | Medium (2) | Medium (2)      | (2x2)x2x2 = 16 | Level 2 |
| Loss of Heating/Cooling   | Medium (2) | Low (1)    | Low (3)         | (2x2)x1x3 = 12 | Level 2 |
| Privacy Invasion          | Medium (2) | Low (1)    | Medium (2)      | (2x2)x1x2 = 8  | Level 3 |
| Rain Entering Window      | Medium (2) | Low (1)    | High (1)        | (2x2)x1x1 = 4  | Level 4 |
| Frost Exposure Through Openings | Medium (2) | Low (1) | High (1)     | (2x2)x1x1 = 4  | Level 4 |
| Wind Damage to Openings   | Medium (2) | Low (1)    | High (1)        | (2x2)x1x1 = 4  | Level 4 |
| Outdoor Air Pollution Ingress | Low (1) | Medium (2) | High (1)      | (2x1)x2x1 = 4  | Level 4 |

---

### 1.6 Risk Monitoring

Residual risk and the effectiveness of the safety goals shall be reviewed
periodically using evidence appropriate to each hazard. The review shall cover
warning timeliness, missed and unnecessary warnings, availability of
safety-relevant devices, maintenance status, and the outcomes of authorized
mitigation.

Maintenance, calibration, audit, and evidence-retention intervals shall be
defined in the system and installation requirements. Any change to detection
criteria or automatic mitigation shall undergo a safety-impact assessment
before use. Traceability from hazards through safety goals to verification
evidence shall be maintained throughout the system lifecycle.

## 2. Traceability Matrix

The table assigns stable hazard and safety-goal identifiers shared with the SYS
and SSRD. Detailed mitigation allocation and verification belong to those
documents.

| Hazard | Hazard ID(s) | HARA goal | Safety goal ID(s) | Risk before | Residual risk |
| --- | --- | --- | --- | --- | --- |
| Unauthorized Access | HZ‑UNAUTH‑01 | 1.3.1 | SG‑015 | Level 1 | Level 2 |
| Cybersecurity | HZ‑CYBER‑SPOOF‑01 / HZ‑CYBER‑DENIAL‑01 | 1.3.2 | SG‑016 | Level 2 | Level 2 |
| Fire\* | HZ‑FIRE‑01 | 1.3.3 | SG‑006 | Level 2 | Level 2 |
| Gas Leak\* | HZ‑GAS‑01 | 1.3.4 | SG‑007 | Level 2 | Level 2 |
| CO Poisoning\* | HZ‑CO‑01 | 1.3.5 | SG‑008 | Level 2 | Level 2 |
| Water Leak/Flood | HZ‑WATER‑01 | 1.3.6 | SG‑009 | Level 1 | Level 2 |
| Electrical Shock\* | HZ‑ELECT‑01 | 1.3.7 | SG‑013 | Level 1 | Level 2 |
| Poor Air Quality | HZ‑AQ‑01 | 1.3.8 | SG‑005 | Level 2 | Level 4 |
| Unsafe Cold Exposure | HZ‑UNDERTEMP‑01 / HZ‑UNDERTEMP‑02 | 1.3.9 | SG‑001 / SG‑002 | Level 1 | Level 3 |
| Unsafe Heat Exposure | HZ‑OVERTEMP‑01 | 1.3.10 | SG‑004 | Level 1 | Level 3 |
| System Failure | HZ‑SYSTEM‑FAIL‑01 | 1.3.11 | SG‑003 | Level 2 | Level 2 |
| Loss of Heating/Cooling | HZ‑HVAC‑01 / HZ‑HVAC‑LOSS‑01 | 1.3.12 | SG‑010 / SG‑012 | Level 2 | Level 2 |
| Privacy Invasion | HZ‑PRIV‑01 | 1.3.13 | SG‑014 | Level 1 | Level 3 |
| Rain Entering Window | HZ‑WEATHER‑01 | 1.3.14 | SG‑011 | Level 3 | Level 4 |
| Frost Exposure Through Openings | HZ‑EXT‑FROST‑01 | 1.3.15 | SG‑017 | Level 3 | Level 4 |
| Wind Damage to Openings | HZ‑EXT‑WIND‑01 | 1.3.16 | SG‑018 | Level 3 | Level 4 |
| Outdoor Air Pollution Ingress | HZ‑EXT‑AQ‑01 | 1.3.17 | SG‑019 | Level 3 | Level 4 |

\* Life-threatening hazards must **not** be reduced below **Level 2** after mitigation, even if formulas suggest a lower level.
