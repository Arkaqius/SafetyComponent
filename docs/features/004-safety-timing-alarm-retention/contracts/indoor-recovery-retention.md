# Contract: Indoor Recovery and Retention

## Authoritative Clear

A default binary-event profile admits a new current-session alarm-to-clear event
only with reviewed source semantics and unambiguous ordering after the accepted
alarm. Initial/replayed/cached/attribute-only off, manual acknowledgement and
test/hush are not clear proof. Unknown-to-clear after a gap does not manufacture
an alarm-to-clear edge. Other clear contracts require separately reviewed profile
evidence; absent proof retains active unverified danger.

Start the full configured interval (default 30 s) on accepted observation using
monotonic receiver time. Do not subtract `last_changed` age. At expiry verify
session, incident, binding, token, uninterrupted eligible source continuity and
still-clear readback. Reconnect, alarm, unknown/test/hush, lost source continuity
or ambiguous ordering cancel the candidate. A still-off cache alone cannot prove
physical reporting continuity. Positive alarms remain immediate and independent
of persistence failures or slow work.

## Startup and Durable Ordering

1. Load and validate the owner checkpoint independently of component enablement.
2. Reconcile trusted retained fault definitions and active journal evidence before
   inactive-fault filtering and initial MQTT/fault/global registration.
3. Restore original active symptoms as retained/unverified and install all retained
   gas restrictions before notification/local-output recovery can run.
4. Initialize current mechanisms without overwriting the restored assertions.
5. Begin a new receiver session; restore no qualification timer, proposal, consent,
   notification command or actuator operation.

Removal, disabling or rebinding cannot clear the original incident or gas latch.
An orphan remains a real fault contributor, even with no current detector page
entry. Same friendly name or reused key does not establish equipment identity.
Rebinding must not silently transfer a prior incident's recovery authority.

Use the bounded checkpoint and single-writer generations defined in the
[data model](../data-model.md). A fresh positive SET remains in memory on failed
storage. Qualified CLEAR is eligible only after the exact incident/candidate
snapshot has durable acknowledgement and no newer alarm superseded it. Failed
clear persists active danger and blocks HEAL. Independently latched gas inhibition
survives alarm HEAL and requires its existing reviewed authorized-clear policy;
this feature adds no gas-reset control.

Legacy conversion preserves all true alarms and gas restrictions, including
unconfigured records. Legacy clear timestamps do not prove recovery. Corrupt or
missing state with active journal evidence yields unknown active danger and a
separate persistence diagnostic. Invalid identities cannot introduce arbitrary
faults; known journal evidence is reconciled against the trusted catalog. No
overflow policy may discard an active assertion.

Commit a durable dirty-session marker before admitting observations. On unclean
restart reconcile owner/journal incident generations; a durable older CLEAR cannot
exclude a newer SET lost before its write completed. Preserve unknown danger and
relevant output restrictions where completeness cannot be proved, and never
reconstruct a missing cause/identity from invented evidence. A failed marker write
denies recovery and unapproved output eligibility, while positive alarms remain
immediate. Mark clean only after stopping ingress, cancelling clear candidates and
draining all writes/acknowledgements; any failed step leaves the session dirty.
Test CLEAR commit -> newer SET -> crash
before SET acknowledgement, including both storage and journal orderings.

Missing/corrupt prior checkpoint after alarm HEAL still leaves the independent
gas latch unknown and fail-closed; an inactive journal is not release evidence.
Proven first installation is a separate reviewed admission case: absence of a file
alone does not establish empty history. Test this case independently of an active
alarm journal and expose its persistence/restriction uncertainty to the operator.
Present this state as unverified/UNEVALUABLE, not confirmed physical gas. Retaining
inhibition blocks unapproved electrical switching; it sends no off/reset command.
Also test a crash before CLEAR acknowledgement, new SET during a CLEAR write,
failed clean drain and failed dirty-marker commit.

## Operator Interface

Keep existing MQTT topics, fault names, entity IDs, raw states and frontend routes.
Add bounded current/retained/orphan and clear-wait/persistence attributes. Show
retained danger independently of disabled/unavailable current monitoring; do not
replace it with a green zero-detection count. Explain unresolved source proof,
pending recovery and independently retained gas restriction. UI is Polish and
runtime labels have equivalent EN/PL/DE meaning. HEAL never authorizes safe re-entry.

## Acceptance and Traceability

SG-006/007/008 and indoor detector supervision -> SYS-SR-IEHM-001..020 ->
SWR-IEHM-007/013/014/017/018/022/023/025. Preserve the existing ten-second
positive-alarm path; the recovery interval cannot become an assertion debounce.

Regress old off after a fresh alarm, full 29.999/30 s recovery, startup/readback,
attribute-only updates, session interruption at second 29, stale callback,
removed/rebound/disabled detectors, first-publication ordering, independent gas
latch, simultaneous hazard contributors, legacy/corrupt/overflow state and failed
SET/CLEAR. Test owner bootstrap and frontend together with zero real household
commands, no notification replay and no unrelated fault changes.
