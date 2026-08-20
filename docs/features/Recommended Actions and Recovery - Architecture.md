# Recommended Actions and Recovery - Feature Architecture

## 1. Purpose and boundary

RecoveryManager converts a current safety symptom into an operator-visible,
structured proposal. A proposal may be manual, automatic for an already
supported local actuator, or `user_confirmed`. External-hazard openings use only
the first and third policies.

SafetyHome is an authorization surface, not an actuator adapter. It sends a
proposal ID and one-time token through the authenticated Home Assistant
WebSocket connection. RecoveryManager remains the only element that may resolve
and call a Home Assistant service.

## 2. Proposal contract

Each active proposal has these allowlisted frontend fields:

- stable `proposal_id` and current lifecycle `status`;
- localized instruction and execution policy;
- reason, source, validity, area, and deadline;
- physical postcondition entity;
- actuator entity only when execution is supported;
- one-time confirmation token only while confirmation is allowed.

The raw lifecycle states are `DO_NOT_PERFORM`, `TO_PERFORM`,
`AWAITING_CONFIRMATION`, `EXECUTING`, `CONFIRMED`, `FAILED`, and `TIMED_OUT`.
SafetyHome translates these raw codes but does not change them.

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
    +-- manual ------------> TO_PERFORM --> contact reaches postcondition
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

## 4. External-hazard openings

Windows and ordinary doors publish a manual close instruction and use their
contact as the completion postcondition. Only these two installation bindings
are confirmation-gated actuators:

| Opening | Directional actuator | Closed postcondition |
| --- | --- | --- |
| Garage gate | `cover.brama_garazowa` | `binary_sensor.garage_gatedoorlow_contact_contact = off` |
| External gate | `cover.gate` | `binary_sensor.frontyard_externalgate_contact_contact = off` |

RecoveryManager calls `cover.close_cover`; it never calls either installation's
raw pulse button. No other External Hazard opening kind may define an actuator.

## 5. Persistence and notification ownership

Active proposal state is stored atomically in
`/config/appdaemon/recovery_state.json`, outside the deployed application
directory. Restart restores operator-visible state without replaying a command.
A restored confirmation proposal receives a new token.

Notification guidance is keyed by proposal ID. An updated proposal replaces its
own text, while clear or shadow removes that proposal's guidance. This prevents
stale or contradictory instructions from accumulating on an active fault.

## 6. Verification

Automated tests shall cover exact proposal payloads, manual versus confirmed
policy, no actuation before confirmation, invalid and replayed tokens, the exact
allowlisted service, physical postcondition handling, timeout, persistence,
shadow/clear withdrawal, and multiple proposals sharing one recovery entity.

Deployment verification shall use configuration readback, hashes, logs, and
diagnostic entity state. It shall not close a household gate merely to prove the
deployment.
