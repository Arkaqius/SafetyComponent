# Recommended Actions and Recovery - Feature Architecture

## 1. Purpose and boundary

Recovery shall describe a concrete action to mitigate a hazard or restore a
failed capability. The owning component shall derive the action from the
current fault, its contributing cause and the affected subject. RecoveryManager
shall manage the resulting operator-visible proposal, eligibility, execution
and completion evidence. An actuator or observable contact shall not be required
to offer a manual action.

A proposal may be `manual`, `automatic` for an explicitly supported local
actuator, or `user_confirmed`. External-hazard openings shall use only `manual`
and `user_confirmed`. Fault level shall select urgency, not authorize a command.
Components whose actuator control is excluded shall still supply appropriate
manual recovery actions. Passive Group C inventory shall create none.

SafetyHome shall present the same proposals at the owning fault and in the
shared actions list. It shall submit command authorization or manual-work
reports through the authenticated Home Assistant connection. Command
authorization shall carry a proposal ID and one-time token. RecoveryManager
shall remain the only recovery element that resolves and calls an actuator
service; reporting manual work shall issue no actuator command.

## 2. Proposal contract

Internal environmental monitoring shall supply manual hazard-response and
detector-repair actions without an actuator call. Their instructions shall follow the
[internal hazard advice boundary](<Internal Environmental Hazard Monitoring - Architecture.md#7-guidance-and-output-safety>).
Shared policy shall prevent comfort/PM ventilation or purification proposals
from conflicting with active or unresolved smoke/gas/CO evidence. Clearing a
detector alarm shall not authorize gas reopening, detector reset or re-entry.
Existing unrelated recovery proposals shall still require their own current
hazard-specific eligibility checks.

Each proposal shall identify its action, purpose (hazard mitigation or capability
repair), fault and incident, contributing cause, affected device/opening/area,
executor, current eligibility, and declared completion method. Multiple causes
of one fault shall retain their own actions and evidence. Repeated updates to
one action shall replace its context without creating duplicates. Distinct
actions for one cause shall have distinct proposal identities.

The existing allowlisted frontend fields shall retain their names:

- stable `proposal_id` and current lifecycle `status`;
- localized instruction and execution policy;
- reason, source, validity, area, and deadline;
- postcondition entity when observable evidence is available;
- actuator entity only when execution is supported;
- one-time confirmation token only while confirmation is allowed.

The raw lifecycle states are `DO_NOT_PERFORM`, `TO_PERFORM`,
`AWAITING_CONFIRMATION`, `EXECUTING`, `CONFIRMED`, `FAILED`, and `TIMED_OUT`.
SafetyHome translates these raw codes but does not change them.

Additional completion and ownership metadata shall use an explicit allowlist.
It shall identify the expected result, evidence source and time, a manual-work
report when applicable, and the reason for blocked or unavailable execution.
Private configuration and unfiltered diagnostic snapshots shall not be copied
into proposals. Missing evidence shall be presented as unknown.

### 2.1 Execution and completion are separate decisions

| Policy | Executor | Command authorization | Completion |
| --- | --- | --- | --- |
| `manual` | User or service technician | None; actuator changes shall be rejected centrally | Declared observed postcondition, or an explicit operator report for a procedural task |
| `user_confirmed` | RecoveryManager after user consent | Current proposal and one-time token, followed by backend revalidation | Observed postcondition; consent and service acceptance are not completion |
| `automatic` | RecoveryManager under explicit component policy | Current eligibility and supported configured service | Observed postcondition; service acceptance is not completion |

A completable task shall declare either observed evidence or an operator report.
Advisory instructions shall declare that they have no task-completion control;
their applicability and withdrawal shall still be reevaluated.
For example, closing a door uses its current contact state; replacing a battery
requires a fresh recovered battery indication; contacting a service technician
may be completed by an operator report. A report shall retain authenticated
operator identity, server-assigned time and the reported task. It shall be bound
to the current proposal and incident and revalidated before acceptance; unknown,
expired or superseded reports shall be rejected. It shall not substitute for
required device evidence or establish hazard clearance. Reports for approved
maintenance-test tasks may provide evidence only under that test's existing
attestation policy; the owning monitor shall evaluate the result.

For an observed-evidence action, a manual-work report shall leave the action
awaiting its postcondition, with a visible explanation. `CONFIRMED` shall mean
the declared action completion method was satisfied; presentation shall say
whether this was observed or operator-reported. A purely advisory instruction
shall not require a user to acknowledge evacuation or emergency guidance.

Action completion shall not clear its fault. FaultManager shall retain fault
qualification, aggregation and any authorized-reset policy. Closing a window
can complete a mitigation action while a room remains too cold. Replacing a
battery can be reported while its device has not yet sent a fresh reading.
Acknowledging a notification, consenting to a command and reporting manual work
shall remain distinct operations.

### 2.2 Eligibility and withdrawal

The owner shall re-evaluate proposals on changes to their relevant evidence,
cause, policy and dependencies. A superseded, expired or no-longer-eligible
instruction shall be withdrawn with its token, listeners and notification
guidance. Returning no action or rejecting a replacement shall not leave an old
executable proposal active. Clearing or shadowing shall withdraw redundant
proposals without claiming they were completed.

Blocked execution shall expose its reason and retain valid repair guidance.
Loss of a contact may block automatic closure or result verification while
still allowing an instruction to inspect the contact. Repair guidance for a
failed data path shall not require that same path to be healthy. Hazard-specific
advice requiring missing evidence shall remain unavailable. Faults with no
applicable action shall have an explicit rationale; absence of a proposal shall
not be labeled proof that no action is needed.

## 3. Execution flow

```text
active symptom
    |
    v
component creates RecoveryResult
    |
    v
RecoveryManager policy and conflict checks
    |
    +-- manual ------------> TO_PERFORM --> declared completion method
    |
    +-- automatic ---------> service call --> EXECUTING --> postcondition
    |
    +-- user_confirmed ----> AWAITING_CONFIRMATION
                                  |
                          SafetyHome confirmation
                                  |
                     revalidate current proposal
                                  |
                     allowlisted service call
                                  |
                         EXECUTING --> postcondition
```

Confirmation validation shall reject an unknown proposal, wrong or replayed
token, expiry, cleared or shadowed symptom, policy conflict, and any change to
the configured actuator. Confirmation does not clear the underlying fault.

For observed completion, all required postconditions shall use current valid
evidence. Invalid or unavailable data shall not complete an action. A deadline
shall distinguish expiry of consent from failure to observe an executed command's
effect. Manual work shall use a task-specific deadline only when policy defines
one; the command-confirmation timeout shall not be applied to battery replacement
or service work. Instructions without observable postconditions shall use a
declared operator-report method or remain advisory, rather than wait indefinitely
for a nonexistent sensor.

## 4. External-hazard openings

Windows and ordinary doors publish a manual close instruction and use their
contact as the completion postcondition. A confirmation-gated example uses:

| Opening | Directional actuator | Closed postcondition |
| --- | --- | --- |
| Example driveway gate | `cover.example_driveway_gate` | `binary_sensor.example_driveway_gate = off` |

RecoveryManager calls `cover.close_cover`; it never calls a raw pulse button.
No unsupported External Hazard opening kind may define an actuator.

### 4.1 Manual recovery allocation

The following allocation shall apply to installed fault families. Instructions
shall name the actual affected subject and known cause; diagnostic observations
shall not be promoted to an inferred physical cause. Several checks sharing one
failed path shall share its repair action. Separate failed paths shall retain
independent actions. Existing fault, mechanism and entity identities shall remain
stable.

| Fault family / cause | Required action | Completion / effect evidence | Command boundary |
| --- | --- | --- | --- |
| `SafetyDoorOpenTimeout{DoorKey}` | Close the named door or gate manually | Current valid closed contact; another door's state is irrelevant | No C-DOOR close, lock or unlock command |
| `RemoteBatteryLow{DeviceKey}` | Replace or charge the named device's battery according to its known equipment profile; if the method is unknown, inspect its instructions | Fresh battery evidence satisfying that device's recovery policy | No device-control call |
| `EntityHealth{EntityKey}`, `InputMonitoringUnavailable` | Inspect the named input's power, link, integration or reporting path according to the failed check | That cause's valid availability, freshness and value checks recover | No automatic restart or reconfiguration |
| `InternalEnvironmentalDetectorUnavailable` | Inspect/service the affected detector or supervised input using its equipment instructions | Independent failed supervision causes recover; a maintenance-test report is not an alarm clear | No detector hush/reset or test command |
| `ExternalDataUnavailable` | Inspect the named provider or required data capability and its connection/configuration | Fresh valid provider/path evidence for the failed contributor | No provider-driven actuator or automatic reconfiguration |
| `TemperatureRecoveryUnavailable`, `ExternalRecoveryUnavailable` | Inspect the affected actuator/contact/input; offer manual mitigation only when hazard policy permits it | Dependency recovery for health failure; observed target postcondition for command/effect failure | No replay of a failed command |
| `RiskyTemperature`, `RiskyTemperatureForecast` (low) | Offer eligible window manipulation, or inspect the affected room when that proposal is unavailable | Contact/actuator evidence completes window work; qualified temperature evidence heals the fault | Supported configured window action only; no HVAC/climate command |
| `RiskyTemperature`, `RiskyTemperatureForecast` (high) | Inspect the affected room and obtain equipment/service guidance for the reported condition | Room inspection may be operator-reported; qualified temperature evidence heals the fault | No window, HVAC or climate command from the high-temperature path |
| `ExternalWeatherExposure`, `OutdoorAirQualityExposure` | Close the named exposed opening under current hazard policy | Current valid closed contact | Manual or supported directional cover after explicit consent |
| `InternalSmokeDetected`, `InternalFlammableGasDetected`, `InternalCarbonMonoxideDetected`, `WaterLeakDetected`, indoor PM conditions | Present the hazard-specific manual response from the internal-hazard contract | Detector/concentration recovery remains separate from user action and does not establish safe re-entry | No detector, ventilation, purification, valve or other actuator command |
| `SafetyAppHealth` | Repair the specific failed publication, delivery, output, store, evaluation or recovery path; show the affected channel/store/subject | Successful evidence on that same path and operation; recipient receipt remains separately attested | No automatic restart, output test, evidence deletion or command replay |
| Platform, WAN, update, backup and maintenance faults | Present cause-specific inspection, maintenance or supported test-report tasks; preserve Supervisor/installation ownership | Rule-specific fresh evidence or explicitly sourced procedural/test reports | No monitor-issued restart, update installation, restore or household routine |
| Heating monitoring faults | Inspect the named equipment/telemetry path or contact service using the model-specific interpretation | Rule-specific heating evidence; communication recovery alone cannot prove thermal recovery | No boiler reset, setpoint, pump forcing or interlock bypass |

Urgent hazard instructions shall follow the
[internal-hazard guidance contract](<Internal Environmental Hazard Monitoring - Architecture.md#7-guidance-and-output-safety>).
The catalog shall not authorize re-entry, gas reopening or speculative ventilation.
High-temperature manual guidance shall not reuse low-temperature window logic.

## 5. Persistence and notification ownership

Active proposal state is stored atomically in the `recovery_state` namespace of
the shared `/config/appdaemon/safety_state.sqlite3` database, outside the deployed
application directory. The existing `/config/appdaemon/recovery_state.json`
configuration path remains a one-time legacy import source, as defined by
[Runtime State Storage](<Runtime State Storage - Architecture.md>).
Restart restores operator-visible state without replaying a command.
A restored confirmation proposal receives a new token.

Manual-work reports and the latest action outcomes shall be persisted with
bounded system-owned retention in the same recovery namespace. Each outcome
shall identify the fault/incident, proposal, result, completion method, evidence
time/source and reason for failure or withdrawal. A transient publication of
`CONFIRMED` followed by removal shall not be the only record of completion.
Restart shall reconcile unresolved work with current evidence without repeating
a command or treating a saved operator report as fresh device evidence.

Notification guidance is keyed by proposal ID. An updated proposal replaces its
own text, while clear or shadow removes that proposal's guidance. This prevents
stale or contradictory instructions from accumulating on an active fault.

SafetyHome and notifications shall use the owner's same localized instruction.
The fault card and shared list shall identify the subject, executor, expected
result, report/evidence status and any block reason. The frontend shall expose
a manual-work report only when useful for that action, and label consent buttons
by the actual command rather than assume every command closes a gate. Runtime
text shall maintain EN/PL/DE meaning parity; technical IDs and raw codes shall
remain language-independent.

## 6. Verification

Automated tests shall cover exact proposal payloads, manual versus confirmed
policy, no actuation before confirmation, invalid and replayed tokens, the exact
allowlisted service, physical postcondition handling, timeout, persistence,
shadow/clear withdrawal, and multiple proposals sharing one recovery entity.

Contract tests shall also cover central rejection of actuator changes under
`manual`, operator reports without actuation or fault clearance, actions without
postcondition entities, delayed/missing/invalid completion evidence, independent
causes, withdrawal on an empty or rejected replacement, visible block reasons,
task-specific deadlines, durable outcomes and report-source localization. Tests
for observation-only components shall assert useful manual proposals alongside
zero actuator calls. System and software traceability is defined in
[SYS section 8.10](<../sys/SafetyConcept - SYS.md#810-recommended-actions-and-recovery>)
and [SSRD section 4.5](<../sys/SafetyComponent - SSRD.md#45-notifications-and-recovery>).

Deployment verification shall use configuration readback, hashes, logs, and
diagnostic entity state. It shall not close a household gate merely to prove the
deployment.
