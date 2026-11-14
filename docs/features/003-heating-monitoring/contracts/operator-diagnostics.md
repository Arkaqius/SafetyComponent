# Contract: Applied Heating Diagnostics and Operator Flow

Preserve `sensor.heating_system_<installation_key>` identities and fault state
codes. Add a diagnostic `schema_version: 2` and per-start `runtime_id`, shared by
the system payload and ledger/coverage projections. Pre-v2 or missing metadata is
explicitly unknown for the new evidence view, never full healthy coverage.

## Bounded payload

| Group | Fields |
| --- | --- |
| Identity/health | Schema/runtime generation, system key, friendly name, health and localized label; independent phase and label. |
| Coverage | Required-path assessments, admitted/excluded rule IDs, reasons, qualified/partial/unavailable outcome and retained-danger/uncertainty markers. |
| Rule evidence | Rule ID, raw evaluation code, active flag, admission, cause/reason, source age, values/units, original/current target, elapsed/remaining budget, inhibition and positive-recovery wait. |
| Retained context | Original symptom/fault/incident/system/room IDs, onset, historical source/contract fingerprint and explicit unevaluable status. |

Keep 13 rule summaries and at most 32 expanded contributor summaries per selected
rule, 64 input summaries and 32 retained summaries per installation payload; bound
complete payloads to 256 KiB UTF-8. Include total counts/truncation markers without
hiding active danger. Input values can be unknown; do not render missing age or
budget as zero. Secrets and unbounded raw HA/configuration payloads are excluded.

The summary health describes monitoring quality, not whether the boiler is
currently running. Required-path coverage is independently computed. Optional
exclusions remain visible, as do retained active H and diagnostic-only admission.
Unresolved retained danger must not disappear when no current heating system
entity exists; project it on the stable fault and global coverage surfaces too.

## Configuration and view flow

Configuration shall expose source roles, original-time selectors, independence/
equipment evidence and profile readiness with clear Polish guidance. System-owned
calibration is reviewed separately; the form shall not invent thresholds or add
editable actuator/service fields. Draft/save/applied state and existing revision
conflicts remain distinct; a save alone cannot change monitoring status.

Heating summary/details shall expose readable values, source ages, admission,
pending time and recovery requirements on desktop/mobile with keyboard labels.
Use EN/PL/DE equivalent runtime keys and Polish operator prose. Preserve notification
attempt history before entity history, with incident filtering and accurate
`accepted_by_home_assistant` semantics.

Disconnect, unknown availability, old schema or generation mismatch invalidates
current healthy/full claims. Historical active danger remains identified as
retained/unknown, independently of stale monitoring metrics.

Acceptance uses mock-only configured, partial, fully qualified, pending, active,
retained-only, corrupt-store, stale and disconnected fixtures. No live household
network calls or device commands are needed.
