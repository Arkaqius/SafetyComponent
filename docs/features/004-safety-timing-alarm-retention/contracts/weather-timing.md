# Contract: Weather Warning Timing

## Response Boundary

For modeled frost, wind, rain/storm and applicable official weather warnings,
the response shall fit 120 seconds total. Start at receipt of a usable normalized
hazard input with a relevant known-open aperture; if the conditions become
available separately, measure from their later availability. Include dispatch
after receipt; do not move the start past internal queueing. Pending hazard and
opening intervals run independently and concurrently, without historical cached
age being credited. Already-qualified current conditions need not restart when
the other condition becomes eligible.

| Stage | Maximum seconds | Completion |
| --- | --- | --- |
| Dispatch | 5 | Usable input/contact delivered to policy |
| Concurrent qualification | max(75, 60) | Weather confirmed; door/gate continuously open, or window open |
| Scheduling/reconciliation and decision | 9 + 1 | Current evidence rechecked, fault set and notification enqueued |
| Notification | 30 | Authorized target submission accepted by HA, or explicit delivery failure |
| Total | 120 | Warning submitted or failure explicitly exposed |

A failed/unavailable target is not successful warning delivery. Record deadline
failure and degraded notification coverage; do not delay or suppress the active
hazard. HA acceptance does not prove phone receipt or physical safety. The
physical-weather-to-cloud/poll delay remains outside this usable-input budget.

## Qualification and Configuration

- Set weather `default_persistence_seconds` and absent weather overrides to 75 s.
  Apply it to every modeled weather type and selected live official warning source,
  including `immediate` warnings; retain validity/freshness checks throughout.
- Decouple outdoor AQ persistence from the shared weather field with an independent
  system-owned `outdoor_air_quality.default_persistence_seconds: 300` and compiled/
  user `outdoor_air_quality.persistence_seconds`. Update schema/compiler/example/UI metadata
  together. Report unsupported timing configuration rather than silently coercing it.
- Retain 60 s door/garage/gate qualification and immediate window qualification
  after hazard qualification. Preserve the existing official `immediate` aperture
  exception without bypassing weather confirmation. Do not serialize 75 + 60 seconds.
- Existing installation weather overrides above the bound require explicit change
  during an authorized configuration/deployment workflow; never silently clamp them.
- Reject configurations exceeding the total allocation. Notification and scheduler
  allowances are real bounded stages, not extra grace after the 120-second limit.
- Count cumulative scheduler delay and rounding within 9 s; retain
  `T_ext_decision <= 1 s`. Add no generic SET debounce or startup grace. Repeated
  observations of the same continuous condition shall not reset onset.
- Timers re-evaluate without waiting for a subsequent provider poll. Late callbacks
  cannot reuse a previous session/token. Freshness loss resets pending confirmation
  and never clears an already-active hazard.
- Keep `clear_delay_seconds: 120`, hysteresis and authoritative positive-clear
  rules independent of the assertion-response change. AQ, indoor alarms and heating
  must not inherit the weather confirmation change.

## Acceptance

Use a fake clock across dispatch, qualification, opening, decision and notification.
Test all weather types/model/official sources, simultaneous eligibility, hazard
before/after aperture, door/window, exact deadlines and scheduler overruns.
At 74.999 s of weather continuity qualification is incomplete; at 75 s it is
eligible. A door at 59.999 s remains unqualified. Verify interruption resets,
stale/failed inputs, invalid overrides, independent AQ 300 s and clear delay 120 s.
Exercise a real in-process notification adapter with a bounded fake HA target;
failed acceptance must not be recorded as successful delivery.

## Traceability

SG-011/018 -> SYS-SR-EXT-010/041/051 -> SWR-EXT-006 and notification allocation.
This contract preserves the 120-second SYS limit. It changes the confirmation
allocation, not provider polling, physical-event assurance or actuator permission.
