# Contract: Shared SafetyMechanism Lifecycle

## Shared Execution Object and Scope

Retain `SafetyMechanism` as the common concrete callback-based object; do not
introduce one unrelated base per domain. A typed `LifecycleScope` owns each
registration, timer and generation. A mechanism has its own scope; a component
may own a parent scope for one source listener or sampler shared by several
mechanisms. Every handle has exactly one owner and an explicit cancellation kind
(state listener, event listener, timer or EventBus subscription).

Construction records configuration only. `start()` registers once and is
idempotent. Activation remains separate through existing enable operations.
Repeated `stop()` is harmless: invalidate generation first, disable execution,
cancel owned work and release subscriptions. A new start uses a new generation;
it never resumes an old qualification interval. Child stop cannot cancel a
parent's shared listener while other enabled children require it.

Disable invalidates pending qualification and denies live result application.
Stopping/disabled state is not HEAL and cannot delete assertions or gas latches.
Cancellation failure remains visible, while the generation fence still prevents
late callbacks from changing state. A callback already computing on the owner
thread must recheck generation before result application. Resource bags hold at
most the finite declared registrations plus one current qualification timer per
channel; repeated evaluations replace/cancel work instead of growing the bag.

## Explicit Inputs and Evaluation Outcomes

Accept entity IDs only through explicit `monitored_entities` declarations or a
declared parent source binding. Strings in `sm_args`, including `location`,
friendly names, actuator metadata and policy text, never imply monitoring.
Temperature forecast declares both temperature and derivative inputs. Door
gating declares its contact and optional condition entity. Heating and Entity
Monitor retain their shared sampling paths; indoor alarms retain full event
payloads and source-session reconciliation. External hazards retain EventBus
provider input plus explicit contact bindings.

Preserve existing mechanism names, `isEnabled` access, registration/enable calls
and parameter keys through typed internal adapters. Delegate `isEnabled` writes
to lifecycle eligibility/invalidation rather than a second independent Boolean.
Normalize the legacy decorator and direct evaluators at their execution boundary.
A result contains outcome
(eligible-positive, eligible-negative, unevaluable, inhibited or disabled), current
identity, bounded evidence and optional failure reason. These are internal result
variants, not new MQTT raw state codes. Domain kernels still own assertion,
recovery, monotonic qualification and cause latching. Do not run another generic
debounce after a qualified domain result.

Report evaluation success/failure once per actual owner evaluation, including
timer/EventBus entry points. A failure cannot become an eligible-negative result.
Recovery simulation is an explicit read-only operation: no state mutation,
qualification, event publication, timers or actuator calls. Unevaluable simulation
cannot establish that an action resolves a hazard; RecoveryManager retains final
authorization and physical postcondition responsibilities.

## Component Integration and Startup

Adapt all six families in one coordinated contract change: temperature, Safety
Doors, Entity Monitor, heating, indoor environmental hazards and external hazards.
Move existing cancellation ownership into scopes without duplicating listeners or
replacing domain state machines. Register scope-owned EventBus subscriptions with
an unsubscribe token; preserve current priorities. Managers using the new response
infrastructure also own their timer/listener/completion-drain handles, making
shutdown quiescent without depending solely on AppDaemon cleanup.
Outstanding external service leases are process-broker resources, not abandoned
mechanism listener handles: they remain tracked/quarantined after domain shutdown.
Quiescence means no further domain mutation or unsent action dispatch, not a
claim that an already-handed-off physical service has been cancelled.

Restore assertion owners and output restrictions before initial publication, then
start scopes disabled and enable eligible live evaluation after configuration and
source admission. Diagnostic publication failure cannot prevent positive-alarm
ingestion. On termination, stop ingress/qualification before draining durable owner
writes; preserve the indoor clean/dirty checkpoint ordering. Reject completion
from the old runtime even if an external service remains outstanding.

## Acceptance and Traceability

FR-019..023; SC-009/010 -> SWR-SM-001..006 and existing fault/owner contracts.

Run one parametrized lifecycle matrix against all six real component adapters:
double start, double stop, same-instance restart, disable during qualification,
late listener/timer, failed cancellation and changed descriptive text. Assert
exact intended subscriptions, zero owned handles after successful stop, zero
obsolete owner-state changes or newly dispatched actions, independent retained
danger and unchanged domain
timing. Include source-session fields required by indoor recovery, forecast
derivative events, shared Entity Monitor listeners, shared heating sampling and
side-effect-free recovery simulation. Every existing fault/topic/entity ID remains.
Previously handed-off external calls remain explicitly in flight/unknown and are
tested separately; a generation fence cannot cancel their possible remote effects.
