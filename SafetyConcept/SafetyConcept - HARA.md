# ISO 26262 Inspired Safety Strategy for Home Automation Systems




## 1. Hazard analysis and risk assessment

### 1.1 Hazard identification:

This process identifies and analyzes potential hazards to the home automation system and its occupants.
By assessing the system, components, and external factors, all hazards are identified for a comprehensive understanding of risks.
This involves examining security vulnerabilities, safety concerns, environmental factors, and system malfunctions.
Identified hazards inform risk assessment and guide the development of safety measures.

---

#### 1.1.1 Identyfied hazards:

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

**Rain Entering Through Open Window:**

This hazard arises when rain enters through an open window, potentially causing water damage to the home's interior and electrical systems. A smart home system can help prevent this by monitoring the weather and alerting residents or automatically closing windows when rain is detected.

---

### 1.2 Hazards assessment and risk classification:

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

#### 1.2.2 Numerical values:

High=3, Medium=2, and Low=1 for _Severity_, _Exposure_  
High=1, Medium=2, and Low=3 for _Controllability_

---


#### 1.2.3 Formula Risk:

Risk_score = (2 x _Severity_) x _Exposure_ x _Controllability_ to calculate risk.

---

#### 1.2.4 Categories:

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
| System cybersecurity      | High (3)   | High (3)   | High (1)        | (2x3)x3x1 = 18 | Level 2 |
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


> Certainly, it's important to note that the initial risk assessment you have conducted takes into consideration the basic safety measures that are commonly found in homes, even without the presence of a home automation system. These traditional safety measures form the baseline upon which the home automation system's additional safety features are built. (ie. RCD, door locks or manual window locks)
---
### 1.3 Safety goals

#### 1.3.1 Unauthorized Access:

    - The system shall continuously monitor for indications of unauthorized access or unexpected movement when the home is declared unoccupied.
    - The system shall immediately issue alerts to the occupants upon detection of unauthorized access or unexpected movement.
    - The system shall communicate an alert signal to a pre-defined security company upon detection of unauthorized access or unexpected movement.
    - The system shall persistently monitor the status of external doors in relation to the home occupancy status.
    - The system shall ensure closure of external doors within a predefined timeout interval.
    - The system shall ascertain the closure of critical windows in the absence of occupants or presence of minors.
    - The system shall ensure external doors are locked when the house is unoccupied or all occupants are asleep.
    - The system shall ensure critical windows are closed when the house is unoccupied or all occupants are asleep.

#### 1.3.2 System cybersecurity:

    - The system cybersecurity will be thoroughly covered during the Threat and Risk Assessment (TARA) process.

#### 1.3.3 Fire:

    - The system shall actively detect the presence of smoke.
    - The system shall promptly alert the occupants in the event of a fire.
    - The system shall schedule and issue reminders for maintenance of fire sensors.
    - The system shall unlock external doors to expedite evacuation in case of fire.

#### 1.3.4 Gas Leak:

    - The system shall alert the occupants promptly upon detection of a gas leak.
    - The system shall automatically disengage the main gas supply when a gas leak is detected.
    - The system shall schedule and issue reminders for maintenance of gas sensors.

#### 1.3.5 Carbon Monoxide Poisoning:

    - The system shall alert occupants when hazardous levels of carbon monoxide are detected.
    - The system shall schedule and issue reminders for maintenance of CO sensors.

#### 1.3.6 Water Leak/Flood:

    - The system shall install sensors in areas susceptible to water leaks.
    - The system shall promptly alert the occupants upon detecting a leak.
    - The system shall disengage the water supply upon detection of a leak.
    - The system shall alert occupants if any doors or windows are open in case of a rain forecast.
    - The system shall alert occupants if any doors or windows are open in case of a storm forecast.

#### 1.3.7 Electrical Shock:

    - The system shall schedule and notify for maintenance of the Residual Current Device (RCD).

#### 1.3.8 Poor Air Quality:

    - The system shall monitor the home's air quality, including parameters such as humidity and particulate matter levels.
    - The system shall alert the occupants if air quality deteriorates below a predefined standard and windows are open.
    - The system shall interface with air purifiers within the home to maintain air quality.

#### 1.3.9 Unsafe Cold Exposure:

    - The system shall alert the occupants if the temperature drops below a certain threshold.
    - The system shall interface with the home heating system to mitigate cold exposure hazards.
    - The system shall alert the occupants if the temperature drops and windows are open.
    - The system shall enhance the heating setpoint to maintain thermal comfort if the temperature drops and windows are open.

#### 1.3.10 Unsafe Heat Exposure:

    - The system shall alert the occupants if the temperature exceeds a certain threshold.
    - The system shall interface with the home heating and air conditioning systems to mitigate heat exposure hazards.
    - The system shall alert the occupants if the temperature rises, windows are closed, and the external temperature is lower than the room temperature.

#### 1.3.11 System Failure:

    - The system shall consistently monitor the activity of all sensors and actuators to detect timeouts and failures.
    - The system shall remind the users about updates periodically.
    - The system shall provide a backup power supply to ensure continuous operation in the event of a power outage.
    - The system shall perform regular self-checks or diagnostics to identify and alert users to potential failures or malfunctions.
    - The system shall monitor network connectivity and performance, including Ethernet port status, system latency, and packet loss.
    - The system shall monitor the health of the Zigbee network.
    - The system shall integrate with the existing Home Automation (HA) fault manager.

#### 1.3.12 Loss of Heating/Cooling:

    - The system shall continuously monitor the current flow temperature and compare it against the expected temperature range to detect any potential heater errors or anomalies.

---
### 1.4 Risk Evaluation

---

In this stage, you compare the risk levels from your risk assessment with your predetermined risk acceptance criteria. Risk acceptance criteria can be defined based on factors such as legal requirements, industry standards, and the risk tolerance of the stakeholders involved.

#### 1.4.1 Priority rules:

**Level 1 Risks:** Level 1 must be addressed immediately due to its high severity, high exposure, and low controllability. These risks are the top priority and should be mitigated before moving forward with the implementation. However, if additional measures cannot be implemented, Level 1 risks should be clearly stated.

**High Severity Risks:** Regardless of their exposure or controllability, risks with a high severity level should be next in line for mitigation. These risks can cause significant harm and, therefore, should be addressed promptly to protect the occupants and the property.

**Low Controllability Risks:** After high exposure risks, focus on risks with low controllability. These are risks that occupants have little to no control over and, thus, require an effective mitigation strategy to prevent potential harm.

Rest of safety measurements.
---
### 1.5 Risk Mitigation

---

For risks that need further mitigation, you'll need to develop a risk mitigation strategy. This strategy should outline specific actions to reduce the likelihood and/or impact of each risk. The strategy can include a variety of measures such as:

- _Mitigation:_ Reducing the impact or likelihood of the risk. This is often the main focus in the context of home automation systems.
- _Acceptance:_ Acknowledging the risk and preparing contingency plans.
- _Avoidance:_ Changing plans or strategies to entirely avoid the risk.
- _Transfer:_ Shifting the risk to another party, such as purchasing insurance.

#### 1.5.1 Risk assessment after implementing safety goals:

| Hazard                    | Severity   | Exposure   | Controllability | Risk Score     | Level   |
| ------------------------- | ---------- | ---------- | --------------- | -------------- | ------- |
| Unauthorized Access       | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| System cybersecurity      | High (3)   | Medium (2) | High (1)        | (2x3)x2x1 = 12 | Level 3 |
| Fire                      | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak                  | High (3)   | Low (1)    | Medium (2)      | (2x3)x1x2 = 12 | Level 3 |
| Carbon Monoxide Poisoning | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Electrical Shock          | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Poor Air Quality          | Low (1)    | Medium (2) | High (1)        | (2x1)x2x1 = 4  | Level 4 |
| Unsafe Cold Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 4 |
| Unsafe Heat Exposure      | Medium (2) | Medium (2) | High (1)        | (2x2)x2x1 = 8  | Level 4 |
| System Failure            | High (3)   | Low (1)    | Low (3)         | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood          | Medium (2) | Medium (2) | Medium (2)      | (2x2)x2x2 = 16 | Level 3 |
| Loss of Heating/Cooling   | Medium (2) | Low (1)    | Low (3)         | (2x2)x1x3 = 12 | Level 3 |
---
### 1.6 Risk Monitoring:

---

After mitigation measures are implemented, the risks are monitored to ensure that the mitigation measures are effective and to identify any new hazards that may arise.  
TODO
