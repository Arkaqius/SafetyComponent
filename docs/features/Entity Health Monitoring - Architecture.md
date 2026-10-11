# Entity Health Monitoring - Feature Architecture

**Safety component:** `EntityMonitorComponent`

**System component ID:** `C-ENT`

## 1. Fixed decisions

The following decisions define the feature boundary:

1. Entity Health Monitoring has three source groups: explicit safety entities,
   component dependencies, and the complete information-only Home Assistant
   entity/device inventory.
2. Group A is selected and calibrated by the installation owner because those
   entities participate in important automations or safety dependencies outside
   SafetyFunctions.
3. Group B is self-declared by Safety Components and the application core. It
   includes all configured shared entities and does not require duplicate
   installation configuration.
4. Group C is informational. It shall never create a symptom, fault,
   notification, recovery action, or application-health degradation.
5. Availability is mandatory for Groups A and B. Freshness and value checks are
   opt-in and require complete, type-compatible calibration.
6. Entity Monitor observes and diagnoses. It shall not call a Home Assistant
   actuator service or modify a monitored entity.
7. Each logical check contribution has one fault owner. Entity Monitor shall
   not create a duplicate Group A fault when a Group B role owns that check.
   Distinct input, recovery, detector or application-health roles may share one
   physical entity while retaining their separate fault families.
8. The complete Group C inventory is read through the authenticated Home
   Assistant frontend connection. It is not copied into MQTT attributes.
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
- provide an entity/device audit view for the complete Home Assistant instance;
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
- Information-only inventory, search, sorting, filtering, and device grouping for
  Group C.
- Fault aggregation for failures owned by C-ENT.

### 3.2 Out of scope

- Inferring that every Home Assistant entity is safety-relevant.
- Treating an unchanged state as stale without a declared update cadence.
- Repairing, reloading, enabling, disabling, or commanding an entity or device.
- Replacing component-specific hazard logic with generic range checks.
- Duplicating provider-health or unavailable-input faults already owned by
  another component.
- Persisting the complete Home Assistant entity registry in MQTT.
- Treating Group C audit results as evidence that a safety condition is clear.

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

### 4.3 Group C - entity and device inventory

Group C contains all entities and devices visible to the authenticated
Home Assistant frontend connection. It is an operator audit surface, not a
Safety Component input.

The frontend exposes at least:

- friendly name and entity ID;
- domain, current raw state, and availability;
- `last_changed` and `last_updated`;
- device and area when available;
- disabled/hidden metadata when registry permissions expose it;
- Group A/B badges and health when the entity also belongs to those groups.

For a selected entity or device, the frontend may query Home Assistant history
on demand to show recent `unknown`/`unavailable` periods. It shall not bulk-load
history for the complete inventory. A device roll-up is derived from its entity
rows and remains informational unless one of those entities independently
belongs to Group A or B.

The view supports text search, sorting, device grouping, and filters for domain,
device, area, availability, source group, and age of the last change/update.

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

 Authenticated SafetyHome connection -> HA states/registries -> Group C view
                                                 |
                                                 +-> joins Group A/B summaries

 EntityMonitorComponent has no edge to RecoveryManager actuator execution.
 Group C has no edge to EventBus, FaultManager, or NotificationManager.
```

## 6. Code placement

```text
backend/components/safetycomponents/entity_monitor/
  __init__.py
  entity_monitor_component.py
  checks.py
  models.py
  registry.py
  schema.py

frontend/src/
  domain/entityHealth.ts
  hooks/useEntityHealth.ts
  pages/EntityAuditPage.tsx
```

Tests mirror backend placement under `backend/tests/` and frontend placement
under `frontend/src/` using the repository's existing test conventions.

## 7. Core model

```python
class EntitySource(str, Enum):
    EXPLICIT = "explicit"
    COMPONENT = "component"
    INVENTORY = "inventory"


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
The frontend joins those diagnostics with the complete Group C inventory.
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
A device-level `last_seen` may represent a humidity, battery, or other message;
it shall not serve as temperature confirmation without a declared source
contract. No global `last_seen` fallback shall be inferred.

`last_changed` is presentation metadata and is never a freshness source. A
change in value is not required for freshness, and an unchanged door, switch,
valve, or temperature remains fresh while its configured source continues to
provide valid confirmations within `report_timeout_seconds`.

The freshness timer starts after the initial snapshot and startup grace. The
configured timeout shall reflect the source's real update behavior; C-ENT shall
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
7. Apply startup grace, then schedule freshness and debounce evaluation
   independently of network acquisition. Ordinary evaluation has a 60-second
   baseline capped by derived monitor requirements; a separate 5-second timer
   reconciles short-budget dependencies.
8. Evaluate mandatory checks before optional checks.
9. Update per-check debounce state and the combined entity health state.
10. Publish diagnostics and emit only C-ENT-owned symptom transitions.
11. Cancel listeners, reader activity and timers before MQTT availability is set
    offline.

The shared reader performs authenticated batch reads in background workers.
Ordinary reads have a 120-second response deadline. Short-budget reads use an
independent worker and a 3-second deadline so an ordinary timeout cannot block
their next acquisition. Each worker admits at most one request in flight;
responses after its deadline are discarded. Ordinary reader evidence expires
at acquisition start plus the group's polling interval, the 120-second deadline
and a 5-second scheduling allowance. Short-budget evidence expires at acquisition
start plus its interval plus 3 seconds. Response delivery time cannot extend
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
| Recovery action | None |

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
unhealthy Group A/B summaries. It does not contain healthy inventory rows or the
complete Group C dataset.

MQTT discovery names and `state_label` are localized. Raw health, source, check,
and reason codes remain language-independent.

## 13. Frontend architecture

SafetyHome joins two sources:

1. C-ENT MQTT diagnostics for authoritative Group A/B health and fault context.
2. Home Assistant state, entity registry, device registry, and area registry for
   Group C presentation.

The frontend performs only presentation filtering. It may defensively recompute
simple display classifications, but it shall not create or clear a safety fault.

The Entity Audit view provides:

- summary cards for unhealthy Group A and B entities;
- a default problem-first list;
- explicit badges for A, B, and C membership;
- entity and device modes;
- text search and combinable filters;
- sorting by health severity, last update, last change, friendly name, area, and
  device;
- tooltips or details with the technical entity ID, owner, check calibration,
  reason code, and timestamps;
- on-demand recent history for one selected entity or device, including periods
  reported by Home Assistant as `unknown` or `unavailable`;
- Polish operator labels with English and German runtime translation parity.

The default view shall not render thousands of expanded rows at once. Filtering,
virtualization or pagination, and collapsed device groups bound rendering cost.

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
Reader request deadlines, startup grace, recovery
debounce and FTTI allocations remain internal safety policy. In particular, a
report-age timeout is not the network request timeout. A tighter requirement
shall cap a legacy global evaluation interval rather than wait for that slower
interval. Immediate life-safety alarm paths remain independent.

The following is a structural example; the entity ID is illustrative rather
than an installation mapping:

```yaml
calibration:
  entity_monitor:
    default_startup_grace_seconds: 60
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
            timestamp_source: "last_reported"

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
                timestamp_source: "last_reported"
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
- Group C uses Home Assistant's existing frontend state/registry connection.
- Frontend filtering uses memoized indexes and bounded rendering.
- A Group C registry or rendering failure cannot block Group A/B evaluation.

## 16. Security and privacy

- The feature uses the existing authenticated Home Assistant and MQTT paths.
- Entity states, friendly names, device names, and area names may reveal
  occupancy or household layout and shall not be sent to external services.
- Diagnostics shall not expose secrets stored in entity attributes.
- The backend publishes an allowlisted diagnostic attribute schema rather than
  copying arbitrary Home Assistant attributes.
- Group C remains inside the Home Assistant/SafetyHome authenticated session.

## 17. Verification

### 17.1 Backend unit tests

- Group A schema validation and calibration precedence.
- Group B registration for Temperature, Safety Doors, shared application inputs,
  and every common entity.
- Membership merge and conflict rejection.
- Shared physical entities with independent input/recovery/application-health
  fault families, single Group A membership and shortest-cadence acquisition.
- Missing, `unknown`, `unavailable`, stale, and recovered states.
- Startup grace and restart snapshots.
- Optional check calibration and target validation.
- Freshness and rate-of-change edge cases.
- Unchanged valid reports, future/malformed timestamps, expired reader evidence,
  failed or late batch reads, and preservation of active faults during transport
  loss.
- A stalled read with no state-change event and an unchanged cache shall cause
  the 5-second dependency group to assert unavailability within its 30-second
  detection budget, with reason `source_report_unavailable`.
- Independent failure and recovery debounce.
- Fault ownership and duplicate-fault prevention.
- Same-entity check aggregation, shared input aggregation with independent
  contributors, per-entity Group A fault separation, and no false clear.
- Two-field monitor calibration, legacy alias normalization/conflict rejection,
  derived scheduling and preservation of allocated detection budgets.
- Stable MQTT IDs and bounded attributes.
- No RecoveryManager registration or actuator service calls.

### 17.2 Backend integration tests

- AppCfgValidator and component registry integration.
- State-listener deduplication, shared batch scheduling, and single-flight reads.
- EventBus and FaultManager transitions.
- Application startup/termination and MQTT availability.
- Component-owned fault behavior remains authoritative.

### 17.3 Frontend tests

- Joining HA inventory with Group A/B diagnostics.
- Entity and device grouping.
- Combined filters and search.
- Sorting by health and timestamps.
- Friendly-name presentation with technical IDs in details.
- Information-only rows never appear as active faults.
- Large-inventory rendering remains bounded.
- English, Polish, and German state-label parity.

## 18. Traceability

| Safety source | Allocation |
| --- | --- |
| HARA 1.3.11 System Failure | Groups A/B entity availability, freshness, diagnostics, and alerts |
| SG-003 | C-ENT checks, fault ownership, no-false-clear behavior, and per-entity level-3 fault allocation |
| IR-009 | Entity state, timestamps, source membership, device, area, and information-only boundary |
| SYS-SR-ENT-* | Software requirements `SWR-ENT-*` |
| NFR-030/031 | Component-owned contracts and freedom from interference by Group C |
| NFR-040/041 | Per-check evidence, health counts, and freshness metrics |

Group C supports operator observability and maintenance but does not claim a
safety-goal allocation.
