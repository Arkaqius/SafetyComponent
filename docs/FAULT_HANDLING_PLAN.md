# Fault handling decisions, SM matrix, and task briefs

This is a discussion and delivery-planning record, not a replacement for the
normative HARA, SYS, SSRD, or feature architecture. It records the user's
2026-09-29 scope selection and proposals that still need review. No runtime
contract changes are implemented by this document.

Baseline inspected: `a2b5c17`, branch
`feature/public-repository-sanitization`. Local installation configuration
`backend/config/user_config.yml` and generated `backend/app_cfg.yaml` were absent;
the public example was inspected. No live installation claims are made.

Branch preparation base (2026-09-30): public `Arkaqius/SafetyComponent` main at
`ff8f4d3bdfdedb64aa13c29e6f130f62327fcbc4`. This is newer than the analysis
baseline above. Implementation/current-coverage claims in this reference retain
that older baseline; before implementation, reconcile the matrix with the public
checkout, including subsequently added monitors and faults. Publishing the plan
does not constitute a fresh runtime audit or implementation of its proposals.

Terminology: [Glossary](#0-glossary). Definitions describe this plan's target
architecture unless explicitly marked as legacy. They do not change current
runtime contracts or resolve the open policy choices listed at the glossary's end.

## 0. Glossary

### Core concepts and identity

| Term | Precise meaning in this plan |
| --- | --- |
| Hazard | A condition with potential for harm. It is the monitored situation, not a software object or a notification. |
| Safety Mechanism (SM) | A logical predicate that returns only a Boolean result when successfully evaluated on eligible inputs. Its computation may use a comparison, model, integral or observation window; it does not own a fault lifecycle or response policy. |
| Boolean result / predicate polarity | Whether the predicate's named condition holds. The proposed new-contract convention is `true` = violation present and `false` = violation absent for those inputs. A missing result or failed invocation is neither value. Existing polarity must be audited during migration. |
| Check | Informal name for one tested condition. Use an explicit SM/binding identity when specifying behavior; a check is not automatically a separate fault. |
| Monitor | An execution role that observes inputs and arranges checks. A monitor may invoke several SMs; failure-detecting checks feed faults, while passive inventory does not. The name alone implies no additional lifecycle. |
| Safety Component | The domain owner, such as Temperature or Safety Doors, that declares its required inputs, SM bindings, faults and response policies. It is not necessarily one physical sensor or one fault. |
| Subject | The concrete thing a condition concerns: a room, door, detector channel, provider, delivery target or actuator. Subject identity is retained even when several subjects share a fault. |
| Entity / entity ID | A Home Assistant state or service-facing object and its technical identifier. An entity may supply evidence about a subject; subject and entity are not interchangeable. One subject may need several entities. |
| Binding | The explicit association of an SM with a subject, input sources, fault-owned parameters and owning fault instance. An SM family ID alone is insufficient when that family serves multiple doors or rooms. |
| Contribution / contributor | An identified SM result associated with a binding and tracked by its owning fault. The contributor is the bound source of that result. Identity and execution metadata do not enlarge the SM's Boolean return type. |
| Symptom | Optional domain name for an identified Boolean contribution. In the target architecture it has no independent lifecycle, priority or response policy. The existing stateful `Symptom` class is a legacy implementation, not this target definition. |
| Cause | An identified reason contributing to a fault or restriction, such as a failed delivery path. It need not be a proven physical root cause. Several causes can remain active independently. |
| Fault | The policy-bearing runtime object that interprets its bound Boolean contributions, maintains activation/status, and owns configuration for qualification, priority, controls, degradation, responses and evidence. It is not the SM, the hazardous event itself, or its notification. |
| Fault definition / family | The reusable configured kind of fault and its policy, for example a door-open-timeout definition. It is distinct from the runtime instances created for individual doors. |
| Fault instance / fault ID | One runtime fault with a stable technical identity and its own state. It may aggregate many subjects or represent a single subject. Friendly translated names do not replace this identity. |
| Fault owner | The component/service accountable for a fault's interpretation and policy. Ownership does not require performing transport, storage or actuator calls inside the fault class. |
| FaultManager / execution service | Infrastructure that evaluates or advances configured faults and dispatches their effects. Separate notification, recovery and storage services execute fault-owned policies rather than redefining them. |
| Aggregation | An explicitly configured combination of identified contributions into a fault, or faults into a system summary. Aggregation does not by itself authorize dropping subject identity, evidence validity or timing. Qualification order remains a policy choice. |

### Evidence, eligibility and timing

| Term | Precise meaning in this plan |
| --- | --- |
| Evidence / observation | The input values, timestamps, quality information and relevant context used to support an evaluation. Evidence is not the Boolean result itself. |
| Validity / freshness | Whether an input satisfies its declared quality and age requirements for a particular use. A recent HA state update alone need not prove a fresh physical measurement. |
| Evaluation | One attempted application of a bound SM to its inputs. A successful eligible invocation produces a Boolean result; execution failure is reported separately to fault handling. |
| Eligibility / enable conditions | Prerequisites determining whether evaluation or an action is meaningful and allowed now, such as valid inputs, applicable operating mode and required capability availability. They are not evidence that the condition is false. |
| Failure qualification / debounce | Fault-owned criteria, often a time interval, required before observed failure evidence activates a fault. This is not an additional pending/confirmed DTC model. |
| Condition recovery / recovery qualification | Positive evidence that the monitored failure has ceased, satisfying the fault's configured clear criteria. It is distinct from executing a recovery action and may require its own time interval. |
| Hysteresis | Different entry and exit criteria that avoid toggling near a boundary. Thresholds belong to fault configuration; this is distinct from a time-based debounce. |
| Detection budget | The allowed time between a defined input/condition reference point and fault detection/activation. It is separate from the notification submission deadline. Concrete budgets require a defined start event. |
| Storage conditions | Rules determining whether and when diagnostic evidence is retained. Refusing or failing to store a snapshot is not evidence of condition recovery. |

### Fault lifecycle, controls and presentation

| Term | Precise meaning in this plan |
| --- | --- |
| Fault status | The public status describing the fault's evaluation/control situation using the eight values below. It does not alone determine `active`, latch or shadowing. Precedence in mixed situations remains to be finalized. |
| Active / activation | A qualified failure remains asserted until the configured release conditions are satisfied. Activation is the transition into that assertion, not every repeated true SM result. The proposed model preserves activation through unknown evidence and through an unreleased latch. |
| `NOT_EVALUATED` | The required evaluation has not yet established a result, for example during startup. It is not PASS; restored active evidence is retained. |
| `PASS` | Eligible evidence satisfies the configured non-failure/recovery criteria. A latched fault can still require explicit reset before deactivation. |
| `PENDING_FAILURE` | Failure evidence is undergoing fault-owned qualification; that evidence has not yet caused a new activation. It is not a separate diagnostic maturity bit. |
| `FAIL` | Eligible failure evidence meets the configured failure criteria. Notification success is not required for this status. |
| `PENDING_RECOVERY` | Positive recovery evidence is undergoing qualification. The existing activation remains until release requirements are satisfied. |
| `UNEVALUABLE` | Required evaluation cannot currently establish a trustworthy result because evidence or execution is unsuitable. Previously active evidence is not cleared. |
| Inhibition / `INHIBITED` | An authorized, temporary, scoped override with an expiry that suppresses the configured responses. It does not prove recovery or make invalid evidence usable. The door example continues observation; general evaluation/clear behavior during inhibition is still an open policy choice. |
| Disablement / `DISABLED` | An explicit exclusion with no automatic expiry, reversible by deliberate re-enablement. It remains visible in coverage and does not erase active evidence or a latch. Whether evaluation continues for every disabled fault is not yet settled. |
| Acknowledgement (ACK) | An operator indication that an alert has been seen, used to stop applicable repeats. It does not clear the condition, remove degradation, disable evaluation or reset a latch. |
| Latch / latched | A policy that retains fault activation after condition recovery until an authorized reset. Selected for the highest priority only; separate from notification acknowledgement and independent gas-output restrictions. |
| Reset | The authorized release of a latch after its required positive recovery evidence is present. It is not deletion of diagnostics, a sensor reset, or blanket authorization for physical actions. |
| Clear / deactivation / heal | Release of an active fault under its recovery and, where applicable, reset policy. Notification removal, loss of input and disappearance from the UI are not clear evidence. Prefer “condition recovered” when only the physical condition has recovered but a latch remains. |
| Shadowing / shadowed | Suppression of a redundant fault response because another fault explicitly covers it. Evaluation, evidence, activation, latches and restrictions are retained. It is not user inhibition or condition recovery. |
| `shadowed_by` | The proposed set of identities explaining which faults suppress a fault's response. Scope and activation rules must be explicit; priority alone does not establish this relation. |
| Fault response event | A transition consumed by notification/recovery services or their journal, such as `SET`, `CLEARED` or `SHADOWED`. It is distinct from the fault's eight-value MQTT evaluation status and does not replace its `active` or `shadowed_by` axes. |
| Fault lifecycle event | A reported transition or response change consumed by services/UI/history. An event is not a second fault object or a new activation merely because it was republished. |

### Classification, dependencies and coverage

| Term | Precise meaning in this plan |
| --- | --- |
| H fault | A fault representing a monitored hazard or operational equipment condition. The H category deliberately includes maintenance/cycling information, so it does not imply immediate danger or a particular priority. |
| D fault / functional-safety diagnostic fault | A fault representing impaired input quality, supervision or supporting system capability. It describes our diagnostic category, not an ASIL/certification claim. Each D allocation declares affected H capabilities, or an intentional empty internal target list. |
| Priority / level / notification level | One shared urgency ordering, L1 highest through L4 lowest. It selects response defaults; H/D classification, actuator permission and degradation targets remain separate configuration. |
| Capability | A scoped ability such as temperature evaluation, recovery execution, mobile notification, publication or durable-state retention. One component/fault may retain some capabilities while another is unavailable. |
| Dependency / consumer | An input or service required for a capability, and the component/capability using it. Dependency mappings declare actual use; they are not inferred from entity names. |
| Degradation | A reduction of a declared capability caused by a technical problem. It affects the specified subjects and consumers rather than automatically disabling an entire component. |
| Restriction | An enforceable, cause-keyed limit on evaluation or an action while its prerequisites are unsatisfied. Multiple restrictions may affect one capability; removing one cause does not remove the others. |
| D-to-H mapping / `degrades` | The explicit target H fault instances, capabilities and subject bindings affected by a D cause. It does not command those H faults to SET or CLEAR. Row aliases in the matrix must resolve to concrete installed bindings. |
| Coverage baseline | The explicitly declared set of required installation capabilities against which coverage is assessed. Uninstalled optional features are outside it; disabling a required feature must remain a visible exclusion. |
| System coverage | A summary of evaluability/enabled scope, independent of hazard urgency. The proposed labels are FULL, PARTIAL, DEGRADED and UNKNOWN; retain reasons and affected capabilities alongside the label. |
| `FULL` | Every required capability in the baseline is evaluable and enabled. FULL does not mean no hazard is active. |
| `PARTIAL` | Explicit user/configuration exclusions reduce baseline coverage; remaining required capabilities are evaluable. |
| `DEGRADED` | A known technical failure reduces at least one required capability. It need not affect unrelated components. |
| `UNKNOWN` | Available evidence does not establish coverage reliably, including incomplete startup assessment. It is not evidence that all capabilities have failed. |
| Provider adapter / provider D fault | The integration owning an external source's protocol, schema, polling and health, and the fault reporting its failure. Provider failure and loss of a consumer capability are distinct when redundant sources exist. |
| App Health / `SafetyAppHealth` | The proposed single D fault aggregating runtime infrastructure causes, with cause-specific restrictions. It is distinct from overall hazard severity and system coverage. Its name/identity remains a migration proposal. |
| Independent supervisor | A detector/reporting owner outside the failure boundary it monitors. Its independence is relative: being outside AppDaemon does not necessarily make it independent of HA, the host or the broker. |
| Groups A / B / C | A: explicitly selected externally owned safety dependencies. B: dependencies declared by components/core services. C: passive entity/device inventory, with no fault lifecycle by itself. An entity appearing in C can separately be monitored through A or B. |

### Responses and diagnostic records

| Term | Precise meaning in this plan |
| --- | --- |
| Response / handling policy | The fault-owned rules for notification, recovery, restrictions and operator controls. Separate services may execute the effects. A successful response does not by itself prove condition recovery. |
| Notification / vector / target | The operator-facing report; its delivery method (mobile, local alarm/light, dashboard); and its configured destination. Removing a notification is not clearing the fault. |
| Notification tag | The stable correlation key for notification updates/removal/ACK. It is a transport/lifecycle identifier, not a subject ID or fault episode. |
| Retry / repeat / quiet update | Retry attempts a delivery that failed or remains pending. Repeat deliberately re-alerts for an ongoing fault under its policy. Quiet update refreshes existing content without a new alert. They have different triggers and limits. |
| Delivery deadline / acceptance | The allocated time for notification submission and the transport's acknowledgement of that submission. HA acceptance is not proof that a physical phone displayed the notification. |
| Recovery action / recovery proposal | A configured mitigation action, or its current operator-visible offer. Modes are none, manual, user-confirmed or explicitly supported automatic execution. Neither a proposal nor a command acknowledgement clears the originating fault. |
| Postcondition | Observable evidence required to verify an action's result, such as a closed contact after a close command. It is distinct from the service accepting the command. |
| Freeze frame | A bounded snapshot of the evidence/context supporting a fault activation. Later source changes do not rewrite that captured evidence. Replacement/retention follow explicit storage policy. |
| Extended data | Bounded supplementary diagnostic metadata such as first/last failure time, last valid pass, activation count and last reason. It is not a continuous raw-data archive. |
| Persistence / durability | Storage and restoration of selected state across process restarts. A durability failure reports loss of that guarantee; it must not manufacture recovery or authorize command replay. |
| Fault episode | A separate historical occurrence identity/object with its own lifecycle. Excluded from this plan; bounded timestamps and activation counts do not introduce an episode subsystem. |
| FDC / pending-confirmed DTC / operation-cycle aging | Automotive-style failure counting, diagnostic maturity and cycle-based historical clearing mechanisms. Excluded; do not confuse them with the selected qualification timers or bounded storage retention. |

### Definitions do not settle these review decisions

The glossary fixes vocabulary, not the following outstanding behavior choices:

- Per-contributor versus aggregate qualification, including timer ownership and
  mixed-evidence status precedence.
- The exact ordering between input invalidity, immediate evaluation restrictions
  and qualified diagnostic activation.
- Fault-wide versus subject-scoped shadowing and migration of existing relations.
- Which new App Health causes require renewed attention after an existing ACK,
  and how application/supervisor ownership is reconciled across restart/outage.
- Evaluation and condition recovery during inhibition/disablement, plus the
  complete allowed combinations of status, activation, latch and controls.

These remain design decisions for the relevant FH tasks. Listing them here does
not approve the review's proposed solutions or silently change section 2.

## 1. Selected scope

| Topic | Decision |
| --- | --- |
| Safety Mechanism boundary | An SM is a logical predicate returning only `true` or `false`, regardless of computational complexity. Faults own lifecycle, handling logic, and their configuration. |
| Symptoms | No separate symptom lifecycle or policy layer. If the term is retained, it denotes an identified Boolean contribution tracked by its owning fault, not another stateful domain object. |
| Safety Doors | Separate fault for every door/gate; replace the shared `SafetyDoorOpenTimeout` aggregation through a coordinated migration. |
| Fault categories | Distinguish monitored hazard/operational faults (H) from functional-safety diagnostic faults (D): self-diagnostics, sensor/input quality, provider availability, and lost supervision. Each D declares its affected H faults and capabilities. |
| Group B | Aggregate component dependency symptoms by lost capability, preserving every affected subject and consumer. |
| Monitors currently bypassing faults | Bring failure-detecting self-diagnostic and dependency monitors into the fault model; health telemetry or logs alone are insufficient. |
| Provider diagnostics | Provider adapter failures are real D faults, distinct from the consumer's loss of a required capability. |
| Application diagnostics | Aggregate application, delivery, persistence, MQTT and shared execution failures into an app-health D fault with cause-specific effects. |
| Degradation | Limit the effect to dependent component/capability/subject; independent functions continue. |
| User control | Support temporary inhibition and permanent disable, with visible scope and duration/reason. |
| Rich fault status | Include `NOT_EVALUATED`, `PASS`, `PENDING_FAILURE`, `FAIL`, `PENDING_RECOVERY`, `UNEVALUABLE`, `INHIBITED`, `DISABLED`. |
| System coverage | Include `FULL`, `PARTIAL`, `DEGRADED`, `UNKNOWN`. |
| Priority | One level 1..4 is both fault priority and notification level; it selects handling defaults, while explicit fault configuration selects recovery/degradation targets and permissions. |
| Highest-priority latch | Include latching for the highest priority. |
| Freeze frame and extended data | Include bounded diagnostic evidence and counters/timestamps. |
| Enable/storage conditions | Handle eligibility with degradation/user control; no independent automotive subsystem. Storage remains a separate evidence-retention decision. |
| Pending/confirmed DTC | Excluded as an additional maturation model. |
| Fault Detection Counter | Excluded. |
| Fault episode model | Excluded; do not add episode IDs, episode entities, or episode lifecycle storage. |
| Operation cycles, aging, DTC byte, UDS | No automotive cycle/aging machinery or DTC protocol is included. Bounded storage retention is still necessary. |

Group C inventory and measurement helpers remain data sources; any actual
failure-detection logic within those helpers needs an owning diagnostic fault.

## 2. Semantic decisions to settle before implementation

The SM/fault responsibility boundary below records the user's clarification.
Detailed fault policies that follow remain proposals to settle before implementation.

### Boolean mechanisms, fault-owned interpretation

An SM answers one logical question. Its result is strictly Boolean: no fault
status enum, priority, notification, recovery command, or policy object is returned.
The predicate can be a simple comparison or a computation over a model, integral,
or observation window; computational complexity does not change this boundary.
Computational history is not a fault lifecycle.

The fault owns input/subject bindings, predicate parameters, aggregation rules,
qualification/debounce, recovery qualification, enable conditions, the eight
statuses, priority, latch, user controls, degradation policy, notification/recovery
policy, and evidence-retention policy. Thresholds are supplied to a predicate from
fault-owned configuration; an SM does not independently load handling policy.
Shared managers may execute those policies without duplicating ownership.

Proposed polarity for new predicate contracts: `true` means the named violation
is present; `false` means it is absent for the evaluated inputs. Existing SM
polarity and signatures require an explicit migration audit, not silent inversion.
The fault aggregates identified Boolean results and applies its own lifecycle.
Upper layers consume faults and capability coverage, not individual check logic.

Invalid input or a failed invocation is not a fabricated `false`. Fault-owned
eligibility uses input-health evidence (which can itself come from Boolean
diagnostic SMs); if required evaluation cannot run, the fault records UNEVALUABLE
or NOT_EVALUATED as appropriate and preserves active evidence. The execution
infrastructure reports invocation failure to fault handling, not as a third SM
return value. Raw inputs and execution metadata remain available to the fault
for freeze-frame capture; they are not extra fields in the SM's Boolean result.

For example, a stale room reading activates an input-health fault and prevents
the dependent temperature fault from interpreting an old comparison as recovery.
No UNKNOWN/PENDING/INHIBITED state is introduced on the temperature SM itself.

The current `Symptom` class contains state and parameters; the target above is
a migration direction, not a claim that today's implementation has this boundary.

### Fault status and active condition

Keep the requested eight values as a diagnostic status exposed by the fault,
computed by fault-owned logic from Boolean results and evaluation eligibility.
Retain an independent `active` flag and
the active contributor set. This allows an active fault to become `UNEVALUABLE`
or `INHIBITED` without reporting recovery. Expose `latched` separately for the
highest-priority policy. Shadowing remains response/presentation metadata.

### Shadowing: preserved behavior and target representation

Shadowing is already implemented, not a new exclusion or a synonym for recovery.
The internal `FaultState.SHADOWED` response event withdraws redundant handling;
`RiskyTemperature.shadows` names `RiskyTemperatureForecast`. NotificationManager
removes the same-tag notification with `clear_notification`, drops pending delivery
and repeats, and distinguishes this from a resolved message. RecoveryManager's
SHADOWED handler withdraws recovery guidance. The current relation is fault-wide,
not a room-specific rule. See the [fault implementation](../backend/components/faults_manager/fault_manager.py),
[notification lifecycle](<features/Mobile Notification Delivery - Architecture.md#44-fault-clear-and-shadow>),
and [recovery contract](<features/Recommended Actions and Recovery - Architecture.md>).

Publish shadowing as `shadowed_by` (a set of fault identities), orthogonal
to the eight evaluation statuses and `active`/`latched`. A forecast may therefore
remain `FAIL`, active, and shadowed by a direct hazard. It is not PASS, INHIBITED,
or DISABLED. The `SHADOWED` event/history code describes response withdrawal;
the MQTT fault state remains the evaluation status.

- Shadowing removes redundant notification and withdraws the shadowed fault's
  recovery proposals; it does not erase evidence, release a latch, or remove
  safety restrictions imposed by that fault.
- Keep evaluating Boolean SMs. When the final shadowing cause disappears,
  reevaluate eligibility and present a still-active condition again. This is not
  a new physical activation or a reason to replace its original freeze frame.
  Never present invalid data as recovery during unshadowing.
- Default shadow relation remains the existing fault-wide relation. Subject-scoped
  shadowing requires an explicit policy/migration, not an implicit room filter.
- FH-01/FH-02 tests must cover multiple shadow owners, shadowed recovery withdrawal
  for the correct target fault, restart, unshadowing, and invalid evidence.

The following transition table concerns evaluation/activation, not shadowing.

`PENDING_FAILURE` and `PENDING_RECOVERY` describe existing time/debounce
qualification. They do not introduce a separate pending-DTC/confirmed-DTC model.

| Situation | Evaluation/status | Active condition |
| --- | --- | --- |
| First evaluation not complete | `NOT_EVALUATED` | No newly proven failure; restored active condition is preserved. |
| Valid evidence passes recovery policy | `PASS` | Clears for an auto-healing fault; a highest-priority latch awaits a permitted reset. |
| Failure qualification in progress | `PENDING_FAILURE` | No new activation yet. |
| Qualified failure | `FAIL` | Active. |
| Recovery qualification in progress | `PENDING_RECOVERY` | Remains active. |
| Required evidence invalid or absent | `UNEVALUABLE` | Preserve any previously active condition. |
| User temporarily inhibits a subject | `INHIBITED` | Preserve existing evidence; apply explicit response inhibition policy. |
| User/configuration disables a subject | `DISABLED` | Do not fabricate recovery or discard an active latch. |

For an aggregate, the fault applies its configured combination rule to eligible
Boolean contributions, then its own qualification/recovery policy. It retains
subject identity and evaluation eligibility as internal evidence, not independent
SM state machines. Partial missing evidence must not clear an active contribution;
positive violation evidence from another subject remains actionable. FH-01 must
define and test fault-status precedence for these mixed-evidence cases, including
scoped inhibition. Never calculate `active` solely from a display label.

### Coverage is independent of hazard severity

Proposed definitions, relative to the declared installation coverage baseline:

| Coverage | Meaning |
| --- | --- |
| `FULL` | All required capabilities are currently evaluable and enabled. An active hazard can coexist with FULL coverage. |
| `PARTIAL` | Known user/configuration exclusions reduce the declared coverage; all remaining required paths are evaluable. |
| `DEGRADED` | A known technical failure reduces a required capability. |
| `UNKNOWN` | Coverage cannot be reliably established, including incomplete startup assessment. |

Expose exclusions and affected capabilities regardless of the aggregate label.
Proposed precedence: known technical loss -> `DEGRADED`; otherwise unresolved
coverage -> `UNKNOWN`; otherwise explicit exclusions -> `PARTIAL`; else `FULL`.
Uninstalled optional capabilities are outside the baseline. Disabling a previously
required capability must remain visible rather than silently shrinking it.
Keep the existing severity summary separate from this coverage summary.

### Priority and responses

Use the existing fault `level` 1..4 as priority AND notification level: P1 = L1,
P2 = L2, P3 = L3, P4 = L4. Do not introduce a second independent notification
severity. `H`/`D` classification describes meaning, not urgency. Existing levels
are retained; newly allocated levels in section 3 are explicit design proposals,
not a completed risk reassessment.

The notification baseline is [SYS section 4](<sys/SafetyConcept - SYS.md#4-notifications>),
the [mobile profiles](<features/Mobile Notification Delivery - Architecture.md>),
and `runtime_defaults.notification` in [system configuration](../backend/config/system_config.yml).

| Priority = level | Notification / UI profile | Submission target / repeat | Proposed latch / user-control default |
| --- | --- | --- | --- |
| P1 = L1 | High-priority mobile; eligible configured alarm and yellow light; HAZARD card. Android max/high; iOS time-sensitive, not critical by default. | 10 s; current repeat interval 60 s, max 3, stopped by ACK. | Latch; ACK allowed; ordinary operator inhibit/disable denied. |
| P2 = L2 | High-priority mobile; eligible configured yellow light; HAZARD card. Android high/high; iOS time-sensitive. | 30 s; transport retries, no L1 alarm repeats. | No latch; inhibit/disable denied unless explicitly allowlisted (door maintenance is allowed). |
| P3 = L3 | Mobile warning and WARNING card, no default local alarm/light. Android default/normal; iOS active. | 30 s; transport retries, no L1 alarm repeats. | No latch; explicit override allowlist only. |
| P4 = L4 | INFO dashboard only; no mobile delivery or local annunciation. | Best effort; no mobile retry/repeat. | No latch; explicit override allowlist only. |

Current transport retry policy is max 3 attempts, base delay 5 s, cap 60 s.
Deadlines measure submission, not proof of receipt by a physical phone, and are
not detector debounce budgets. Quiet updates, ACK refreshes and resolved messages
use normal/alert-once Android delivery and passive iOS interruption. SHADOWED uses
removal, not a resolved alert. SYS also specifies Sleep/Local-Only behavior; this
plan preserves that requirement without claiming every mode is implemented.

### How priority maps into fault configuration

Priority selects handling defaults, not the hazard algorithm or a universal
actuator action. The following is the target logical configuration contract;
new field names are design notation, not keys accepted by today's YAML schema.

| Fault configuration concern | Mapping / ownership | Can priority alone determine it? |
| --- | --- | --- |
| `level` | Existing per-fault value; selects notification profile of the same number, deadline, repeats, UI urgency and latch/control defaults above. | Yes, for these defaults. |
| `class`, owner, SM/subject bindings, parameters, aggregation, failure/recovery qualification | Explicit fault definition; SM still returns only Boolean. | No. |
| Notification destinations and allowed vectors | Installation binds services/entities; level selects profile. Hazard/output restrictions can veto a vector, never authorize an unsafe one. | Profile yes; physical targets/eligibility no. |
| `recovery` | Explicit mode `none`, `manual`, `user_confirmed` or supported `automatic`, action binding, prerequisites and postcondition. Every level uses the same eligibility gate. Default is `none`. | No; P1 does not mean automatic actuation. |
| `degrades` | Explicit list of target H fault, capability, subject mapping, cause and restoration evidence. Empty list must be intentional. Apply before dependent recovery and independently of notification/ACK/shadowing. | No; P3 can block P1 evaluation on an invalid detector input without changing either fault's level. |
| Latch/reset | P1 latch only; fresh recovery plus authorized reset. P2..P4 auto-heal after their recovery policy. | Level selects latch; recovery evidence remains fault-specific. |
| User control | Level constrains eligibility; per-fault allowlist specifies temporary/permanent control and bounds. Muting D warnings never restores invalid data. | Only the default/ceiling, not permission by itself. |
| `shadows` | Explicit fault relation; no automatic suppression solely because another fault has a higher priority. | No. |
| Freeze frame / extended data | Bounded capture on activation and explicit retention/allowlist. All matrix faults inherit this policy. | No; retain diagnostic evidence at all levels. |

For example, proposed `TemperatureRecoveryUnavailable` has class D, level 3,
notification profile 3, no latch, and no automatic repair. Its explicit
`degrades` list targets `RiskyTemperature` and `RiskyTemperatureForecast`, only
their affected room's recovery capability. It does not disable temperature
detection. `SafetyDoorOpenTimeout{DoorKey}` instead uses level 2, no recovery
action by default, and explicitly permits temporary/permanent operator control.

Resolution order: validate configuration and bindings; apply evaluation/input
eligibility; aggregate Boolean evidence and advance fault state; capture evidence
and apply restrictive effects; evaluate explicitly configured recovery under all
restrictions; dispatch eligible notification vectors. Notification/storage failure
must not block restrictions. Restrictions remain until all causes have recovered.
Do not let a generic per-fault override silently change L3 into an L1 mobile profile,
enable lower-priority latching, or bypass hazard-specific actuation restrictions.

Highest-priority reset is distinct from acknowledgement: require authoritative
recovery of every active contributor plus explicit authorized reset. Invalid
input, restart, or user disable cannot release the latch. Existing gas electrical
switching inhibition is a distinct protection and must not be released implicitly
by resetting the alarm. Exact reset permissions remain an implementation decision.

Recovery is evaluated only where an action is defined and currently eligible;
priority alone never authorizes actuation. Apply restrictive degradation before
evaluating a dependent recovery. Delivery/storage failure cannot block detection
or degradation enforcement.

## 3. SM-to-fault matrix: current code and proposed target

This is one catalog for implemented mechanisms, new allocations and documented
future mechanisms. New names are proposals, not reserved runtime identifiers.
`H` includes hazards and operational equipment conditions; `D` means loss of
diagnostic/supervision or supporting capability. A device's maintenance code is
an H operational condition, not automatically a D loss of our monitoring.

Baseline: **I** = implemented fault/SM baseline; **R** = existing monitoring to
reroute/refactor; **N** = new fault integration; **F** = documented future feature.
These flags describe current evidence, not extra runtime states.

Every fault row specifies owner, Boolean source/subject, class/level, recovery,
and D-to-H effects. Notification, latch, control defaults and bounded evidence
inherit section 2 for that exact level. All new D allocations below use L3 for
component/provider loss, or proposed L2 for app-health infrastructure loss;
these are reviewable priorities, not automatic escalation to life-safety L1.
D faults default to operator repair guidance, not automatic repair/restart.

### Target lists and degradation semantics

Each D entry below has an explicit target list, including an intentional empty
list where the monitored automation is external. Row references identify the
named H faults in this same catalog; they are not deployable identifiers.
Configuration must resolve them into exact fault IDs and subject bindings.

- `H-TEMP` = M01 `RiskyTemperature`, M02 `RiskyTemperatureForecast`.
- `H-EXT` = M04 `ExternalWeatherExposure`, M05 `OutdoorAirQualityExposure`.
- `H-IEHM` = M07 `InternalSmokeDetected`, M08 `InternalFlammableGasDetected`,
  M09 `InternalCarbonMonoxideDetected`, M20 `InternalParticulateMatterHigh`,
  M21 `InternalParticulateMatterExposure`.
- `H-HEAT` = M23 `HeatingDeviceFault`, M24 `HeatingMissingDemand`,
  M25 `HeatingNoResponse`, M26 `HeatingInsufficientOutput`,
  M27 `HeatingDistributionSuspected`, M28 `HeatingRoomDeliveryInsufficient`,
  M29 `HeatingExcessTemperature`, M30 `HeatingCyclingDiagnostic`,
  M31 `HeatingMaintenance`.
- `H-ALL` = H-TEMP + M03 `SafetyDoorOpenTimeout{DoorKey}` + H-EXT +
  H-IEHM + H-HEAT. Expand only installed/configured instances. Future definitions
  do not create missing-component alarms in today's installation.

Targets mean loss of a named capability, NOT setting or clearing the H fault.
An `evaluation` restriction affects only the declared input/subject; positive
alarm evidence on independent valid channels remains actionable. `recovery`,
`notification`, `publication`, and `durability` restrictions leave hazard
detection running wherever its own prerequisites remain valid. The target list
is narrowed by the failed contributor, never applied wholesale by class/priority.

### Unified allocation matrix

| Row / baseline | Owner | Boolean source / aggregation scope | Fault: current -> target | Class / level | Recovery / special response | D: affected H fault list | Capability and subject restriction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M01 / I | Temperature | `sm_tc_1`, `sm_tc_3`; direct low/high by room | `RiskyTemperature` retained | H / L2 | Existing low-temperature recovery only when eligible; shadows M02 | Not D | Hazard itself does not disable monitoring. |
| M02 / I | Temperature | `sm_tc_2`, `sm_tc_4`; forecast low/high by room | `RiskyTemperatureForecast` retained | H / L3 | Configured low-temperature guidance/recovery; shadowed by M01 | Not D | Keep forecast evidence while its response is shadowed. |
| M03 / R | Safety Doors | `sm_safety_door_open_timeout`; one door/gate | Shared `SafetyDoorOpenTimeout` -> `SafetyDoorOpenTimeout{DoorKey}` | H / L2 | None by default; per-door temporary/permanent override allowed | Not D | One subject, no effect on other doors or contact health. |
| M04 / I | External Hazard | `sm_ext_weather_exposure`; hazard x opening | `ExternalWeatherExposure` retained | H / L2 | Manual closure or eligible user-confirmed directional cover closure | Not D | Explicit postcondition and conflict checks. |
| M05 / I | External Hazard | `sm_ext_outdoor_air_quality_exposure`; opening | `OutdoorAirQualityExposure` retained | H / L3 | Manual closure / explicitly supported confirmed closure | Not D | Constrain conflicting ventilation advice, not all monitoring. |
| M06 / I | External Hazard | `sm_ext_provider_unavailable`; required weather/AQ capability | `ExternalHazardDataUnavailable` retained | D / L3 | Repair required data path; no actuation | H-EXT | Evaluation/advice/recovery requiring the missing capability only; retain independent valid weather/AQ evidence. |
| M07 / I | Internal Environmental Hazard | `sm_iehm_smoke`; detector | `InternalSmokeDetected` retained | H / L1 | Latch, smoke guidance; no RecoveryManager actuator proposal | Not D | Hazard-specific notification/output eligibility. |
| M08 / I | Internal Environmental Hazard | `sm_iehm_flammable_gas`; detector | `InternalFlammableGasDetected` retained | H / L1 | Latch, gas guidance; no recovery actuator proposal | Not D | Preserve separate electrical-switching prohibition. |
| M09 / I | Internal Environmental Hazard | `sm_iehm_carbon_monoxide`; detector | `InternalCarbonMonoxideDetected` retained | H / L1 | Latch, CO guidance; no recovery actuator proposal | Not D | Hazard-specific guidance; ACK is not clearance. |
| M10 / I, F for PM | Internal Environmental Hazard | `sm_iehm_detector_health`; detector/channel/cause | `InternalEnvironmentalDetectorUnavailable` retained | D / L3 | Repair affected detector/input; no duplicate Group B fault | H-IEHM | Evaluation only for the failed detector's actual smoke/gas/CO/PM channels; healthy channels continue. |
| M11 / I | Entity Monitor; explicit Group A | `sm_entity_health_<entity_key>`; checks x selected external entity | `EntityHealth{EntityKey}` retained | D / L3 | Manual external dependency repair | [] for Group A-only external automations; if also consumed internally, use M12..M16's explicit list and single owner | Declare external automation coverage; never infer internal H dependencies from entity domain/name. |
| M12 / R | Requesting component: Temperature in this instance | Group B input-health Boolean checks; room temperature and required forecast computation | Per-entity faults -> `TemperatureMonitoringUnavailable` | D / L3 | Repair measurement/computation path | H-TEMP | Evaluation by room and direct/forecast capability; derivative-only failure must not disable direct comparison. |
| M13 / R | Requesting component: Temperature recovery | Group B contact/actuator/required recovery-input checks; failed command/postcondition | Per-entity faults/logs -> `TemperatureRecoveryUnavailable` | D / L3 | Manual path repair; no automatic command replay | H-TEMP | Recovery for the affected room/proposal only; direct/forecast evaluation continues if its inputs are valid. |
| M14 / R | Requesting component: Safety Doors | Group B door/condition input-health checks | Per-entity faults -> `SafetyDoorMonitoringUnavailable` | D / L3 | Repair contact/condition input | M03 `SafetyDoorOpenTimeout{DoorKey}` | Evaluation of affected door only; preserve previously active timeout evidence. |
| M15a / R | Requesting component: External Hazard | Group B opening-contact checks | Per-entity faults -> `ExternalOpeningMonitoringUnavailable` | D / L3 | Repair contact path | H-EXT | Exposure evaluation for affected opening; provider ingestion continues. |
| M15b / N | Requesting component: External Hazard recovery | Required actuator/postcondition checks; failed command/readback | Partial dependency coverage/logs -> `ExternalRecoveryUnavailable` | D / L3 | Manual path repair; no command replay | H-EXT | Recovery only for dependent opening/proposal; keep other exposure detection and advice. |
| M16 / R | Declared shared-input owner; consumers register their use | Shared outside-temperature/common-input checks | Per-entity fault -> requesting component's existing D fault where there is one consumer; proposed `CommonInputUnavailable` for genuinely shared inputs | D / L3 | Repair common source; one owner, multiple consumer effects | H-TEMP; H-EXT; M03; H-HEAT, only where explicit dependency bindings exist | Each declared consumer capability/subject; no arbitrary all-component shutdown or duplicated entity-health fault. |
| M18a / N | OpenMeteoWeatherApiComponent | Adapter timeout/schema/availability/freshness checks, by provider | Health telemetry -> `ExternalProviderUnavailable{OpenMeteoWeather}` | D / L3 | Repair provider path; existing bounded polling continues | M04 `ExternalWeatherExposure` | Remove invalid provider evidence; restrict only weather sub-capabilities needing it, not AQ or independent IMGW warnings. |
| M18b / N | ImgwWarningsApiComponent | Adapter timeout/schema/availability/freshness checks, by provider | Health telemetry -> `ExternalProviderUnavailable{ImgwWarnings}` | D / L3 | Repair provider path; polling continues | M04 `ExternalWeatherExposure` | IMGW-dependent warning coverage only; retain valid Open-Meteo observations. |
| M18c / N | OpenMeteoAirQualityApiComponent | Adapter timeout/schema/availability/freshness checks, by provider | Health telemetry -> `ExternalProviderUnavailable{OpenMeteoAirQuality}` | D / L3 | Repair provider path; polling continues | M05 `OutdoorAirQualityExposure`; M01, M02, M20, M21 only if their advice requires outdoor AQ | AQ exposure/advice eligibility, not unrelated temperature or indoor smoke/gas/CO detection. |
| M20 / F | Internal Environmental Hazard | `sm_iehm_pm25_high`; sensor/window | `InternalParticulateMatterHigh` (documented) | H / L2 | Hazard guidance only; no automatic ventilation/purification proposal | Not D | Preserve smoke/gas/CO advice restrictions. |
| M21 / F | Internal Environmental Hazard | `sm_iehm_pm25_exposure`; sensor/long window | `InternalParticulateMatterExposure` (documented) | H / L3 | Guidance only; require sufficient window coverage | Not D | No inferred safe exposure through missing samples. |
| M22 / F | Heating System | `sm_hsm_supervision_loss`; feed/measurement/interpretation | `HeatingSupervisionLoss` (documented) | D / L3 | Repair supervision path; no boiler actuation | H-HEAT | Affected feed/mode/measurement only; valid absolute-temperature checks and native boiler protection remain independent. |
| M23 / F | Heating System | `sm_hsm_device_fault`; device/model code | `HeatingDeviceFault` (documented) | H / L3 | Operator diagnostic/service guidance; no automatic reset | Not D | Equipment failure is distinct from lost supervision. |
| M24 / F | Heating System | `sm_hsm_missing_demand`; room/request | `HeatingMissingDemand` (documented) | H / L3 | Operator guidance, no boiler control | Not D | Eligible room demand only. |
| M25 / F | Heating System | `sm_hsm_no_response`; request/boiler | `HeatingNoResponse` (documented) | H / L3 | Operator guidance, no boiler control | Not D | Respect bounded startup/inhibition conditions. |
| M26 / F | Heating System | `sm_hsm_no_flow_rise`, `sm_hsm_flow_tracking` | `HeatingInsufficientOutput` (documented) | H / L3 | Operator guidance, no boiler control | Not D | Eligible output/flow observation window. |
| M27 / F | Heating System | `sm_hsm_pump_mismatch`, `sm_hsm_flow_return` | `HeatingDistributionSuspected` (documented) | H / L3 | Operator guidance, no pump command | Not D | Declared topology and eligible load. |
| M28 / F | Heating System | `sm_hsm_room_delivery`; room/demand | `HeatingRoomDeliveryInsufficient` (documented) | H / L3 | Operator guidance, no actuator command | Not D | Affected room; retain independent C-TEMP protection. |
| M29 / F | Heating System | `sm_hsm_mode_overtemperature`, `sm_hsm_absolute_overtemperature` | `HeatingExcessTemperature` (documented) | H / L2 | Urgent guidance; no invented boiler safety-control action | Not D | Mode-specific and absolute checks retain separate eligibility. |
| M30 / F | Heating System | `sm_hsm_short_cycling`; mode/window | `HeatingCyclingDiagnostic` (documented) | H / L4 | Dashboard diagnostic guidance only | Not D | Operational efficiency condition, not supervision failure. |
| M31 / F | Heating System | `sm_hsm_maintenance`; manufacturer indication | `HeatingMaintenance` (documented) | H / L4 | Dashboard maintenance guidance only | Not D | Fresh manufacturer-defined evidence. |
| M17a / N | App Health; bootstrap/external supervisor for outage | Invalid configuration, initialization failure, stopped/unhealthy process | `safety_app_health` telemetry -> proposed `SafetyAppHealth`, cause startup/process | D / L2 | Operator intervention; no automatic restart; independent reporting path | H-ALL | Only affected component if isolated; all installed H evaluation/reporting on whole-process outage. External observer must not claim live internal states. |
| M17b / N | App Health / publication runtime | MQTT connection/publication/missing heartbeat | Telemetry -> same `SafetyAppHealth`, cause publication | D / L2 | Restore transport; independent observer for broker loss | H-ALL | Publication/UI freshness for affected topics; do not stop independent in-process detection or working delivery. |
| M17c / N | App Health / notification delivery | Target submission exhaustion, sustained queue/deadline failure, required WAN loss | Delivery health telemetry -> same `SafetyAppHealth`, cause delivery | D / L2 | Bounded existing retries; operator channel repair | H-ALL L1..L3 instances using the failed target; [] for dashboard-only L4 | Notification target/path only; surviving mobile/local channels continue. No assumption of handset receipt. |
| M17d / N | App Health / local annunciator | Actual configured-output command/verification failure | Logs -> same `SafetyAppHealth`, cause local output | D / L2 | Repair output; no automatic actuator test | M07, M08, M09 for eligible alarm/light; M01, M03, M04, M20, M29 for eligible L2 light | Failed notification vector only. Deliberate gas switching prohibition is not an output failure. |
| M17e / N | App Health / state stores | Load/save failure; notification/recovery/hazard/fault store and guarantee | Logs/telemetry -> same `SafetyAppHealth`, cause persistence | D / L2 | Repair store; no evidence deletion/reset | H-ALL, narrowed to consumers of the failed store | Durability/restart guarantees only; uncertainty blocks unsafe reset/replay, not valid current detection. |
| M17f / N | App Health / evaluation runtime | SM invocation/init failure or shared execution failure not already owned by component D | Logs/SM error -> same `SafetyAppHealth`, cause evaluation | D / L2 | Repair runtime; no automatic reconfiguration | H-ALL, exact H/subject bindings of the failed invocation | Evaluation of affected bindings only; known component input/model failures belong to M12/M22 instead, never duplicate faults. |
| M17g / N | App Health / recovery runtime | Shared recovery dispatcher failure, not a component actuator failure | Logs -> same `SafetyAppHealth`, cause recovery infrastructure | D / L2 | Repair dispatcher; no command replay | H-TEMP, H-EXT where a recovery action is configured | Recovery dispatch only; per-actuator/postcondition failures belong to M13/M15b, not another runtime fault. |

### Ownership, aggregation and later implementation

M12 is an instance of a general allocation rule: the component requesting the
monitoring owns the fault and declares which capability is lost. Entity Monitor
provides reusable Boolean checks; it does not choose a generic fault solely from
the physical sensor type. Thus temperature *evaluation* and temperature *recovery*
have different D allocations even if a shared contact/sensor participates in both.
M13/M15b aggregate dependency and execution evidence when they describe the same
lost recovery capability. A rejected actuator command or postcondition timeout
is retained as its own contributor under the existing D fault and exact H
binding. Service acceptance does not clear it; observed postcondition evidence
does, including after manual repair. Outstanding failures are stored across
restart without replaying the command. New components must declare the
equivalent allocation.

A shared input has one diagnostic owner and explicit fan-out to all consumers.
Do not create both Group A and component faults for the same failure. Resolve
M16's owner and concrete targets during configuration compilation; an undeclared
internal consumer is a validation error, not a wildcard degradation target.

Provider adapter failure is always a real D condition (M18a..c), even where a
redundant source keeps a consumer operational. M06 is a distinct, derived
*capability-loss* fault and only activates when the consumer's required evidence
is insufficient. Record provider causes explicitly so redundant input is not
discarded and restrictions are not double-counted. If M06 and a provider D both
need response deduplication, configure an explicit shadow relation scoped to the
covered provider/capability; never infer shadowing from priority. This extends the
existing fault-wide shadow contract and needs dedicated migration/tests.

App Health is one logical D fault, not seven unrelated top-level faults.
M17a..g are its Boolean contributors with one level and independent restriction
targets. Recovering MQTT cannot clear an active persistence/delivery cause.
Retain `sensor.safety_app_health` as application-health telemetry, not a
projection of a D fault. Exact new App Health fault identity requires a
coordinated consumer change.

Passive Group C inventory and valid measurement values have no fault lifecycle.
A failed required derivative belongs to its requesting component's D fault (M12
for temperature forecasting), or App Health for a shared execution failure.
Provider failures are explicitly excluded from this informational category.

Per-door routing cannot be implemented by copying the same `related_sms` entry
into multiple faults: the current resolver rejects multiple matches. Add explicit
subject binding while preserving the existing SM family ID where possible.

F rows belong to the same target catalog and later implementation scope, not
today's runtime coverage. Reconcile their source documents' incident/episode
terminology with the rejected FaultEpisode model before implementation.
The heating and PM feature implementations remain separate from the FH framework
tasks; this document does not claim those features are already implemented.

### Mandatory fault integration for bypassing monitors

This checklist closes section 3; its allocations are already merged into the
matrix, not maintained as a second catalog.

- Integrate every current failure detector into M12..M18/M17 or a documented
  component-owned D fault; actual provider diagnostics cannot remain telemetry-only.
- Use the row's class, level, recovery policy and explicit H-target/capability list.
  Validate each binding; distinguish intentional external-only [] from missing
  allocation. No unresolved priority or unbounded runtime wildcard is acceptable.
- Qualify failure/recovery in the fault, never in a new stateful SM/symptom layer.
  Historical error counters alone do not prove a current failure.
- Normal user decline, confirmation expiry and intentional output inhibition
  are not technical failures. A failed issued command or verified missing
  postcondition contributes to the appropriate component recovery D fault.
- Notification failure must not recursively create more app-health faults when
  the app-health notification fails. Use the same stable cause, bounded retry,
  and available independent reporting. App Health's own delivery follows this
  rule even though its H-target list describes downstream hazard services.
- Allocate out-of-process detection for process/broker loss. An HA-hosted
  supervisor can observe an app outage but cannot promise detection of total
  HA/host loss; supervisor placement and independent reporting are FH-08 decisions.
- Test partial recovery, multiple active causes, provider redundancy, component
  isolation, shadowing, and retained active hazards with unavailable evidence.

## 4. Cross-cutting acceptance examples

1. Entrance door maintenance for one hour affects only that door's timeout fault.
   Other doors and entrance contact-health checks remain enabled. Continue
   observing/counting elapsed open time. Expiry reevaluates current evidence
   without restarting a complete timeout; unavailable input cannot invent PASS.
2. Applying inhibition to an already active fault records the control change and
   suppresses only authorized responses. It never emits a healed notification.
   A persisted absolute expiry survives restart without extending the interval.
3. Muting/overriding a freshness diagnostic never makes stale input usable.
   Degradation follows evidence validity even if its warning is inhibited.
4. Stale kitchen temperature preserves an existing kitchen hazard, marks its
   evaluation UNEVALUABLE, and blocks only dependent decisions/recovery. Other
   rooms continue. Recovery requires fresh successful evidence, not merely
   removal of an override or disappearance of a notification.
5. Several faults can restrict the same capability. Removing one cause does not
   restore it while another cause remains. Restriction handling is idempotent;
   restoring capability triggers reevaluation with current inputs.
6. A latched priority-1 fault survives restart and acknowledgement. Reset requires
   valid recovery evidence and authorization; unknown input prevents reset.
7. Freeze frame captures first activation input values/units, source timestamps,
   age/quality, thresholds/timers, subject, priority, configuration fingerprint,
   and active restrictions. Capture before asynchronous processing can change
   the evidence. Allowlisted fields and bounded payloads exclude secrets.
8. Extended data stores first/last failure times, last valid pass, activation
   count, duration where trustworthy, and last diagnostic reason. Add explicit
   clock uncertainty; do not manufacture elapsed observations during downtime.
   Repeated context updates do not increment activation count. Define bounded
   replacement/retention without operation-cycle aging or a FaultEpisode model.
9. Snapshot storage failure does not block notification, detection, degradation,
   or existing active-state persistence. Administrative evidence deletion is
   separate from physical recovery and is outside normal acknowledgement.

## 5. Separate task briefs and prepared branches

The eight branches below are prepared from the public main base identified above,
with one shared documentation-only commit carrying this reference. They are task
starting points, not completed implementations or a dependency stack. Before
working on a branch, integrate the latest main and the completed prerequisite
tasks. Do not base implementation on the unrelated private sanitization branch.
First reconcile the matrix baseline and settle section 2's open semantic choices.

| Task | Branch | Depends on | Deliverable |
| --- | --- | --- | --- |
| FH-01 | `feature/fault-state-policy` | Matrix decisions | Boolean SM boundary, fault categories/status/active/shadowing, shared priority-notification profiles, published contract. |
| FH-02 | `feature/fault-routing-aggregation` | FH-01 | Per-door fault instances, Group B ownership/aggregation, startup binding validation. |
| FH-03 | `feature/fault-degradation` | FH-01, FH-02 | Scoped restriction handling and FULL/PARTIAL/DEGRADED/UNKNOWN coverage. |
| FH-04 | `feature/fault-user-control` | FH-03 | Temporary/permanent controls, persistence, expiry, and immediate operator UI. |
| FH-05 | `feature/fault-priority-latch` | FH-01, FH-02 | Highest-priority latch/reset, integrated with control permissions when FH-04 lands. |
| FH-06 | `feature/fault-freeze-frame` | FH-01, FH-02 | Bounded freeze frames and extended data; later fields integrate degradation/control metadata. |
| FH-07 | `feature/fault-diagnostics-ui` | FH-02..FH-06, FH-08 | Unified fault/coverage/evidence views and migration regression checks. |
| FH-08 | `feature/fault-self-diagnostics` | FH-01, FH-02, FH-03 | App-health aggregation, real provider D faults, bypass-monitor integration and independent supervisor allocation. |

### Recommended implementation order

1. **FH-01 - state and policy contract.** Refresh the inventory against public
   main, settle the open review decisions, and test the Boolean-SM/fault boundary.
   Split contract/test work from migration if needed to keep reviews manageable.
2. **FH-02 - routing and aggregation.** Establish explicit subject bindings and
   single ownership before adding more diagnostic fault sources.
3. **FH-03 - degradation and coverage.** Implement scoped, cause-keyed restrictions
   and verify partial recovery without false clear.
4. **FH-08 - self-diagnostics.** Connect provider and App Health causes to the
   established routing/degradation model; allocate independent supervision.
5. **FH-05 - priority latch.** Establish persistent latch/reset behavior and
   permissions before exposing the broader operator override workflow.
6. **FH-04 - user control.** Deliver temporary/permanent controls with working UI,
   preserving the established latch and degradation protections.
7. **FH-06 - freeze frame.** Add bounded evidence capture once the required state,
   restriction and control fields are stable.
8. **FH-07 - diagnostics UI and integration.** Complete the unified presentation,
   translations and cross-feature regressions.

This is a recommended serial order, not extra hard dependencies. After FH-02,
FH-05 and the basic FH-06 capture/storage work can proceed independently of
FH-03/FH-08; integrate their later restriction/control fields before completion.
Each implementation PR owns its acceptance tests and minimal usable presentation;
FH-07 is not a reason to defer earlier regression testing or required controls.
Share corrections to this plan through the integration branch rather than
maintaining eight divergent versions. No runtime changes or PRs are implied by
preparing/publishing these branches.

### FH-01: Fault state and priority policy

The implementation contract for this branch is
[Fault State Policy](<features/Fault State Policy - Architecture.md>). This
branch introduces the fault-owned evaluation object, priority/category metadata,
shadow-owner tracking and the eight-status MQTT contract. Full migration of
every existing SM's debounce and eligibility,
including explicit negative observations for every required binding,
durable L1 latching, operator controls, degradation and rich UI publication
remain separately scoped work; the presence of a status enum is not evidence
that those behaviors are deployed.

Define the Boolean-only SM interface and fault-owned configuration/policy boundary.
Migrate stateful symptom behavior into fault handling without adding a parallel
symptom lifecycle. Define fault evaluation/status, active contributions,
priority/category, latch metadata, and handling profiles. Decide the fault's
mixed-evidence transition table and make priority
the source of handling defaults using the same L1..L4 notification level. Keep
shadowing orthogonal to evidence, preserve SHADOWED response history, and test
response withdrawal and unshadowing. Publish `active`, `latched` and
`shadowed_by` separately from evaluation status; update MQTT and frontend
consumers together. Inventory HA dashboard and automation consumers of removed
raw states and fault identities.
Update SYS/SSRD and affected feature contracts together. No extra pending/confirmed,
FDC, episode, or aging subsystem. Acceptance: state transition and mixed-evidence
tests, Boolean-only predicate contract tests, invalid-input/invocation-failure
tests, exact notification-level/profile tests, shadow/unshadow tests, priority
policy tests, and exact eight-status MQTT/frontend contract tests.

### FH-02: Routing and aggregation

Implement M03 and M11..M16 with a validated owner/subject mapping. Fail startup
on missing/ambiguous contributor ownership or invalid shadow references/cycles,
while distinguishing a known but uninstalled mechanism from a typo. Preserve
per-subject evidence and apply the shared-input ownership rule. Remove the old
shared door fault and its retained MQTT discovery/state without an alias, tag
mapping, saved-state import or false HEAL. Migrate dashboard and automation
consumers to per-door IDs explicitly. Acceptance: two independent doors, one door
recovering while another fails, several Group B checks/rooms, merged A/B inputs,
uninstalled mechanisms, and old-identity retirement tests.

### FH-03: Degradation and coverage

Declare each dependency's affected capability/subject and recovery conditions.
Compile every D row's explicit H-target list into concrete installed bindings;
reject missing/ambiguous targets and distinguish intentional external-only lists.
Track restriction causes independently; enforce restrictive effects before
dependent recovery. Derive coverage against the declared baseline and publish
reasons plus affected scope. Handle unavailable provider subsets without
disabling independent weather/AQ functions. Define which self-diagnostics can run
in process and which require an independent supervisor. Acceptance: stale room,
provider failure, two overlapping causes, recovery reevaluation, restart, and
no false clear. Avoid global component shutdown for a local dependency failure.

### FH-04: User control

Deliver allowlisted temporary inhibition/permanent disable plus authenticated
backend commands and usable SafetyHome controls in this task. Include target,
reason, expiry, attribution where supplied by authenticated infrastructure,
and persistence. Do not trust arbitrary client-supplied user identity. Make
inhibition, disable, acknowledgement, and reset distinct operations. Enforce
priority restrictions server-side and preserve technical degradation independently
of suppressed responses. Acceptance: one-hour door example, active-fault override,
expiry/restart/clock uncertainty, revoked permissions, and other-door isolation.

### FH-05: Highest-priority latch

Persist priority-1 latches, expose eligible reset, and require current recovery
evidence for all contributors. Acknowledgement silences repeats without resetting
the latch. Keep gas output inhibition separate. Provide minimal authenticated
reset UI with the backend, then integrate into FH-07. Acceptance: active condition
reset rejection, unavailable evidence rejection, valid reset, restart, multiple
detectors, and no implicit release of independent restrictions.

### FH-06: Freeze frame and extended data

Implement versioned allowlisted first-activation capture and bounded extended
data independently of notification delivery history. Specify capacity, eviction,
replacement on next activation, persistence errors, and clock semantics. Optional
recovery/significant-change captures require explicit bounds; no continuous HA
payload archive. Acceptance: immutable original evidence after source changes,
no extra activation counts on quiet refresh, secret filtering, size bounds,
restart, and storage failure isolation. No episode objects or IDs.

### FH-07: Diagnostic presentation and integration

Show category/priority, requested rich status, active/latch indication, contributors,
shadowed-by identities, coverage, restriction causes, user controls, freeze frame,
and extended data. Show the D-to-H capability relationship and App Health causes
without presenting a notification outage as loss of hazard detection.
Keep Group C inventory informational. A healthy-looking PASS label cannot hide an
active latch; FULL coverage cannot imply absence of hazards. Complete EN/PL/DE
runtime parity and regression tests of existing notification/recovery/history
contracts. Integrate controls already delivered with FH-04/FH-05 rather than
leaving those features unusable until this task.

### FH-08: Bring bypassing monitors into fault handling

Inventory every current health/error monitor in core, managers, providers and
components. Assign each detected safety-relevant failure to an existing or new
fault using the unified section 3 matrix and its final integration checklist.
Implement M17a..g as causes of one App Health D fault and M18a..c as provider D
faults, with declared levels and dependency effects. Include notification delivery,
local outputs, persistence, recovery execution, evaluation errors, application
startup and MQTT publication. Preserve existing health sensors as diagnostic
projections of evidence rather than losing their detail. Distinguish normal user
decline, intentional output inhibition and historical error counters from current
technical failure. Allocate out-of-process detection for faults which disable
their own in-process manager/transport; no live deployment is implied by this
task brief. Acceptance: qualified SET, evidence-based recovery, target isolation,
no notification recursion, storage failure, app/broker outage simulation, and
explicit supervisor coverage limits. Every failure monitor has a documented owner;
measurement-only helpers and passive inventory are identified explicitly.
M06 consumer capability loss and M18 provider failure must remain distinct under
redundancy; retain cause identity and avoid duplicate restriction accounting.

## 6. Evidence and validation scope

Current behavior is grounded in these sources, not inferred from requirements:

- [System fault catalog](../backend/config/system_config.yml) and
  [public installation example](../backend/config/user_config.example.yml).
- [Runtime types](../backend/components/core/types_common.py),
  [fault routing](../backend/components/faults_manager/fault_manager.py), and
  [application wiring](../backend/SafetyFunctions.py).
- [Temperature](../backend/components/safetycomponents/temperature/temperature_component.py),
  [Safety Doors](../backend/components/safetycomponents/safety_doors/safety_doors_component.py),
  [external hazards](../backend/components/safetycomponents/external_hazard/external_hazard_component.py),
  [Entity Monitor](../backend/components/safetycomponents/entity_monitor/entity_monitor_component.py), and
  [internal hazards](../backend/components/safetycomponents/internal_environmental_hazard/internal_environmental_hazard_monitor_component.py).
- [Fault tests](../backend/tests/test_fault_manager.py),
  [entity tests](../backend/tests/test_entity_monitor_component.py),
  [door tests](../backend/tests/test_safety_doors_component.py), and
  [integration tests](../backend/tests/test_system_notification_recovery.py).
- [Notification handling](../backend/components/notification_manager/notification_manager.py),
  [local annunciation](../backend/components/notification_manager/local_annunciator.py),
  [recovery event handling](../backend/components/recovery_manager/recovery_manager.py), and
  [provider runtime](../backend/components/external_apis/core/api_runtime.py).

Normative allocation and future reconciliation surfaces:

- [HARA](<sys/SafetyConcept - HARA.md>),
  [SYS](<sys/SafetyConcept - SYS.md>), and
  [SSRD](<sys/SafetyComponent - SSRD.md>).
- [Entity Health](<features/Entity Health Monitoring - Architecture.md>),
  [External Hazard](<features/External Hazard Monitoring - Architecture.md>),
  [Internal Environmental Hazard](<features/Internal Environmental Hazard Monitoring - Architecture.md>),
  [Heating System](<features/Heating System Monitoring - Architecture.md>),
  [Recovery](<features/Recommended Actions and Recovery - Architecture.md>), and
  [Notifications](<features/Mobile Notification Delivery - Architecture.md>).

Before each implementation PR, synchronize its affected normative documents,
configuration/compiler/schema, tests and public contract consumers. Keep HARA at
hazards and safety goals. Technical docs remain English; new runtime/operator
text requires EN/PL/DE parity. This planning-only change introduces no runtime
translations or evidence of deployment.
