# Data Model: Safety Timing and Indoor Alarm Retention

## Weather Response Allocation

System-owned positive finite stage limits: dispatch 5 s, weather persistence 75 s,
decision/reconciliation 10 s, notification 30 s; existing door qualification 60 s
runs concurrently. Validate `dispatch + max(weather, opening) + decision + notify
<= 120`, including configured overrides. AQ uses a separate 300 s default and
does not inherit the changed weather value. Reject NaN, infinity and negative or
unbudgeted timing. A 120 s weather-persistence override is invalid.

## Weather Exposure Episode

Key: existing provider/hazard/opening identities, plus a receiver-session/token.
Track usable observation identity, authoritative validity/freshness, monotonic
hazard onset, known-open onset, qualification deadlines and stage timestamps.
Never credit age of a cached observation as elapsed receiver qualification.
Hazard and aperture qualification are independent concurrent conditions. A source
gap invalidates hazard qualification; an unknown/closed contact invalidates its
opening qualification. An old callback cannot assert a new episode.

## Indoor Observation

Fields: stable detector/entity/channel/profile identity, profile version and binding
fingerprint; normalized alarm/clear/test/hush/unknown state; provenance
`live_event`, `startup_snapshot`, `readback` or `restored_checkpoint`; receiver
session and monotonic receipt; available HA transition/context metadata; optional
reviewed producer epoch/sequence/time. Absence remains explicit. A receiver session
is never substituted for a producer epoch. No monotonic value survives a reboot
as valid timing proof.

## Clear Qualification

Key: incident, detector, current binding fingerprint, receiver session and unique
qualification token. Contains accepted authoritative clear identity and monotonic
start/deadline. State transitions:

`active/unverified -> qualifying -> durable_clear_pending -> cleared`

Invalid observation, discontinuity, binding change or intervening alarm returns
to active/unverified and invalidates the token. Default duration is 30 newly
observed seconds. A readback confirms continuity only within the reviewed source
contract; it cannot establish source freshness by itself. Failed durable clear
remains active with a persistence diagnostic.

## Retained Indoor Assertion

Stable symptom/fault/incident/detector identities, trusted hazard, original source
and binding/profile fingerprint, activation time, bounded cause/context,
reviewed clear watermark if available, and separately latched gas inhibition.
Classification: current, retained-unverified or orphan. Do not derive a trusted
fault name from arbitrary checkpoint content: reconcile against an allowlisted
indoor hazard catalog. Preserve original incident identity across restarts and
configuration removal. Cleared alarm and active gas inhibition are valid together.

## Owner Checkpoint

Existing namespace `internal_environment_state`, strict envelope schema version 2,
generation, owner-session clean/dirty marker and records. Maximum 4096 records
and 1 MiB UTF-8 encoded envelope.
Bound technical IDs to 128 characters, entity IDs to 255, display text to 256,
each cause/context to 4 KiB and depth 4. Validate finite numbers and UTC-aware
timestamps; reject duplicate/malformed identities and oversized data. Never
truncate or evict active assertions to fit these limits. Current detector
admission remains its separate default 64 / maximum 256.

Single writer, one in-flight and one coalesced pending snapshot; monotonic
generations prevent stale acknowledgements. Atomic write acknowledgements bind
to incident/generation/candidate. SET failure preserves in-memory danger and gas
restriction. CLEAR failure denies HEAL/release. No synchronous retry may block
the immediate alarm path. Legacy active records are conservatively converted;
legacy clear times remain historical. Corruption or missing checkpoint with active
journal evidence produces retained unknown danger and persistence uncertainty.

Commit an owner dirty-session marker before admitting observations. An unclean
restart cannot treat the last durable CLEAR as proof that no newer positive SET
was observed: reconcile owner/journal incident generations and preserve explicit
unknown danger/restrictions wherever absence of a newer assertion is unproven.
Only stop ingestion, drain all writes and atomically mark clean for orderly
shutdown. Failure to establish the marker leaves persistence degraded and recovery
ineligible, without suppressing immediate positive alarms. Exact cause/identity
of a never-durable observation cannot be reconstructed; expose this limitation
as uncertainty rather than inventing evidence.

Checkpoint loss/corruption after prior ownership also leaves gas inhibition
unknown and fail-closed even if the alarm journal says CLEARED. Journal HEAL
does not prove release of the independent latch. File absence alone cannot prove
a virgin installation; cold-start admission requires explicit reviewed evidence
of no prior owner state. Unknown history must not silently bootstrap healthy.

## Operator Projection

Add bounded attributes to existing indoor/fault diagnostics, preserving technical
identities. Include current monitoring enabled/available, active/retained status,
evaluation quality, clear wait/reason, persistence status and gas inhibition.
Limit each diagnostic payload to 64 KiB and 64 detailed records; publish total and
omitted counts and aggregate danger/inhibition over all records. Detail omission
must never remove a fault contribution. A disabled monitor with retained danger
cannot appear healthy. Runtime strings maintain EN/PL/DE parity; frontend Polish.
