# Safety Routines

## Purpose and boundary

Safety Routines (C-ROUTINE) shall provide advisory, timestamped checks before
household transitions such as bedtime or leaving. A run shall evaluate selected
sources directly; absence of a continuous-monitoring fault shall not count as
positive evidence. The service shall not own household faults, clear existing
alarms, change continuous safety coverage, or dispatch actuators. Its storage
health shall contribute to the existing application persistence diagnostics.

The controlling contracts are [SYS](../sys/SafetyConcept%20-%20SYS.md),
`SYS-SR-ROUTINE-001..006`, and [SSRD](../sys/SafetyComponent%20-%20SSRD.md),
`SWR-ROUTINE-001..008`. Existing HARA hazard/goal allocations remain unchanged:
advisory checklists shall not independently justify a reduction of residual risk.

## Configuration ownership

`user_config.installation.safety_routines` shall map stable PascalCase IDs to
scenario definitions. Omission shall compile to an empty registry without
changing existing configuration behavior. The compiler shall emit
`user_config.safety_routines.routines`; startup shall validate that runtime
contract again. This service shall not be registered as a fault-producing
`SafetyComponent` or attach its optional sources to continuous C-ENT coverage.
Missing sources shall yield an unknown check result, rather than preventing
unrelated continuous monitoring from starting.

The [installation example](../../backend/config/user_config.example.yml) contains
disabled bedtime and leaving scenarios. A scenario shall contain `name`,
`enabled` (default true), `checks`, and optional `triggers`, `delay_seconds`
(default 0), and `observation_seconds` (default 0). New scenarios in the operator
form shall default to disabled. Installation names shall be shown as supplied.

| Check field | Contract |
| --- | --- |
| `name`, `entity_id` | Human-readable name and stable HA source ID. |
| `kind` | `state` (default) or `numeric_range`. |
| `expected_states` | Exact, case-sensitive HA state strings for a state check. |
| `attribute` | Optional value attribute for state checks only. |
| `minimum`, `maximum`, `unit` | Inclusive numeric bounds, at least one bound, and the exact HA `unit_of_measurement`. No implicit conversion. |
| `observed_at_entity_id` | Entity whose state is the original observation timestamp. |
| `observed_at_attribute` | Original observation timestamp attribute on the value source. Exactly one timestamp selector is required. |
| `max_age_seconds` | Maximum observation age, 1–86400 seconds, default 300. |
| `condition` | Optional reading with the same source/time fields and disjoint `pass_states` and `skip_states`. |

Original timestamps shall be timezone-aware ISO 8601 or numeric Unix seconds.
HA acquisition time, `last_changed`, and `last_updated` shall not be substituted.
The installer shall bind an actual original observation time, not a cached-value
publication timestamp. State checks shall compare actual sensor state codes;
for example, a contact may use `off` for closed. Numeric checks shall reject
booleans, malformed/non-finite values, absent/wrong units and missing bounds.

Triggers shall be either `{kind: event, event: household_leaving}` or a complete
state transition with `kind: state`, `entity_id`, `from_state`, and `to_state`.
No initial-state callback or startup shall count as a transition. Events starting
with `safety_routine_` shall be reserved to prevent self-trigger loops. Multiple
triggers on one scenario shall each be sufficient to request a run.

## Evaluation and lifecycle

Each accepted run shall receive a new `run_id` and retain its own scenario name,
expectations, observations and timestamps. Lifecycle states shall be `waiting`,
`running`, `completed`, `cancelled`, or `interrupted`. Pending, cancelled and
interrupted runs shall have aggregate status `unknown`. Completion shall be
confirmed by the backend, never inferred from a client countdown.

After the delay, a zero-length observation window shall evaluate once. A longer
window shall evaluate immediately, at intervals no greater than five seconds,
and at its end. Successive passing samples shall require advancing original
source timestamps. Re-reading a cached observation shall not prove sustained
normal behavior. More than ten seconds between callbacks or backward clock
movement during sampling shall interrupt the run. These are sampled observations,
not proof of physical conditions between samples.

| Result | Meaning |
| --- | --- |
| `pass` | Qualified evidence meets the configured expectation. |
| `problem` | Qualified evidence violates the expectation. |
| `unknown` | Source, timestamp, unit, numeric value or applicability cannot be qualified. |
| `skipped` | A qualified condition explicitly selects a configured skip state. |

Within a window, later passing samples shall not erase a problem or evidence gap.
Known applicability changes shall not fabricate a pass. A problem shall take
precedence in the displayed result; `evidence_incomplete` shall additionally
preserve any missing-evidence observation. Aggregate precedence shall be problem,
unknown, pass, then `not_applicable` when all checks are skipped. Counts shall
preserve the individual result categories.

At most one run per scenario shall be active. Overlap shall return
`already_running`. Repeating a retained manual request ID shall return its
original run, without evaluating again. A new manual request ID shall create a
new run. Idempotency shall be bounded to retained history; automatic triggers
shall not have durable event IDs. Finished reports shall remain historical after
source/configuration changes. Restart shall mark persisted unfinished runs
interrupted without replay; shutdown shall cancel timers and listeners.

## Reports and event interface

The service shall use Home Assistant's authenticated event transport. It shall
not add MQTT entities containing full reports or broadcast installation config.
Requests on `safety_routine_request` shall contain `request_id` (1–128 ASCII
letters, digits, `.`, `_`, `:`, or `-`) and an action:

| Action | Additional fields | Response |
| --- | --- | --- |
| `list` | None | Configured scenario summaries and newest-first run summaries. |
| `run` | `routine_id` | Accepted/current report or explicit error. |
| `report` | `routine_id`, optional `run_id` | Requested historical report; omission selects the latest. |
| `cancel` | `routine_id`, `run_id` | Cancelled report, or `run_unavailable` for a stale request. |

Responses on `safety_routine_response` shall contain `version: 1`, correlated
`request_id`, `storage_available`, and either `error`, `run`, or `routines`/`runs`.
Completed runs shall emit `safety_routine_completed` with summary fields including
`routine_id`, `run_id`, `status`, counts and timestamps, permitting installation
automations to consume completion. The service itself shall not send mobile
notifications or operate household devices.

SafetyHome shall expose the Polish scenario list, manual run, cancellation,
history and report details at `#/safety-routines`, with a configuration editor at
`#/configuration/safety_routines`. It shall subscribe before sending, correlate
responses, enforce an eight-second response timeout, clean up subscriptions, and
show disconnection/transport uncertainty. A timeout shall not prove a run failed
to start. Historical success shall be labeled as a result at the time of checking.
Packaged result/reason labels shall have EN/PL/DE parity.

## Resource and persistence limits

The closed schema shall permit at most 16 scenarios, 24 checks per scenario,
four triggers per scenario, a 600-second delay and 300-second observation window.
Identifiers and source/value strings shall be bounded. Limits are service code
policy; no new `system_config.yml` calibration key is introduced.

The existing SQLite database shall store at most 20 runs in the independent
`safety_routines` store (8 MiB bound). Active runs shall not be evicted. Reports
shall be saved before delayed execution and at completion/cancellation/shutdown.
Responses shall be limited to 256 KiB; lists shall omit check details. Storage
failures shall be logged, visible in application diagnostics and reported to the
UI; memory-only results shall not be represented as durably saved. Unsupported
or malformed stored history shall not become a successful report.
If history cannot be loaded, the service shall keep new reports in memory and
shall not overwrite unreadable history; a successful restart shall be required
to resume durable writes.

## Verification

The Polish [operator guide](../../frontend/SAFETY_ROUTINES.md) explains the
away/bedtime configuration workflow and report interpretation. Installation
bindings and commissioning evidence remain private; examples do not constitute
default enabled scenarios or evidence of qualified live sources.

[Backend contract tests](../../backend/tests/test_safety_routines.py) shall cover
configuration, quality, numeric units, conditions, report aggregation, repetition,
overlap, restart, timer/read/storage failures and no actuator calls.
[Frontend contract tests](../../frontend/src/domain/safetyRoutines.test.ts) shall
validate responses and reject impossible success. Browser tests shall cover
manual runs, immutable history, partial evidence, disconnects and configuration
access on desktop/mobile. The standard backend/frontend suites and local
documentation links shall be checked before publication.
