# Validation Guide: Safety Timing and Indoor Alarm Retention

## Prerequisites

Use Python 3.10+, repository backend development dependencies and the Node version
in `frontend/.nvmrc`. Use the bundled AppDaemon stub, fictional installation
fixtures, fake monotonic clock and fake HA notification target. No live Home
Assistant session, detector stimulation or household command is required.

## Acceptance Scenarios

1. Exercise the complete weather response from usable input and known-open
   aperture. Measure the [allocated stages](contracts/weather-timing.md), including
   dispatch and target acceptance, and assert total <=120 s for windows and doors.
   Repeat every weather type and selected live source with failed/stale evidence.
   Assert AQ remains 300 s and positive-clear delay remains 120 s.
2. Assert an indoor alarm then inject a one-day-old off snapshot. Confirm no HEAL.
   Supply a reviewed live clear transition and test 29.999/30 s boundaries. Restart,
   reconnect or interrupt at second 29: a new complete interval is required.
3. Persist active gas danger and inhibition; remove the detector, change its binding
   or disable the component, then restart. Inspect the very first fault/global
   output and restriction policy: original danger remains active/unverified.
4. Fail checkpoint SET/CLEAR, convert legacy orphan records, corrupt/miss checkpoint
   with active journal evidence, and exceed record/byte limits. No successful-looking
   recovery, inhibition release or silent active-record eviction is permitted.
   Include corruption after alarm HEAL with a retained gas latch, and crash after
   durable CLEAR followed by a newer SET whose write has not completed. Verify
   dirty-session restoration exposes uncertainty rather than a healthy state;
   file absence is not proof of a first installation.
5. Inspect frontend retained/disabled-but-active diagnostics and EN/PL/DE runtime
   labels. Assert zero actuator calls and no historical notification replay.
6. Parametrize temperature, doors, Entity Monitor, heating, indoor alarms and
   external hazards against the [shared lifecycle](contracts/shared-mechanism-lifecycle.md).
   Repeat start/stop and same-instance restart, disable during qualification,
   deliver late callbacks and change only a location label. Confirm exact intended
   subscriptions, released owned handles, zero obsolete effects and no extra input.
   Recovery simulation must report unevaluable distinctly and have no live effects.
7. Inject an MQTT exception at the original pre-fault-event failure point and a
   throwing first response consumer. Confirm authoritative danger, independent
   consumer admission and local failure evidence under the
   [isolation contract](contracts/response-isolation.md). No diagnostic retry may
   duplicate an alarm transition or action.
8. Use a non-household supported packaged AppDaemon/HASS harness with callback
   service completion: immediate callback, None result, explicit failure, delayed
   result and one never-completing target. Confirm scheduling return is not
   acceptance, healthy independent targets/recovery proceed within their budgets,
   and no forbidden service parameters are sent. Repeat app reload while the old
   lease remains unresolved; verify fixed process-wide credits, quarantine,
   byte/count limits, overload and duplicate/obsolete completion handling.
9. Race queued local-output intent with gas inhibition and recovery command with
   token expiry/new restrictions. Observe immutable writer acknowledgement and
   current authorization before any mocked dispatch. A timeout cannot prove
   physical cancellation, so no automatic command replay is allowed. Test MQTT
   discovery/attributes/state/availability ordering across old/new generations,
   failure and heartbeat; desired projection is not accepted publication.

These scenarios become regression cases during implementation; passing the
current baseline suite alone does not establish that these defects are fixed.

The fake service transport implements the same callback contract as the supported
runtime and records bounded submission/completion times. Ordinary AppDaemon stub
tests alone cannot establish real HASS callback forwarding semantics. The declared
dependency is >=4.5,<5; a local installed version outside that range is not runtime
admission evidence. No test harness may connect to the household instance.

## Evidence Matrix

### Indoor delivered-event contract

The offline [packaged event probe](../../../backend/tests/test_appdaemon_indoor_event_contract.py)
captures actual AppDaemon 4.5.13 HASS `receive_event`, event/state processing and
plugin start/stop delivery. Its [sanitized fixture](../../../backend/tests/fixtures/indoor_event_contract.json)
contains fictional alarm, clear, same-state and unknown-to-clear transitions.
Initial namespace synchronization emits no state transition. The HASS adapter
forwards `origin`, `time_fired` and `context` in `data.metadata`, together with
the old/new HA state records. No physical producer epoch, sequence or timestamp
is supplied or inferred from these HA fields.

The packaged binary profile's `ha_state_changed_v1` contract admits a delivered
LOCAL alarm-to-clear edge whose actual old-state watermark matches the accepted
current-session alarm, with ordered HA transition/update/event times and context.
It requires a complete newly observed monotonic 30-second interval and matching
readback. A missing/unreviewed contract retains positive alarm admission but
cannot authorize recovery. This proves HA event continuity within that contract;
it does not prove physical detector heartbeat or original measurement freshness.
Replay, cached/initial off, attribute-only off, interruption, reconnect and
disable/re-enable do not create or resume a recovery interval.

Run with the same isolated `SAFETY_APPDAEMON_PYTHON` interpreter used below:

```powershell
pytest backend/tests/test_appdaemon_indoor_event_contract.py backend/tests/test_indoor_clear_authority.py backend/tests/test_internal_environmental_hazard_component.py backend/tests/test_internal_environmental_hazard_startup.py
```

This source-admission evidence is separate from durable CLEAR acceptance (US3).

### Implementation baseline — 2026-11-16

Python 3.10.5: `python -m ruff check backend` and `python -m mypy` passed;
the configured mypy scope contains 13 source files. Both backend pytest runs
passed (1440 tests), including `--cov=backend --cov-report=term-missing`.
These establish a baseline, not feature-004 acceptance.

At baseline, the public configuration/schema used weather persistence 300 seconds
and had no independent AQ persistence field. T035/T036 change the default to 75 s
and give AQ a separate 300 s interval; installed explicit weather overrides above
the allocation are rejected and require correction in an authorized installation
workflow.
Neither ignored `backend/config/user_config.yml` nor `backend/app_cfg.yaml`
exists locally; no private installation values were read or changed.

Three ignored historical deployment snapshots were inspected only for aggregate
weather timing policy. None has an explicit persistence override; they do not
establish the configuration of the current deployment. No snapshot was changed
or included in source control.

Installed AppDaemon 4.4.2 is outside `>=4.5,<5`; it cannot satisfy T031/T049.
The initial Node 18.20.8 also differs from `frontend/.nvmrc` (20). Its frontend
test failures and refusal to run Playwright require rechecking under Node 20;
they do not establish a product regression. Existing formatter failures are
tracked separately from changed files.

### Packaged callback evidence and approved acceptance policy

The offline [adapter regression](../../../backend/tests/test_appdaemon_service_contract.py)
exercises actual packaged AppDaemon 4.5.13 HASS, service and websocket result
processing with only a fictional socket substituted. It confirms:

| Case | Scheduling return | Callback result |
| --- | --- | --- |
| Successful HA response without a body | `None` | Envelope with `success: true`, `result: null`, `ad_status: OK` |
| HA rejection | `None` | Envelope with `success: false` and error |
| Response timeout | `None` | Envelope with `success: false`, `ad_status: TIMEOUT` |
| Disconnected plugin | `None` | Bare `None`; zero socket requests |
| Transport exception | `None` | Bare `None`; runtime catches the exception |
| Stalled fictional send | `None` | No completion before explicit harness cleanup |

Completion runs on the AppDaemon event-loop thread, distinct from the invoking
application worker. Callbacks must enqueue results for owner validation.
Bare `None` is ambiguous and cannot establish HA acceptance from this adapter.
On 2026-11-16 the maintainer approved requiring Boolean `success: true` in the
completion envelope. A successful empty body (`result: null`) is valid within
that envelope. The extended T031 probe verifies the actual packaged HASS path
through the service broker as well as directly. It checks owner-only application,
lease-before-completion and unresolved-resource quarantine. It does not establish
whole-manager isolation, successful phone delivery or deployment readiness.

Reproduce without connecting to Home Assistant:

```powershell
$serviceContractEnv = Join-Path ([IO.Path]::GetTempPath()) 'safetycomponent-service-contract'
python -m venv $serviceContractEnv
$env:SAFETY_APPDAEMON_PYTHON = Join-Path $serviceContractEnv 'Scripts/python.exe'
& $env:SAFETY_APPDAEMON_PYTHON -m pip install -r safety_component/requirements.txt
pytest backend/tests/test_appdaemon_service_contract.py -q
```

The test subprocess uses Python isolated mode so the bundled test stub cannot
shadow the installed adapter. Without the interpreter variable this test skips;
a skipped/stub-only run is not supported-runtime evidence.

Broker and mobile-target regressions run without the packaged interpreter:

```powershell
pytest backend/tests/test_service_dispatcher.py backend/tests/test_mobile_push_dispatch.py
```

Their fake-clock results establish bounded infrastructure and target independence.
Production bootstrap injects the broker into NotificationManager, local outputs,
MQTT and recovery. The snapshot writer and root stalled-target admission are
covered by the US4 tests; the complete weather/indoor response timelines remain
separate acceptance gates. The adapter's legacy direct interface is tested only
as a compatibility boundary.

### Indoor persistence and restart admission

The owner loads before monitor enablement, inactive-fault filtering and first
fault/global publication, even when the indoor monitor is absent. Version 2
retains original known incident/binding identities, independent gas inhibition
and historical clear proof. Version 1 lacks those original identity fields:
`legacy_unattributed` preserves actual flags without assigning an invented
hazard, entity, profile or incident to current replacement equipment.

Dirty ownership is acknowledged through the process writer before source ingress.
SET stays effective in memory when storage fails; CLEAR remains active until an
exact successful snapshot acknowledgement and a final current-source/owner check.
A newer SET or reentrant source change invalidates the older acknowledgement.
One in-flight and one coalesced pending snapshot bound storage work. A clean
shutdown marker is admitted only after ingress/candidates are fenced and earlier
writes acknowledged. Admission alone is never claimed as successful persistence.
If a retired owner's storage remains unfinished beyond the bounded startup wait,
the replacement retains in-memory danger and uncertainty and admits no competing
snapshot writes for that session. A later orderly reload can read the completed
old snapshot; an earlier read must never overwrite its eventually durable alarm.

A single bounded process witness distinguishes the exact preceding owner and
storage from an intervening failed-marker launch. **A full process restart loses
this witness and restores unverified history and fail-closed gas restriction,
even from a clean checkpoint.** A successful new marker does not remove that
historical uncertainty. This is distinct from confirmed physical gas. It issues
no off/reset command. Original durable records survive; details of a never-durable
alarm cannot be reconstructed.

`commissioned_checkpoint` and a current-launch receipt are internal offline
admission boundaries for separately reviewed virgin-installation evidence, not
an operator gas reset or an automatic empty-file rule. They must not overwrite
retained state or conflict with any indoor journal history, including a CLEARED
gas alarm. The repository adds no public control to release an independent latch
or erase unknown prior history. Installation review remains necessary before
deployment; test receipts refer only to fictional fixtures.

Summary diagnostics include at most 64 detailed retained records and reserve
60,000 bytes for that list within a 64 KiB payload. Fault details have their own
smaller allowance alongside contributors and freeze frame. Total/omitted counts
and danger/gas aggregation include every retained contribution. Polish UI shows
retained/disabled states and pending durable clear; EN/PL/DE runtime labels have
equivalent meaning. HEAL never grants safe re-entry.

### Six-family lifecycle evidence

The actual-registration matrix captures callbacks passed to each production
registrar, repeats start/stop and same-instance restart, changes child eligibility
and presentation metadata, injects cancellation failures and delivers old
callbacks. It verifies zero obsolete state changes or new service submissions.
Child stop/disable discards pending qualification while preserving shared inputs
and active assertions. Independent regressions cover door, entity, indoor and
external clear intervals and notification stop when final persistence throws.

| Factory | Declared source ownership (domain timers are separate) |
| --- | --- |
| Temperature, two rooms | 12 child state inputs; two shared derivative samplers |
| Doors | One child contact input; optional condition adds its explicit input |
| Entity Monitor | One parent state input and normal/fast samplers; children share them |
| Heating fixture | One parent sampler; no duplicated child source |
| Indoor, two detectors | Two parent state inputs and three HA state/session event inputs |
| External, one window | One parent contact input and three scoped EventBus subscriptions |

The typed read-only simulation boundary preserves eligible negative,
unevaluable/inhibited/disabled outcomes without publication, qualification or
telemetry. Recovery rechecks current symptom/component/mechanism registries,
runtime and generation after simulation; obsolete proof is denied. Heating's
unsupported hypothetical kernel remains explicitly unevaluable.

The configured mypy scope contains 33 files, including the indoor schema,
observation, owner store and monitor, shared core, response managers/adapters,
MQTT projection and ExternalApiRuntime. The other five domain adapters and
derivative sampler are not claimed as fully mypy-verified. Queue admission is
distinct from HA acceptance and snapshot acknowledgement. A stopped owner cannot
revoke an already handed-off physical effect; process-owned leases and offline
MQTT barriers remain tracked behind unresolved calls.

### Acceptance allocation

| Scope | Acceptance evidence |
| --- | --- |
| FR-001..003; SC-001 | Scenario 1, full 120 s timeline and invalid overrides |
| FR-004..007; SC-002/003 | Scenario 2, authority/session and exact recovery boundaries |
| FR-008..012; SC-004/005 | Scenarios 3/4/9, owner bootstrap, durable CLEAR and crash ordering |
| FR-013; SC-004/005 | Scenario 5, operator states, bounded payloads and runtime translation parity |
| FR-014/015/023; SC-006/010 | All scenarios, no real commands/replay and unchanged domain safety semantics |
| FR-016/017; SC-007 | Scenario 7, response ordering and publication/consumer exception isolation |
| FR-018; SC-008 | Scenarios 8/9, hung target, bounded resource capacity and independent progress |
| FR-019..022; SC-009/010 | Scenario 6, six-family lifecycle and typed execution/simulation outcomes |

## Required Commands

From repository root:

```powershell
python -m ruff check backend
python -m mypy
pytest backend/tests
pytest backend/tests --cov=backend --cov-report=term-missing
git diff --check
```

From `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
npm run test:ui
```

Use the mock Playwright configuration for browser tests. Report scoped mypy
coverage accurately and separate unchanged formatting failures from new failures.
Before implementation delivery, map each FR/SC in the [specification](spec.md)
through the [contracts](contracts/indoor-recovery-retention.md) to executable
tests and captured results. A deployment remains a separate authorized workflow.
