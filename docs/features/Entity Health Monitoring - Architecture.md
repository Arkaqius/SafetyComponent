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
5. Availability and freshness are mandatory for Groups A and B. Additional
   checks are opt-in and require complete, type-compatible calibration.
6. Entity Monitor observes and diagnoses. It shall not call a Home Assistant
   actuator service or modify a monitored entity.
7. One underlying failure has one fault owner. Entity Monitor shall not create a
   duplicate fault when the owning component already defines failure semantics.
8. The complete Group C inventory is read through the authenticated Home
   Assistant frontend connection. It is not copied into MQTT attributes.

## 2. Goals

The feature shall:

- detect unavailable or stale entities that could mask a household safety
  condition or prevent an important automation from operating;
- let an installation explicitly select and calibrate externally owned safety
  dependencies, such as climate or heating entities;
- make SafetyFunctions aware of the health of every entity dependency consumed
  by its components and core services;
- expose one consistent view of explicit and component-owned entity health;
- aggregate multiple C-ENT-owned failures without losing per-entity or per-check
  context;
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
- Availability, freshness, optional sanity checks, failure/recovery debounce,
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
- mandatory availability and freshness calibration;
- optional accepted-state, type, range, rate-of-change, or stuck-at checks;
- failure and recovery debounce;
- an enabled/disabled flag that preserves the stable key.

Group A configuration is installation-specific and belongs under
`user_config.safety_components.EntityMonitorComponent`.

### 4.2 Group B - component dependencies

Group B makes SafetyFunctions self-aware. A component or core service registers
every entity whose loss affects its inputs or required diagnostics. Registration
contains:

- stable dependency key;
- `entity_id` resolved from validated configuration;
- owner component/core service;
- purpose and expected value kind;
- freshness contract;
- enabled optional checks;
- fault ownership;
- optional area/device context.

All entries in `user_config.common_entities` are registered as Group B records.
Component schemas or core policy own the calibration; an installation shall not
have to repeat the same entity in Group A.

Examples of Group B dependencies include temperature inputs registered by
`TemperatureComponent`, door contacts registered by `SafetyDoorsComponent`,
shared outside-temperature or occupancy inputs, and required provider or
aggregate diagnostics registered by `ExternalHazardComponent`.

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
                    - initial HA snapshot
                    - state listeners
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

One backend registry record exists per Group A/B Home Assistant entity ID. When
multiple owners or sources reference the same entity, the record preserves each
membership and merges compatible checks. The frontend joins those records with
the complete Group C inventory. A component-owned check cannot be disabled or
relaxed by Group A configuration.

Conflicting value kinds, units, or fault owners are configuration errors. Two
identical checks are deduplicated by their stable check key.

## 8. Check model

Every check returns a structured result containing check key, result state,
reason code, observed value, evaluation timestamp, relevant source timestamps,
and calibration identity.

### 8.1 Mandatory checks

| Check code | Purpose | Failure state |
| --- | --- | --- |
| `availability` | Detect missing entities, read failures, and native `unknown` or `unavailable` states | `unavailable` |
| `freshness` | Detect absence of a trustworthy state/attribute update within `max_silence_seconds` | `stale` |

The freshness timer starts after the initial snapshot and startup grace. It uses
the newest trustworthy update timestamp available from Home Assistant. The
configured timeout must reflect the source's real update behavior; a check shall
not infer a heartbeat from domain type alone.

For a safety-relevant dependency, the owning contract shall allocate a detection
budget from its applicable FTTI. Freshness timeout plus failure debounce shall
fit that budget. If the real source cadence cannot satisfy the budget, the
source cannot serve as the sole safety channel for that requirement.

### 8.2 Optional checks

| Check code | Required calibration | Result on failure |
| --- | --- | --- |
| `accepted_states` | Non-empty set of normalized allowed raw states | `degraded` |
| `value_type` | Expected boolean, string, integer, or finite number | `degraded` |
| `numeric_range` | Unit plus inclusive minimum and/or maximum | `degraded` |
| `rate_of_change` | Unit, sample window, maximum rise and/or fall | `degraded` |
| `stuck_at` | Expected update cadence, observation window, and minimum variation or transition count | `degraded` |

Optional checks are generic channel-health diagnostics. Safety-specific
thresholds, such as unsafe room temperature, remain in the owning Safety
Component and are not duplicated here.

Rate-of-change evaluation may reuse numeric sampling utilities from
`DerivativeMonitor`, but Entity Monitor owns its check result, calibration, and
fault semantics. Non-numeric, non-finite, unit-incompatible, stale, or
unavailable input is unevaluable and cannot pass a numeric check.

Stuck-at checking is disabled unless the policy declares a meaningful expected
variation. A door that remains closed or a switch that remains off for a long
time is not faulty merely because its state is unchanged.

## 9. Evaluation lifecycle

1. Validate Group A configuration and component/core dependency declarations.
2. Resolve entity IDs, area names, and Group B registrations.
3. Merge records and reject incompatible contracts.
4. Register bounded MQTT diagnostics for Groups A and B.
5. Read one initial Home Assistant state snapshot.
6. Subscribe to state updates for the deduplicated Group A/B entity set.
7. Apply startup grace, then schedule freshness evaluation.
8. Evaluate mandatory checks before optional checks.
9. Update per-check debounce state and the combined entity health state.
10. Publish diagnostics and emit only C-ENT-owned symptom transitions.
11. Cancel listeners and timers before MQTT availability is set offline.

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
| Safety Mechanism | `sm_entity_health` |
| Symptom | `EntityHealthFailure{EntityKey}{CheckKey}` |
| Fault | `EntityHealthFailure` |
| Level | 3 |
| Recovery action | None |

The fault aggregates all active entity/check symptoms and retains:

- friendly name and entity ID;
- source groups and owner;
- failed check and reason code;
- current and last valid values;
- last change, last update, failure-start, and evaluation timestamps;
- area and device when known.

For Group B, the dependency declaration selects `entity_monitor`, `component`,
or `none` as fault owner. When `component` is selected, C-ENT provides health
diagnostics but does not emit a duplicate symptom. `none` is allowed only for an
informational component diagnostic and never weakens an existing component
safety contract.

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

Global policy belongs in `app_config.calibration.entity_monitor`. Explicit
installation selection belongs in
`user_config.safety_components.EntityMonitorComponent`.

The following is a structural example; the entity ID is illustrative rather
than an installation mapping:

```yaml
app_config:
  calibration:
    entity_monitor:
      startup_grace_seconds: 60
      default_failure_debounce_seconds: 15
      default_recovery_debounce_seconds: 60

  faults:
    EntityHealthFailure:
      name: "Safety entity health failure"
      level: 3
      related_sms:
        - "sm_entity_health"

user_config:
  components_enabled:
    EntityMonitorComponent: true

  safety_components:
    EntityMonitorComponent:
      explicit_entities:
        BedroomTrv:
          entity_id: "climate.bedroom_radiator"
          area_id: "bedroom"
          description: "Heating dependency used by the bedroom automation"
          max_silence_seconds: 45
          failure_debounce_seconds: 15
          recovery_debounce_seconds: 60
          checks:
            value_type:
              type: "string"
            accepted_states:
              values: ["heat", "off", "auto"]
```

Group B declarations are created from already validated component configuration
and code-owned contracts. They are not copied into this user configuration.

Strict validation rejects:

- missing or invalid entity IDs;
- duplicate stable keys pointing to different entities;
- non-positive timing values;
- a safety freshness/debounce combination that exceeds its allocated FTTI
  detection budget;
- empty accepted-state sets;
- range checks without a bound;
- numeric checks without units;
- rate checks without a sample window or direction bound;
- stuck-at checks without cadence and variation semantics;
- incompatible checks for the declared value type;
- Group B ownership or calibration conflicts.

## 15. Performance and boundedness

- Group A/B state listeners are deduplicated by entity ID.
- Freshness uses one scheduler over deadline entries rather than one unbounded
  polling loop per entity.
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
- Group B registration for Temperature, Safety Doors, External Hazard, and every
  common entity.
- Membership merge and conflict rejection.
- Missing, `unknown`, `unavailable`, stale, and recovered states.
- Startup grace and restart snapshots.
- Optional check type and unit validation.
- Rate-of-change and stuck-at edge cases.
- Independent failure and recovery debounce.
- Fault ownership and duplicate-fault prevention.
- Multi-entity fault aggregation and no false clear.
- Stable MQTT IDs and bounded attributes.
- No RecoveryManager registration or actuator service calls.

### 17.2 Backend integration tests

- AppCfgValidator and component registry integration.
- State-listener deduplication.
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
| SG-003 | C-ENT checks, fault ownership, no-false-clear behavior, and level-3 fault aggregation |
| IR-009 | Entity state, timestamps, source membership, device, area, and information-only boundary |
| SYS-SR-ENT-* | Software requirements `SWR-ENT-*` |
| NFR-030/031 | Component-owned contracts and freedom from interference by Group C |
| NFR-040/041 | Per-check evidence, health counts, and freshness metrics |

Group C supports operator observability and maintenance but does not claim a
safety-goal allocation.
