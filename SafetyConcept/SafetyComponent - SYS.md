## 1. System Calibration values:
---
##### 1.2 Windows calibration values
---

Critical windows list:
    - Bedroom right window
    - Bedroom left window
    - Living room window
    - Kitchen window

External doors list and CAL_:
    - Garage gate
    - Entrance door
    - Living Room door

## 4. System components requirements:

### 3.1 Windows and doors close status

    - Possible safestates:
        - OPEN - Shall be open
        - CLOSED - Shall be closed
        - NOTIFICATION - Notify current status

    |          | Sleep time | Leaving | Vacation |
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


