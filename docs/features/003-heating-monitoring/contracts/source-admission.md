# Contract: Source and Profile Admission

## Source model and boundaries

Preserve `user_config.model_version: 2`, `installation.heating_systems`, existing
semantic bindings/profile selection, configuration revisions and separate restart.
System configuration owns calibrated policy; installation configuration owns
source/room/circuit mappings. No arbitrary expressions or service calls enter
either the bindings or commissioning record.

Add optional `installation.heating_systems.<key>.qualification` with
`schema_version: 1`, `equipment_ref`, `policy_fingerprint`, `reviewed_at` and
`bindings`. Each binding key identifies an installation role or `rooms.<room>.<role>`
and supplies `producer_ref`, `meaning`, `cadence_bound_seconds`,
`independence_basis` and optional `topology_basis`. Limit the map to 192 binding
records, each text field to 512 characters and each serialized qualification
object to 128 KiB UTF-8. Reject unknown fields, missing/mismatched roles and
nonfinite/nonpositive cadence. `reviewed_at` is an aware UTC time, not a source
measurement time. `policy_fingerprint` must match the reviewed selected policy.
Use a 64-character lowercase SHA-256 fingerprint of the canonical selected
policy; exclude friendly labels, observation samples and secrets. Binding
fingerprints separately cover semantic selectors, roles, cadence and ownership.

Runtime readiness is derived; there is no user-supplied `qualified: true` switch.
Synchronize this schema in compiler, runtime validation, configuration metadata,
examples and UI. The record supports a reviewed commissioning process; a filled
text reference alone is not proof of a physical fact or a substitute for tests.
Existing Diagnostic-only files remain readable and explicitly partial. Introducing
additional evidence must not reinterpret their contact data as measurement data.

The existing authenticated `GET /api/config` gains additive read-only
`heating_qualification` metadata for the saved source: selected policy fingerprint,
required evidence and validation/readiness reasons per configured system/rule.
Bound it to 64 KiB UTF-8, 16 systems and 13 rule summaries/system with truncated
reason lists explicitly marked. Existing import/save validation reports invalid
admission through its current bounded error format; revisions and atomic writes
remain unchanged. No new device-control endpoint is added. This metadata is
saved-source guidance, never proof of the currently applied monitoring state or
of physical commissioning. Draft readiness must be labeled as draft.

## Evidence required before operational admission

| Path | Evidence |
| --- | --- |
| Input supervision | Actual producer contact/observation contract and allocated age/acquisition/qualification path. |
| Need/request | Independent qualified room temperature, effective current target and permission versus the associated controller request. |
| Boiler response | Issued heat request, actual boiler response, DHW/phase, physical flow target and declared bounded inhibition context. |
| Thermal output | Original flow/return observations with coherent source times, units, sufficient sampling and reviewed equipment policies. |
| Pump/distribution | Actual supported pump/load/hydraulic meaning; a relay command is not proof of circulation. |
| Room delivery | Assigned room/circuit and evidence of a real delivery attempt, qualified room trends and comparable recovery. |
| Device/thermal limits | Current manufacturer-defined code meanings and reviewed equipment/firmware operating/absolute limits; historical errors remain historical. |

See [existing provenance guidance](<../../Heating Input Provenance.md>). New unchanged
samples may advance observation time only when actually observed again. Cached
republishing, transport connection and HA write time do not refresh field age.

## Admission outcome

Each rule is admitted only if policy, bindings, producer evidence, independence,
topology and timing validate together. Missing facts are actionable exclusions or
validation errors. Preserve the valid draft and revision on rejected save.

Required full-chain paths are need, request, response, thermal output, room
delivery and input quality, plus current-code interpretation where the equipment
reports codes. Optional cycling/maintenance/hydraulic checks remain separately
visible and may be excluded without falsifying what the required chain covers.
Each path names its contributing admitted rules; there is no full-coverage shortcut
from selecting all R01..R13.

Broader profiles are admitted only after evidence review. No generated example
supplies fictitious production limits. External producer changes are recorded as
prerequisites owned outside SafetyComponent when necessary.

## Acceptance

- Replay, missing/future times, wrong units and contradictory source meaning fail.
- Same-group controller request/permission cannot establish independent need.
- Wrong equipment/profile/calibration or insufficient cadence fails admission.
- Valid fictional contracts with different entity names produce equal semantics.
- At least two materially different equipment/source profiles vary units, raw
  codes, reviewed policy/version references and supported capabilities; equivalent
  qualified facts yield equivalent decisions without device-specific rule logic.
- Current code classification is tied to reviewed manufacturer/model/firmware
  versions: operational states, active faults, maintenance and history remain
  separate, and unknown codes never imply healthy or faulty operation.
- Diagnostic-only files remain partial, and no existing heating device command is
  sent by import, validation, save, restart or recovery.
