# Entity Health Monitoring - Feature Architecture

**Safety component:** `EntityMonitorComponent`

**System component ID:** `C-ENT`

## 1. Fixed decisions

The following decisions define the feature boundary:

1. Entity Health Monitoring has two monitored source groups: explicit safety
   entities and component dependencies.
2. Group A is selected and calibrated by the installation owner because those
   entities participate in important automations or safety dependencies outside
   SafetyFunctions.
3. Group B is self-declared by Safety Components and the application core. It
   includes all configured shared entities and does not require duplicate
   installation configuration.
4. Entities outside Groups A/B shall not be enrolled implicitly or included in
   the monitored list, including when Home Assistant reports them unavailable.
5. Availability is mandatory for Groups A and B. Freshness and value checks are
   opt-in and require complete, type-compatible calibration.
6. Entity Monitor observes and diagnoses. It shall not call a Home Assistant
   actuator service or modify a monitored entity.
7. Each logical check contribution has one fault owner. Entity Monitor shall
   not create a duplicate Group A fault when a Group B role owns that check.
   Distinct input, recovery, detector or application-health roles may share one
   physical entity while retaining their separate fault families.
8. System Health shall present Group A/B diagnostics and the separate battery
   maintenance section. It shall not expose a general Home Assistant inventory.
9. C-ENT creates at most one `EntityHealth{EntityKey}` fault per unhealthy Group
   A entity that it owns. Temperature, door, external-opening and shared Group B
   inputs contribute to `InputMonitoringUnavailable`; recovery and detector
   diagnostics retain their separate faults without duplicate C-ENT faults.
10. Failure and recovery debounce govern the transition of each check result
    between passing and failed states.

## 2. Goals

The feature shall:

- detect unavailable or stale entities that could mask a household safety
  condition or prevent an important automation from operating;
- let an installation explicitly select and calibrate externally owned safety
  dependencies, such as climate or heating entities;
- make SafetyFunctions aware of the health of every entity dependency consumed
  by its components and core services;
- expose one consistent view of explicit and component-owned entity health;
- preserve independent entity/check evidence inside shared input faults, while
  retaining separate faults for external-only Group A entities;
- list all configured monitored records in System Health, including healthy
  and unavailable records, separately from battery maintenance;
- make entity source, owner, state, availability, timestamps, device, and area
  easy to filter in SafetyHome;
- use friendly names for operators while preserving stable entity IDs and raw
  codes for diagnostics;
- avoid unbounded MQTT payloads and unnecessary duplicate Home Assistant state
  subscriptions;
- provide deterministic evidence and fault-injection seams for automated tests.

## 3. Boundaries

### 3.1 In scope

- Home Assistant entity state and registry metadata.
- Explicit installation-owned safety dependencies.
- Safety Component and core dependency declarations.
- Every configured `common_entities` binding.
- Availability, optional freshness and value checks, failure/recovery debounce,
  and diagnostic publication for Groups A and B.
- Search, health/source filtering, and diagnostic details for monitored records
  within System Health.
- Fault aggregation for failures owned by C-ENT.

### 3.2 Out of scope

- Inferring that every Home Assistant entity is safety-relevant.
- Treating an unchanged state as stale without a declared update cadence.
- Repairing, reloading, enabling, disabling, or commanding an entity or device.
- Replacing component-specific hazard logic with generic range checks.
- Duplicating provider-health or unavailable-input faults already owned by
  another component.
- Persisting the complete Home Assistant entity registry in MQTT.
- A general Home Assistant entity/device inventory or using unmonitored entities
  as evidence that a safety condition is clear.

## 4. Monitoring groups

### 4.1 Group A - explicit safety entities

Group A covers dependencies known by the installation owner but not owned by a
SafetyFunctions component. Typical examples include climate entities, heating
controllers, pumps, valves, helper entities, or sensors used by important Home
Assistant automations.

Each entry has a stable installation key and contains:

- `entity_id`;
- optional `area_id` and operator description;
- mandatory availability monitoring;
- optional freshness, required-value, allowed-values, finite-number, numeric-
  range, or rate-of-change checks;
- optional report-age timeout and failure debounce; recovery policy is system-owned;
- an enabled/disabled flag that preserves the stable key.

Group A selection belongs to the installation registry under
`installation.monitored_entities`; generated runtime configuration places the
validated entries under `EntityMonitorComponent`. System timing defaults remain
under `calibration.entity_monitor`.

### 4.2 Group B - component dependencies

Group B makes SafetyFunctions self-aware. A component or core service registers
every entity whose loss affects its inputs or required diagnostics. Registration
contains:

- stable dependency key;
- `entity_id` resolved from validated configuration;
- owner component/core service;
- purpose and expected value kind;
- optional `report_timeout_seconds` and a trustworthy source timestamp contract;
- enabled optional checks;
- fault ownership;
- optional area/device context.

All entries in `installation.common_entities` are registered as Group B records.
Component schemas or core policy own defaults. System calibration may override
failure/recovery debounce, detection budget, and check thresholds by stable
dependency key. An entity may also be selected in Group A; the registry retains
both memberships and resolves one owner for each logical check contribution;
distinct fault-family roles remain separate records.

Examples of Group B dependencies include temperature inputs registered by
`TemperatureComponent`, door contacts registered by `SafetyDoorsComponent`,
and shared outside-temperature or occupancy inputs registered by the application
core or their consuming component.

### 4.3 Unmonitored entities

Entities outside Groups A/B shall not appear in the monitored list and shall
not create C-ENT symptoms, faults, notifications, recovery actions, or
application-health degradation. SafetyHome shall not offer a general Home
Assistant entity/device inventory. Battery discovery and maintenance remain a
separate C-FSM contract and a separate section within System Health.

The monitored list shall derive membership from backend Group A/B diagnostics,
not from the complete Home Assistant registry or from entity availability.
Its size shall reflect the installation's declared records, including separate
fault-family records sharing one physical entity; no fixed count is assumed.

`last_changed` means that the state value changed. `last_updated` means that the
state or its attributes changed. Neither timestamp proves a physical heartbeat
unless the owning integration or dependency contract guarantees periodic
updates.

## 5. Logical architecture

```text
                   validated application configuration
                              |
            +-----------------+------------------+
            |                                    |
            v                                    v
 Group A explicit entries            Group B dependency declarations
 user-owned calibration              component/core-owned calibration
            |                                    |
            +-----------------+------------------+
                              v
                    EntityHealthRegistry
                    - merge memberships
                    - resolve ownership
                    - reject conflicts
                              |
                              v
                    EntityMonitorComponent
                    - shared live HA report reader
                    - immediate state listeners
                    - freshness scheduler
                    - check evaluation
                    - debounce/state machine
                    - bounded diagnostics
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
       owned symptom events          MQTT Group A/B diagnostics
             |
             v
 EventBus -> FaultManager -> NotificationManager

 Authenticated SafetyHome connection -> Group A/B diagnostics -> System Health

 EntityMonitorComponent has no edge to RecoveryManager actuator execution.
 Unmonitored entities have no edge to C-ENT fault evaluation.
```

## 6. Code placement

```text
backend/components/safetycomponents/entity_monitor/
  __init__.py
  entity_monitor_component.py
  models.py
  schema.py

frontend/src/
  domain/entityHealth.ts
  components/MonitoredEntities.tsx
  pages/FunctionalSafety.tsx
```

The component module implements registry and check evaluation. Tests mirror
backend placement under `backend/tests/` and frontend placement
under `frontend/src/` using the repository's existing test conventions.

## 7. Core model

```python
class EntitySource(str, Enum):
    EXPLICIT = "explicit"
    COMPONENT = "component"


class EntityHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class FaultOwner(str, Enum):
    ENTITY_MONITOR = "entity_monitor"
    COMPONENT = "component"
    NONE = "none"


@dataclass(frozen=True)
class EntityDependency:
    key: str
    entity_id: str
    sources: frozenset[EntitySource]
    owner: str
    purpose: str
    fault_owner: FaultOwner
    checks: tuple["EntityCheckConfig", ...]
    area_id: str | None = None
```

Backend registry records are keyed by physical entity and diagnostic fault
family. Compatible declarations for the same input family merge their checks,
consumers and memberships. A recovery, detector or application-health family
retains a separate logical record even when it references the same physical
entity. For example, one window contact may contribute to both
`InputMonitoringUnavailable` and `TemperatureRecoveryUnavailable`; the merge
shall not rename or discard the recovery fault.

Group A membership attaches once when Group B records exist, preferring the
input-monitoring record when present. It does not create duplicate Group A
faults for the other logical roles. The shared reader acquires one physical
entity at the shortest derived cadence required by its records; every logical
record retains independent checks, debounce state and coverage bindings.
The frontend lists those diagnostic records within System Health.
A component-owned check cannot be disabled or relaxed by Group A configuration.

Conflicting value kinds or ownership within the same logical record are
configuration errors. Distinct fault-family roles are not an ownership conflict.
Identical checks within a record are deduplicated by their stable check key.

## 8. Check model

Every check returns a structured result containing check key, result state,
reason code, observed value, evaluation timestamp, relevant source timestamps,
and calibration identity.

### 8.1 Mandatory check

| Check code | Purpose | Failure state |
| --- | --- | --- |
| `availability` | Detect missing entities, read failures, and native `unknown` or `unavailable` states | `unavailable` |

Availability is evaluated against the entity itself. It fails when the entity
cannot be read, is missing, returns `None`, or has a normalized native state of
`unknown` or `unavailable`. An empty state may be rejected by an enabled
`required_value` check rather than by availability.

### 8.2 Optional checks

Every optional check targets either the entity `state` or one named attribute.

| Check code | Required calibration | Exact pass condition | Failure state |
| --- | --- | --- | --- |
| `freshness` | `timestamp_source` and positive dependency-level `report_timeout_seconds` | The age of the latest valid confirmation is no greater than `report_timeout_seconds` | `stale` |
| `required_value` | Target | The target exists and is neither `None` nor an empty string | `degraded` |
| `allowed_values` | Target and non-empty set of normalized values | The normalized target value belongs to the configured set | `degraded` |
| `finite_number` | Target | The target converts to a finite number; `NaN` and positive/negative infinity fail | `degraded` |
| `numeric_range` | Target plus inclusive `minimum` and/or `maximum` | The finite numeric target is within every configured bound | `degraded` |
| `rate_of_change` | Target, positive `window_seconds`, `min_samples >= 2`, and at least one rise/fall bound | The rate calculated from the oldest and newest valid samples in the window is within every configured bound | `degraded` |

`target: state` reads the entity state. `target: <attribute_name>` reads exactly
that Home Assistant attribute. Missing targets are unevaluable unless
`required_value` is enabled for the same target; unevaluable input cannot pass a
dependent numeric check or clear an active symptom.

Freshness uses only the configured trustworthy source:

- `last_contact_at`, normalized from the unique `sensor.*_last_seen` on the
  same Home Assistant registry device, when device contact is the declared
  basis for trusting the channel's last valid value;
- `last_reported` from a live Home Assistant read when the integration's entity
  reports are a trustworthy confirmation of the monitored input;
- `last_updated` only when the owning integration guarantees a real periodic
  state or attribute update; or
- one named timestamp attribute supplied by the entity.

`last_reported` advances when the integration writes the entity, including an
unchanged value. It is not independently proof of a new physical measurement.
MQTT may suppress an unchanged entity write unless `force_update` is enabled;
receiving another MQTT message therefore does not necessarily advance
`last_reported`.
A device-level `last_seen` may represent a humidity, battery, or other message.
Temperature inputs shall use this device-contact contract by default: the last
valid temperature remains usable while `last_contact_at` is within 3600 seconds,
even if the temperature value and its Home Assistant report timestamps do not
advance. Availability, finite-number and configured numeric-range checks remain
required. Contact does not claim a new temperature measurement. Missing,
ambiguous, invalid or future contact evidence shall leave freshness unevaluable;
neither a successful read nor `last_reported` shall replace it automatically.
Explicit dependency overrides may select another trustworthy timestamp for
sources such as a thermostat integration without device `last_seen`.
Other physical sensor channels may declare the same contact contract. Derived
rates, weather/provider products and application-health outputs shall retain
their own evidence contracts. No global `last_seen` fallback shall be inferred.

The shared Home Assistant report provider shall acquire device-contact
metadata for a monitored `sensor` or `binary_sensor` when exactly one `sensor.*_last_seen`
entity belongs to the same Home Assistant registry device. Ambiguous or absent
matches shall not supply contact evidence. Unix seconds, Unix milliseconds and
timezone-aware ISO timestamps shall normalize to UTC; invalid or future values
shall be omitted. C-ENT shall expose `last_contact_at` and
`last_contact_source_entity` separately from `last_reported`. Contact shall affect
freshness only when the owning dependency selects
`timestamp_source: last_contact_at`; otherwise it remains informational, with no inferred timeout.
It shall not replace availability or value checks, assert passing alarm evidence,
or clear an active fault without the owning channel's valid recovery evidence.

`last_changed` is presentation metadata and is never a freshness source. A
change in value is not required for freshness, and an unchanged door, switch,
valve, or temperature remains fresh while its configured source continues to
provide valid confirmations within `report_timeout_seconds`.

Availability, value and freshness checks shall evaluate from the initial
snapshot; startup shall not postpone freshness calculation or reset source-report
age. Qualified D contributions without an allocated `detection_budget_seconds`
shall use the application-wide
[startup gate](<Fault Routing and Aggregation - Architecture.md#startup-qualification>).
Dependencies with an allocated detection budget shall bypass the gate and retain
their existing detection, degradation and notification timing from startup.
The configured timeout shall reflect the source's real update behavior; C-ENT shall
not infer a heartbeat from entity domain or from repeated reads performed by
C-ENT itself.

For a safety-relevant dependency, the owning contract shall allocate a detection
budget from its applicable FTTI. The applicable input-acquisition delay, bounded
read timeout, evaluation scheduling and failure debounce shall fit that budget.
Freshness paths shall additionally allocate the freshness timeout. Immediate
event reception and periodic reconciliation have different acquisition bounds;
a nominal polling period alone is not a complete detection budget. If the real
source cadence cannot satisfy the budget, the source cannot serve as the sole
safety channel for that requirement.

Optional checks are generic channel-health diagnostics. Safety-specific
thresholds, such as unsafe room temperature, remain in the owning Safety
Component and are not duplicated here.

In particular, `sensor.entity_health_temperature_forecast_<room>` supervises
the room's derivative input, including availability and finite-number checks.
A `healthy` result means those input checks pass; it does not compare the
modeled room temperature with its safety limits. Valid available inputs may
still predict a dangerous temperature. C-TEMP shall publish its last low/high
forecast predicate observations in the existing threshold sensors'
`forecast_evaluation` attributes, separately from the qualified
`RiskyTemperatureForecast` fault and its active contributors. The last
observation and the qualified fault may differ while debounce is in progress.
An application-health evaluation diagnostic or a repair proposal for a failed
evaluator concerns successful execution of that path, not whether its
temperature predicate detects a hazard. Operator views shall retain these
three meanings: input health, predicate observation, and qualified alarm.

Rate-of-change evaluation may reuse numeric sampling utilities from
`DerivativeMonitor`, but Entity Monitor owns its check result, calibration, and
fault semantics. The rate is `(newest_value - oldest_value) / elapsed_time`
expressed per minute. Non-numeric, non-finite, stale, or unavailable input is
unevaluable and cannot pass a numeric check.
An internally generated temperature `_rate` has no numeric value until its
second sample. The derivative monitor shall seed the first source sample at
registration so the next scheduled sample can produce a valid rate. Its
dependency detection budget shall exceed the configured
derivative sampling interval and include scheduler margin; the initial unknown
value is not evidence of a safe forecast. Its availability failure debounce
shall use that same interval-derived threshold, rather than the generic
dependency default, so the first missing rate does not set a fault before the
second sample is due. A configured component override may replace the debounce.
The temperature derivative dependency uses a failure debounce of the sampling
interval plus 60 seconds and a detection budget of the sampling interval plus
390 seconds, reserving a further 330 seconds for acquisition and evaluation.
Room-temperature and shared outside-temperature dependencies retain their
3600-second report-silence limit, use 60-second failure confirmation and allocate
a 4020-second detection budget. The budget covers report silence, 120-second
acquisition cadence, a 120-second read deadline, scheduling and evaluation
phase allowances, and failure confirmation. It does not change temperature
hazard thresholds or the owning component's direct alarm paths.

### 8.3 Debounce policy

`failure_debounce_seconds` and `recovery_debounce_seconds` apply independently
to the state transition of each check result and do not create additional
symptom IDs. A failing check enters `PENDING_FAILURE`; it creates its symptom
only when failure debounce expires without a passing result. A failed check
enters `PENDING_RECOVERY` only on current positive passing evidence and clears
only when recovery debounce expires without another failure.

## 9. Evaluation lifecycle

1. Validate Group A configuration and component/core dependency declarations.
2. Resolve entity IDs, area names, and Group B registrations.
3. Merge records and reject incompatible contracts.
4. Register bounded MQTT diagnostics for Groups A and B.
5. Register the deduplicated Group A/B entity set with the shared live Home
   Assistant report reader. Temperature-owned and shared outside-temperature
   dependencies have a 120-second baseline batch cadence, other ordinary
   dependencies have a 60-second baseline, and short-budget dependencies use
   the fast group. Effective intervals may be shortened by report-age and
   confirmation requirements, with a 5-second minimum. Multiple logical
   records share the shortest interval for their physical entity.
6. Subscribe to state updates as an immediate supplement. A newer state or
   attribute transition shall not wait for the next periodic report read.
7. Schedule freshness and debounce evaluation immediately and independently of
   network acquisition. Route eligible qualified D transitions through the shared
   startup gate; H, `SafetyAppHealth` and dependencies with allocated detection
   budgets retain immediate routing. Ordinary evaluation has a 60-second
   baseline capped by derived monitor requirements; a separate 5-second timer
   reconciles short-budget dependencies.
8. Evaluate mandatory checks before optional checks.
9. Update per-check debounce state and the combined entity health state.
10. Publish diagnostics and emit only C-ENT-owned symptom transitions.
11. Cancel listeners, reader activity and timers before MQTT availability is set
    offline.

The shared reader performs authenticated batch reads in background workers.
Its dedicated scheduler shall use monotonic five-second deadlines independently
of AppDaemon's pinned application callbacks, including MQTT publication. Missed
ticks shall not cause a catch-up burst. Shutdown shall wake the scheduler and
reject late responses without depending on cancellation of an AppDaemon timer.
Ordinary reads have a 120-second response deadline. Short-budget reads use an
independent worker and a 4-second deadline so an ordinary timeout cannot block
their next acquisition. Each worker admits at most one request in flight;
responses after its deadline are discarded. Ordinary reader evidence expires
at acquisition start plus the group's polling interval, the 120-second deadline
and a 5-second scheduling allowance. Short-budget evidence expires at acquisition
start plus its interval, the 4-second deadline and a 1-second scheduling
allowance: ten seconds for the five-second group. A nine-second scheduling gap
shall not invalidate an otherwise valid report or restart recovery qualification.
After expiry, missing evidence shall remain unevaluable. The ten-second validity
window, five-second evaluation cadence and fifteen-second failure debounce fit
the existing thirty-second detection allocation. Response delivery time cannot extend
either expiry. Repeated reads retain the original source timestamps; they do
not invent heartbeats. A failed attempt invalidates the affected group's
previous reports, and a stalled request cannot renew them. Missing or expired
acquisition evidence shall not advance recovery or clear an active symptom.
State-change cache data alone shall not supply the report timestamp for an
unchanged input.

Availability failure dominates freshness and optional checks. Freshness failure
dominates optional checks. The entity state is `healthy` only when every enabled
check has current positive passing evidence.

## 10. Failure and recovery state machine

```text
            passing evidence
    +------------------------------+
    |                              v
 HEALTHY -- failing sample --> PENDING_FAILURE
    ^                              |
    |                              | failure debounce satisfied
    |                              v
 PENDING_RECOVERY <-- pass -- FAILED
    |                              |
    +-- recovery debounce ---------+
```

- Missing, stale, invalid, or unevaluable input never advances recovery.
- A different failing check does not erase an existing failure.
- Each check keeps independent debounce state.
- The per-entity health is the most severe active check state.
- Restart reconstructs health from the initial snapshot and timestamps; it does
  not assume that the previous process state was healthy.

## 11. Fault ownership and aggregation

C-ENT uses the following stable contract when it owns a failure:

| Element | Stable ID |
| --- | --- |
| Safety Mechanism | `sm_entity_health_<entity_key>` |
| Symptom | `EntityHealthFailure{EntityKey}{CheckKey}` |
| Fault | `EntityHealth{EntityKey}` |
| Level | 3 |
| Recovery action | Cause-specific manual repair; no actuator command |

The owner shall supply repair proposals under the
[shared recovery contract](<Recommended Actions and Recovery - Architecture.md>),
naming the affected entity and failed availability, freshness or value path.
Positive recovery of that cause shall complete its observed repair action;
operator-reported inspection shall not establish that the source is healthy.
Group B repair actions shall follow their declared fault owner, preserving one
action for a shared failed path. Unmonitored entities shall create none.

Each C-ENT-owned Group A entity has its own fault. All active check symptoms
for that entity aggregate into the same fault; symptoms belonging to another
entity aggregate into that other entity's fault. Each fault retains:

- friendly name and entity ID;
- source groups and owner;
- failed check and reason code;
- current and last valid values;
- last change, last update, failure-start, and evaluation timestamps;
- area and device when known.

After Group A/B records are merged and validated, C-ENT registers the safety
mechanism and fault definition for each C-ENT-owned entity with FaultManager
before state listeners and check evaluation start. Registration is deterministic
from the stable entity key. The operator-facing fault name uses the current
friendly entity name while the runtime IDs remain unchanged.

For Group B, the requesting component declares each dependency and its consumer
bindings. C-ENT routes temperature, door, external-opening and shared input
checks into `InputMonitoringUnavailable`; recovery and detector diagnostics
retain separate faults. It does not emit a duplicate `EntityHealth` fault. A shared input
has one declared owner and explicit consumer bindings. `none` is allowed only
for an informational diagnostic and never weakens an existing safety contract.
For configured temperature and external-hazard recovery actuators, C-ENT also
hosts an event-driven `RecoveryCommand` contributor under the same Group B fault.
RecoveryManager reports rejected commands and missed postconditions with the
exact H symptom and actuator identity. Entity availability cannot clear this
contributor; only an observed recovery postcondition can. Outstanding failures
are restored from recovery state before fault evaluation after restart.
An interrupted executing proposal is marked failed rather than made executable
again; its persisted expected state is observed passively so a later manual
repair can release only that command contributor.
The shared input fault retains independent per-source contributors, so repair
of one entity cannot clear another failure or enable an unrelated H consumer.
The binding and fault identities are defined in
[Fault Routing and Aggregation](Fault%20Routing%20and%20Aggregation%20-%20Architecture.md).

## 12. MQTT diagnostics

Each Group A/B entity publishes one diagnostic sensor:

```text
sensor.entity_health_<entity_key>
```

Its raw state is `healthy`, `degraded`, `stale`, or `unavailable`. Attributes
include bounded check summaries and operator/diagnostic context. Entity keys are
stable configuration or dependency keys, not slugs derived solely from a
friendly name.

The aggregate sensor is:

```text
sensor.entity_monitor_summary
```

It publishes bounded counts by health and source plus a bounded list of
unhealthy Group A/B summaries. Individual diagnostic entities supply the full
monitored list; the summary does not contain the complete Home Assistant inventory.

MQTT discovery names and `state_label` are localized. Raw health, source, check,
and reason codes remain language-independent.

## 13. Frontend architecture

System Health presents C-ENT MQTT diagnostics for authoritative Group A/B
health and fault context alongside the separate C-FSM battery section. Its
monitored list shall not enumerate the Home Assistant entity or device registry.

The frontend performs only presentation filtering. It may defensively recompute
simple display classifications, but it shall not create or clear a safety fault.

The monitored-entities section provides:

- summary cards for unhealthy Group A and B entities;
- a default problem-first list;
- explicit badges for A and B membership;
- all monitored records, including healthy and unavailable ones;
- text search and combinable health/source filters;
- problem-first ordering by health severity and friendly name;
- tooltips or details with the technical entity ID, owner, check calibration,
  reason code, and timestamps;
- Polish operator labels with English and German runtime translation parity.

Diagnostic details shall be expandable per monitored record. The old `/entities`
route shall redirect to `/functional-safety`; the navigation shall expose
System Health rather than a separate entity/device inventory.

## 14. Configuration contract

Global timing and publication policy belongs in `system_config.yml` under
`calibration.entity_monitor`. Explicit installation health
dependencies belong in the private `user_config.yml` under
`installation.monitored_entities`. Installation-specific overrides keyed by
stable component dependency IDs belong under
`installation.component_settings.entity_monitor.component_overrides`. The public
repository contains only schema-safe examples and shall not contain bindings
from a real Home Assistant installation.

The ordinary monitor timing contract exposes two fields per dependency:
`report_timeout_seconds` is the maximum age of a trusted source report, and
`failure_debounce_seconds` is the continuous failed-check period needed to
confirm a problem. A successful HA read never resets the source-report age.
Freshness is opt-in and requires a trustworthy timestamp source; availability
checks still apply when no freshness contract is declared.

The monitor derives read/evaluation cadence within its system-owned limits and
allocated detection budget. Derived cadence has system-owned bounds, including
a 5-second minimum; accepting a timing configuration does not by itself prove
that the complete acquisition/evaluation/notification path meets its FTTI.
The schema checks the freshness-plus-debounce allocation; the owning dependency
contract must separately allocate transport and scheduling overhead.
Reader request deadlines, shared D startup qualification, recovery
debounce and FTTI allocations remain separate safety policies. The startup
override retains its existing `startup_grace_seconds` path; its system default
is 600 seconds and `0` disables the gate. It shall apply at each SafetyFunctions
initialization without delaying acquisition or check evaluation. H evidence,
`SafetyAppHealth` and dependencies with allocated detection budgets shall bypass
the gate. Each dependency's existing `detection_budget_seconds` shall accompany
its symptom contributions so routing preserves that allocation. In particular, a
report-age timeout is not the network request timeout. A tighter requirement
shall cap a legacy global evaluation interval rather than wait for that slower
interval. Immediate life-safety alarm paths remain independent.

The following is a structural example; the entity ID is illustrative rather
than an installation mapping:

```yaml
calibration:
  entity_monitor:
    default_startup_grace_seconds: 600
    default_failure_debounce_seconds: 15
    default_recovery_debounce_seconds: 60
    default_evaluation_interval_seconds: 60
    component_overrides:
      TemperatureBedroom:
        detection_budget_seconds: 990
        report_timeout_seconds: 600
        failure_debounce_seconds: 60
        checks:
          freshness:
            timestamp_source: "last_contact_at"

user_config:
  model_version: 2
  installation:
    monitored_entities:
      ExampleHeatingAppHealth:
        entity_id: "sensor.example_heating_app_health"
        description: "Health output of another AppDaemon application"
        report_timeout_seconds: 600
        failure_debounce_seconds: 15
        checks:
          freshness:
            timestamp_source: "last_reported"
          allowed_values:
            target: "state"
            values: ["running"]
    component_settings:
      entity_monitor:
        component_overrides:
          TemperatureExampleRoom:
            report_timeout_seconds: 600
            failure_debounce_seconds: 60
            checks:
              freshness:
                timestamp_source: "last_contact_at"
```

Group B declarations are created from already validated component bindings and
code-owned defaults. The system calibration remains the baseline; an
installation may refine one dependency only by its stable key under the
dedicated Entity Monitor component override map.

For migration, legacy `checks.freshness.max_silence_seconds` remains accepted as
the report-age timeout alias. Existing recovery, startup, evaluation and
detection-budget fields remain accepted and validated; new installation
examples use the two monitor timing fields. When both freshness timeout forms
are supplied they must agree. The normalized diagnostic representation may
retain `max_silence_seconds` for existing consumers. A legacy timing field cannot
relax a declared life-safety detection budget or extend a derived safety cadence.

Strict validation rejects:

- missing or invalid entity IDs;
- duplicate stable keys pointing to different entities;
- non-positive report-age deadlines or negative debounce values;
- an availability debounce that exceeds its allocated FTTI detection budget;
- a safety freshness/debounce combination that exceeds that budget;
- freshness checks without a trustworthy timestamp source or timeout;
- empty allowed-value sets;
- range checks without a bound;
- rate checks without a sample window, minimum sample count, or direction bound;
- incompatible checks for the declared value type;
- Group B ownership or calibration conflicts.

## 15. Performance and boundedness

- Group A/B state listeners are deduplicated by entity ID and supplement shared
  periodic report reads without replacing the owning component's alarm path.
- The shared background reader batches due entity groups and prevents
  overlapping network reads within each worker. The short-budget worker is
  independent of ordinary reads. Freshness and debounce use a separate scheduler;
  there is no network polling loop per entity.
- MQTT diagnostics use bounded attributes and unhealthy summaries.
- Frontend filtering operates on the installed monitored records.
- A presentation failure cannot block Group A/B backend evaluation.

## 16. Security and privacy

- The feature uses the existing authenticated Home Assistant and MQTT paths.
- Entity states, friendly names, device names, and area names may reveal
  occupancy or household layout and shall not be sent to external services.
- Diagnostics shall not expose secrets stored in entity attributes.
- The backend publishes an allowlisted diagnostic attribute schema rather than
  copying arbitrary Home Assistant attributes.
- Monitored diagnostic presentation remains inside the authenticated
  Home Assistant/SafetyHome session.

## 17. Verification

### 17.1 Backend unit tests

- Group A schema validation and calibration precedence.
- Group B registration for Temperature, Safety Doors, shared application inputs,
  and every common entity.
- Membership merge and conflict rejection.
- Shared physical entities with independent input/recovery/application-health
  fault families, single Group A membership and shortest-cadence acquisition.
- Missing, `unknown`, `unavailable`, stale, and recovered states.
- Shared startup grace, restart snapshots, immediate check evaluation, and
  eligible D deferral without delaying H, `SafetyAppHealth` or dependencies with
  allocated detection budgets.
- Optional check calibration and target validation.
- Freshness and rate-of-change edge cases.
- Unchanged valid reports, future/malformed timestamps, expired reader evidence,
  failed or late batch reads, and preservation of active faults during transport
  loss.
- A stalled read with no state-change event and an unchanged cache shall cause
  the 5-second dependency group to assert unavailability within its 30-second
  detection budget, with reason `source_report_unavailable`.
- Nine-second scheduling gaps shall preserve qualified application-health
  checks; ten-second evidence expiry and failed or late requests shall still
  invalidate them. Independent scheduler startup, monotonic scheduling,
  skipped ticks, duplicate-start rejection and bounded shutdown shall be tested.
- Independent failure and recovery debounce.
- Fault ownership and duplicate-fault prevention.
- Same-entity check aggregation, shared input aggregation with independent
  contributors, per-entity Group A fault separation, and no false clear.
- Two-field monitor calibration, legacy alias normalization/conflict rejection,
  derived scheduling and preservation of allocated detection budgets.
- Stable MQTT IDs and bounded attributes.
- Cause-specific manual recovery registration and valid recovery evidence;
  no actuator service calls or recovery creation for unmonitored entities.

### 17.2 Backend integration tests

- AppCfgValidator and component registry integration.
- State-listener deduplication, shared batch scheduling, and single-flight reads.
- EventBus and FaultManager transitions.
- Application startup/termination and MQTT availability.
- Component-owned fault behavior remains authoritative.

### 17.3 Frontend tests

- Group A/B diagnostic membership without a general HA inventory.
- Monitored entities and battery maintenance both remain in System Health.
- Combined filters and search.
- Problem-first health ordering.
- Friendly-name presentation with technical IDs in details.
- Information-only rows never appear as active faults.
- Unmonitored unavailable entities remain absent; installed monitored counts
  are dynamic, and separate fault-family records remain visible.
- The legacy entity route redirects to System Health.
- English, Polish, and German state-label parity.

## 18. Traceability

| Safety source | Allocation |
| --- | --- |
| HARA 1.3.11 System Failure | Groups A/B entity availability, freshness, diagnostics, and alerts |
| SG-003 | C-ENT checks, fault ownership, no-false-clear behavior, and per-entity level-3 fault allocation |
| IR-009 | Entity state, timestamps, source membership, device, area, and information-only boundary |
| SYS-SR-ENT-* | Software requirements `SWR-ENT-*` |
| NFR-030/031 | Component-owned contracts and isolation from unmonitored entities |
| NFR-040/041 | Per-check evidence, health counts, and freshness metrics |

Unmonitored Home Assistant entities have no C-ENT safety-goal allocation.
