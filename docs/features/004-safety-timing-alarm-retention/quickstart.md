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

These scenarios become regression cases during implementation; passing the
current baseline suite alone does not establish that these defects are fixed.

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
