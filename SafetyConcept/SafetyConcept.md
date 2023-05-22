# Home Automation - Safety, security and recovery strategy

## 1. Hazard analysis and risk assessment
### 1.1 Hazard identification:
This process identifies and analyzes potential hazards to the home automation system and its occupants.
By assessing the system, components, and external factors, all hazards are identified for a comprehensive understanding of risks.
This involves examining security vulnerabilities, safety concerns, environmental factors, and system malfunctions.
Identified hazards inform risk assessment and guide the development of safety measures.

---
#### ****Identyfied hazards:****
---
##### **Unauthorized Access:** 
This could occur if a door or window is left open or unlocked, or if a security system is disabled.  

##### **Fire:** 
This could be caused by a malfunctioning device, such as a heater, stove, or electrical equipment.  
##### **Gas Leak:** 
Gas appliances could leak, leading to potential poisoning or explosion.  
##### **Carbon Monoxide Poisoning:** 
This is another risk associated with gas appliances, particularly if they are not properly ventilated.  
##### **Water Leak/Flood:** 
This could occur if a pipe bursts or a faucet is left running.  
##### **Electrical Shock:** 
This could be caused by a faulty device, or by water coming into contact with electrical equipment.  
##### **Poor Air Quality:** 
This could be caused by a lack of ventilation, leading to a buildup of pollutants or allergens.  
##### **Loss of Heating/Cooling:** 
This could occur if the HVAC system fails, leading to uncomfortable or even dangerous indoor temperatures.  
##### **Failure of Safety or Monitoring Devices:** 
Devices like smoke detectors, CO detectors, or security cameras could fail to operate correctly.  
##### **Privacy Invasion:** 
Unauthorized access to the system could lead to privacy concerns, such as surveillance through security cameras.  
##### **System Failure:** 
A failure in the home automation system itself could lead to various problems, such as lights not working, doors not unlocking, etc.  
##### **Unsafe Cold Exposure:** 
This can occur if a room's temperature falls below the safe threshold for the situation or occupants. For example, the bathroom temperature might need to be at least 22°C during a child's bath.  
##### **Unsafe Heat Exposure:** 
Similarly, a room's temperature could rise above the safe threshold for the situation or occupants. For example, the living room might become uncomfortably or unsafely hot during a summer heatwave if the cooling system isn't functioning properly.  
##### **Rain Entering Through Open Window:**  
This hazard arises when rain enters through an open window, potentially causing water damage to the home's interior and electrical systems. A smart home system can help prevent this by monitoring the weather and alerting residents or automatically closing windows when rain is detected.  

---

### 1.2 Hazards assessment and risk classification:  
This process evaluates identified hazards based on severity, exposure, and controllability.
By quantifying these factors and calculating risk scores, hazards are prioritized.
The assigned priorities guide the development of safety measures and risk mitigation strategies.  

Based on the hazard assessment, each identified hazard is assigned a risk level. This risk level is typically determined by factors such as the potential severity of the hazard, the likelihood of the hazard occurring, and the ability of the user or system to control the hazard.  

---

#### Definitions   
*Severity* refers to the potential harm that could be caused by the hazard. High severity hazards could cause serious harm, such as injury or significant property damage, while medium severity hazards might cause discomfort or minor damage.  

*Exposure* refers to the likelihood of the hazard occurring. High exposure hazards could occur regularly, while medium exposure hazards might only occur occasionally.  

*Controllability* refers to the user's ability to prevent or mitigate the hazard. High controllability hazards can be easily managed by the user, while medium controllability hazards might require more effort or specialized knowledge to manage.  

---

#### Numerical values:  
High=3, Medium=2, and Low=1 for *Severity*, *Exposure*  
High=1, Medium=2, and Low=3 for *Controllability*   

#### Formula Risk:  
Risk_score = (2 x *Severity*) x *Exposure* x *Controllability* to calculate risk.    

#### Categories:  
*Level 1:* High Risk (Risk score 24 and above)  
*Level 2:* Medium Risk (Risk score between 12 and 23)  
*Level 3:* Low Risk (Risk score between 6 and 11)  
*Level 4:* Very Low Risk (Risk score 5 or below)  

### Risk assessment rules  
**Severity:**  
*High*: These hazards pose immediate threats to health or life. They require instant action to mitigate. Examples include a fire, gas leak, or carbon monoxide poisoning.  

*Medium*: These hazards could lead to potential costs if not addressed promptly. They might not directly threaten health or life but can cause significant damage or inconvenience. For instance, unauthorized access could lead to theft, while a water leak could cause property damage.  

*Low*: These hazards might cause minor costs if repeated over time, or could potentially impact health if the exposure is sustained or repeated. For example, poor air quality might not pose a direct threat but can lead to health issues over time. Similarly, a slight loss of heating or cooling might be uncomfortable but is not immediately dangerous.  

**Exposure:**  
*Low:* These hazards are very unlikely to occur. There might be very specific or rare conditions that could lead to these hazards, but under normal circumstances, the chances are minimal.  

*Medium:* These hazards are possible under certain circumstances. They might not happen regularly, but there are known situations or conditions where these hazards could materialize.  

*High:* These hazards occur often or under a wide range of common conditions. They are part of the routine or daily operation and therefore have a higher likelihood of happening.  

**Controllability:**  
*Low:* These hazards are beyond the control of the residents or can only be mitigated in a limited way. They often require the involvement of specialists or emergency services to manage. For example, a gas leak would be considered a low controllability hazard, as it requires professional assistance to mitigate.  

*Medium:* Residents can mitigate these hazards, but it may take time and the recovery may not be complete. These are situations that may not be easily managed remotely. For example, a water leak could be considered a medium controllability hazard, as a resident could potentially stop the leak, but may not be able to repair the damage without professional help.  

*High:* These hazards can be easily mitigated if residents are notified in time, and many of these situations can be managed remotely. For instance, an open window could be considered a high controllability hazard, as it can be simply closed if a resident is notified and still in the house, or potentially even remotely via an automated system.    

---

| Hazard | Severity | Exposure | Controllability | Risk Score | Level |
| --- | --- | --- | --- | --- | --- |
| Unauthorized Access | High | Medium | Low | (2x3)x2x3 = 36 | Level 1 |
| System cybersecurity | High | High | High | (2x3)x3x1 = 18 | Level 2 |
| Fire | High | Low | Low | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak | High | Low | Low | (2x3)x1x3 = 18 | Level 2 |
| Carbon Monoxide Poisoning | High | Low | Low | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood | Medium | Medium | Medium | (2x2)x2x2 = 16 | Level 2 |
| Electrical Shock | High | Medium | Low | (2x3)x2x3 = 36 | Level 1 |
| Poor Air Quality | Low | High | Medium | (2x1)x3x2 = 12 | Level 3 |
| Unsafe Cold Exposure | Medium | High | Medium | (2x2)x3x2 = 24 | Level 1 |
| Unsafe Heat Exposure | Medium | High | Medium | (2x2)x3x2 = 24 | Level 1 |
| System Failure | High | Low | Low | (2x3)x1x3 = 18 | Level 2 |
| Rain Entering Through Open Window | Medium | High | Medium | (2x2)x3x2 = 24 | Level 1 |
| Loss of Heating/Cooling | Medium | Low | Low | (2x2)x1x3 = 12 | Level 3 |

> Certainly, it's important to note that the initial risk assessment you have conducted takes into consideration the basic safety measures that are commonly found in homes, even without the presence of a home automation system. These traditional safety measures form the baseline upon which the home automation system's additional safety features are built. (ie. RCD, door locks or manual window locks)

### 1.3 Safety goals

#### Unauthorized Access:  
    - The system should monitor for signs of forced entry or movement when the home is unoccupied, 
    - The system should alert the occupants
    - The system should alert a security company.  
    - The system shall monitor external doors state regard current occupy of house.  
    - External doors shall be closed in defined timeout.
    - Front windows shall be closed if nobody/kids are in house 

#### System cybersecurity:  
    - Add two factor authentication to HA system.  
    - The system should encrypt communication and storage of sensitive data to prevent unauthorized access.  

#### Fire:  
    - The home automation system should detect
    - The system should alert occupants of a fire in any part of the home.  
    - The system should schedule and notify of maintenance of fire sensors.  
    - The system shall unlock external doors to speedup evacuation  

#### Gas Leak:  
    - Gas sensors should be installed near potential sources of gas leaks, such as the kitchen stove, gas heater, or any other gas appliances.   
    - The system should alert occupants   
    - The system should shut off the main gas supply in case of a detected gas leak.  
    - The system should schedule and notify of maintenance of gas sensors.  

#### Carbon Monoxide Poisoning:  
    - Carbon monoxide detectors should be placed in key areas such as near bedrooms and fuel-burning appliances. The system should alert occupants if dangerous levels of carbon monoxide are detected.  
    - The system should schedule and notify of maintenance of CO sensors.  
    
#### Water Leak/Flood:  
    - Sensors should be installed in areas prone to water leaks.   
    - The system should alert occupants of detected leaks  
    - The system should shutting off the water supply.  

#### Electrical Shock:  
    - The system should schedule and notify of maintenance of RCD.  

#### Poor Air Quality:  
    - Monitor the home's air quality, including indicators such as humidity and particulate matter levels.  
    - The system should alert occupants if air quality falls below a certain standard.  
    - The system should interact with air purifiers in house.  

#### Unsafe Cold Exposure:  
    - The system should monitor the temperature in each room.  
    - The system shall notify occupants if temperature is below threshold  
    - The system shall interact with house heating system to mitigate hazard. 
    - The system shall monitor doors and windows status
    - The system shall notify occupants if temperature is falling and windows are open

#### Unsafe Heat Exposure:  
    - The system should monitor the temperature in each room.  
    - The system shall notify occupants if temperature is above threshold  
    - The system shall interact with house heating system to mitigate hazard. 
    - The system shall interact with house AC system to mitigate hazard.  
    - The system shall notify occupants if temperature is falling and windows are closed if outside temperature is lower than in room.

#### Rain Entering Through Open Window:  
    - The system shall monitor doors and windows status
    - The system shall monitor current weather 
    - The system shall notify occupants of incoming rain if one of doors or windows is open.  
    - The system shall notify occupants if storm is comming and windows are open

#### System Failure:  
    - The system shall monitor all safety devices activity to detect timeouts.   
    - The system shall remind about updates.   
    - The system should have a backup power supply to ensure continuous operation in the event of a power outage.  
    - Critical components of the system (such as fire and gas leak detectors) should be designed with redundancy, so that the failure of a single component does not compromise the entire system. 
    - The system should regularly perform self-checks or diagnostics to identify and alert users to potential failures or malfunctions.    
    - The system should have a manual override capability, allowing users to control critical functions in the event of a system failure.   

#### Loss of Heating/Cooling:  
    - The system shall monitor current flow temperature against heater error.  


### 1.4 Risk Evaluation  
---

In this stage, you compare the risk levels from your risk assessment with your predetermined risk acceptance criteria. Risk acceptance criteria can be defined based on factors such as legal requirements, industry standards, and the risk tolerance of the stakeholders involved.   

#### Priority rules:  
**Level 1 Risks:** Level 1 must be addressed immediately due to its high severity, high exposure, and low controllability. These risks are the top priority and should be mitigated before moving forward with the implementation. However, if additional measures cannot be implemented, Level 1 risks should be clearly stated.     

**High Severity Risks:** Regardless of their exposure or controllability, risks with a high severity level should be next in line for mitigation. These risks can cause significant harm and, therefore, should be addressed promptly to protect the occupants and the property.  

**Low Controllability Risks:** After high exposure risks, focus on risks with low controllability. These are risks that occupants have little to no control over and, thus, require an effective mitigation strategy to prevent potential harm.  

Rest of safety measurements.  

### 1.5 Risk Mitigation  
---

For risks that need further mitigation, you'll need to develop a risk mitigation strategy. This strategy should outline specific actions to reduce the likelihood and/or impact of each risk. The strategy can include a variety of measures such as:  


- *Mitigation:* Reducing the impact or likelihood of the risk. This is often the main focus in the context of home automation systems.  
- *Acceptance:* Acknowledging the risk and preparing contingency plans.  
- *Avoidance:* Changing plans or strategies to entirely avoid the risk.  
- *Transfer:* Shifting the risk to another party, such as purchasing insurance.  

#### Risk assessment after implementing safety goals:  

| Hazard | Severity | Exposure | Controllability | Risk Score | Level |
| --- | --- | --- | --- | --- | --- |
| Unauthorized Access | High (3) | Low (1) | Low (3) | (2x3)x1x3 = 18 | Level 2 |
| System cybersecurity | High (3) | Medium (2) | High (1) | (2x3)x2x1 = 12 | Level 3 |
| Fire | High (3) | Low (1) | Low (3) | (2x3)x1x3 = 18 | Level 2 |
| Gas Leak | High (3) | Low (1) | Medium (2) | (2x3)x1x2 = 12 | Level 3 |
| Carbon Monoxide Poisoning | High (3) | Low (1) | Low (3) | (2x3)x1x3 = 18 | Level 2 |
| Water Leak/Flood | Medium (2) | Low (1) | Medium (2) | (2x2)x1x2 = 8 | Level 4 |
| Electrical Shock | High (3) | Low (1) | Low (3) | (2x3)x1x3 = 18 | Level 2 |
| Poor Air Quality | Low (1) | Medium (2) | High (1) | (2x1)x2x1 = 4 | Level 4 |
| Unsafe Cold Exposure | Medium (2) | Medium (2) | High (1) | (2x2)x2x1 = 8 | Level 4 |
| Unsafe Heat Exposure | Medium (2) | Medium (2) | High (1) | (2x2)x2x1 = 8 | Level 4 |
| System Failure | High (3) | Low (1) | Low (3) | (2x3)x1x3 = 18 | Level 2 |
| Rain Entering Through Open Window | Medium (2) | Medium (2) | Medium (2) | (2x2)x2x2 = 16 | Level 3 |
| Loss of Heating/Cooling | Medium (2) | Low (1) | Low (3) | (2x2)x1x3 = 12 | Level 3 |
    
### 1.6 Risk Monitoring:  
---

After mitigation measures are implemented, the risks are monitored to ensure that the mitigation measures are effective and to identify any new hazards that may arise.   
TODO  

---
---
## 2. System requirements 
---
---
### 2.1 System boundaries  
---
#### 2.1.1 Inside the System Boundary:
---
Hardware sensors - Input interface:  
- windows contact sensor
- door contact sensor
- smoke detector
- gas detector
- carbon monooxide detector
- climate sensor for each room (temperature and humidity)  
- Inside air pollution

Cloud sensors - Input interface:  
- Weather sensor
    - Current temperature, pressure, wind speed, clouds
    - Forecast for temperature, pressure, wind speed, clouds
    - Hazardous fenoma:
        - Storm alert
        - Blizzard alert
        - Wind alert
        - Rain alert
        - Heatwave alert
        - Tornado alert
- Occupancy sensor
- Outside air pollution

HW Actuators - Output interface: 
- Smart locks
- Siren
- Information light
- Alert light

Cloud Actuators:
- Phone application popup
- Main card in Lovelance
- User action scheduler

Processing:
- Home assistant instance

---
#### 2.1.2 Outside the System Boundary:
---
- The physical environment where the home is located and which the sensors are monitoring
- Users who interact with the system, either physically or through an interface/app
- Internet services providing data such as weather forecasts


---
#### 2.1.3 System modes:
---
**Armed Mode:** 
- The system is actively monitoring for hazards and is ready to react.   

**Disarmed Mode:** 
- The system is not actively monitoring for hazards.   

**Maintenance Mode:** 
- The system checks the status of its sensors and actuators, updates its software, and performs other maintenance tasks.

---
#### 2.1.4 Interfaces requirements:
---

#### House occupy
- Sleep time - Event that notify that everyone goes to sleep
- Leave - Home is empty less than 1 day
- Vacation - Home is empty more than 1 day
- Home Alone: Only one person is at home. This could adjust safety and security measures, and change other settings like temperature or lighting.
- Guests: You have guests over. This may require different settings for privacy, security, or comfort.

#### Weather and external environment:
- Freezing - Temperature below 4 C
- Storm - Incoming storm
- Rain
- Air pollution - Air pollution 2.5pmm above 20
- Heatwave: High temperatures might require specific responses such as closing blinds, turning on air conditioning, etc.
- High Wind: Could lead to similar responses as a storm.
- Snow: Cold temperatures combined with snowfall might affect heating systems and require specific actions.
- High Humidity: This might trigger dehumidifiers or other responses to control internal humidity.

---
#### 2.1.5 System components:
---

**Window Monitoring Component:**  

**Inputs:**  

- Window contact sensor data
Occupancy sensor data
Room temperature sensor data
Outside temperature data (from weather forecast)
Rain forecast data (from weather forecast)
Storm forecast data (from weather forecast)

**Outputs:**   

- Alerts to occupants (via various channels)

**Safety Goals Addressed:**

- Front windows shall be closed if nobody/kids are in the house
- The system shall notify occupants if the temperature is falling and windows are open
- The system shall notify occupants if the temperature is falling and windows are closed if the outside temperature is lower than in the room
- The system shall notify occupants of incoming rain if one of the doors or windows is open
- The system shall notify occupants if a storm is coming and windows are open

**States and Transitions:**

- Normal State: All windows are closed, no alert conditions exist  
- Window Open State: One or more windows are open, which triggers the following sub-states:
    - Unoccupied House State: No occupants in the house  
    Trigger: Occupancy sensor detects no occupants and at least one window is open  
    Action: Alert occupants that a window is open while the house is unoccupied  
    - Temperature Falling State: Room temperature is falling
    Trigger: Room temperature sensor detects a falling trend and at least one window is open  
    Action: Alert occupants that the temperature is falling and windows are open  
    - Outside Temperature Lower State: Outside temperature is lower than room temperature  
    Trigger: Outside temperature sensor detects a lower temperature than room temperature   sensor and windows are closed  
    Action: Alert occupants that the temperature is falling and windows are closed  
    - Rain Forecast State: Rain is forecast  
    Trigger: Weather forecast predicts rain and at least one window is open  
    Action: Alert occupants of incoming rain and open windows  
    - Storm Forecast State: Storm is forecast  
    Trigger: Weather forecast predicts a storm and at least one window is open  
    Action: Alert occupants of incoming storm and open windows  

--- 

---
#### 2.1.6 System Calibration values:
---



## 4. System components requirements:
### 3.1 Windows and doors close status
- Each doors and windows shall have defined safety status for scenarios:
    - Sleep time
    - Vacation (more than 1 day)
    - Out (less than 1 day)
- External doors shall have defined timeout
- System shall monitor outside temperature, corresponding room temperature and window status
- System shall monitor external air pollution and windows status

- Possible safestates:
    - OPEN - Shall be open
    - CLOSED - Shall be closed
    - NOTIFICATION - Notify current status

| | Sleep time | Leaving | Vacation |
| -------- | -------- | -------- | -------- |
| Bedroom door | CLOSED | CLOSED | CLOSED |
| Upper bathroom door | CLOSED | CLOSED | CLOSED |
| Office door | CLOSED | CLOSED | CLOSED |
| Wardrobe door | CLOSED | CLOSED | CLOSED |
| Kids Room door | CLOSED | CLOSED | CLOSED |
| Bathroom door | CLOSED | CLOSED | CLOSED |
| Garage door | CLOSED | CLOSED | OPEN |
| Upper bathroom window | NOTIFICATION | NOTIFICATION | CLOSED |
| Bedroom window | NOTIFICATION | CLOSED | CLOSED |
| Kids Room window | NOTIFICATION | NOTIFICATION | CLOSED |
| Office window | NOTIFICATION | NOTIFICATION | CLOSED |
| Bathroom window | CLOSED | CLOSED | CLOSED |
| Kitchen window | CLOSED | CLOSED | CLOSED |
| Living room window | CLOSED | CLOSED | CLOSED |
| Garage gate | CLOSED | CLOSED | CLOSED |
| Entrance door | CLOSED | CLOSED | CLOSED |
| Living Room door | CLOSED | CLOSED | CLOSED |

#### Priorities
- External doors dangers are always priority 1
- All daggers during leaving and vacation conditions are priority 1 except notification cases.
- Dangers with notification RA are always priority 2
- Sleep time daggers for windows and door are priority 1 except notification

### 3.2 External doors timeouts
- Dangers shall be active if external doors are open longer than specified in the table.
    - Garage gate: 120s
    - Entrance door: 60s
    - Living Room door: 3h
#### Priorites
- External doors dangers are always priority 1

