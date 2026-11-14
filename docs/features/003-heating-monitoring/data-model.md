# Data Model: Read-Only Heating Monitoring

Existing source model 2 and heating IDs remain authoritative. This design extends
evidence/admission and introduces an owner ledger; it does not add device control.

## Entities and validation

| Entity | Fields and relationships | Validation |
| --- | --- | --- |
| Installation/room | Existing stable keys, friendly labels, circuit association, selected profile, input bindings | Existing system/room limits and case-insensitive collision checks remain; a removed key does not remove retained danger. |
| SourceEvidence | Semantic role, entity/attribute selector, unit/conversion, original-time selector, source cadence/age, evidence kind, producer reference, independence group | Finite values, supported units, bounded age/skew; no future/regressing/replayed observation becomes new evidence. References and group names require qualification evidence. |
| CommissioningRecord | Installation/room/role and rule references; equipment/profile identity; producer semantics; measured timing; independence/topology rationale; reviewed limits and recovery evidence; qualification outcome | Sanitized record with no credentials/private bindings in public fixtures. Incomplete/mismatched evidence prevents admission; operator cannot elevate contact to measurement proof. |
| RuleAdmission | Rule ID, required roles/phases, policy fingerprint, evidence references, excluded reason and qualified timing allocation | Policy and all required facts must agree. Selection alone is not admission. Full-chain credit excludes unsupported/shadow paths. |
| NeedEpisode | Original onset/target, current qualified target, elapsed debt, remaining budget, circuit/room, inhibited/unevaluable reason | Monotonic runtime; reconcile UTC downtime once as debt, never as observed recovery. Target changes cannot renew onset. |
| HeatingAssertion | Stable symptom/fault/installation/room, rule, incident UUID, onset, active flag, evidence/cause context, policy/binding fingerprints, recovery reference/watermarks, current/retained/unverified status | Closed typed records, bounded strings/collections, finite values and trusted rule-to-fault mapping. No payload-supplied severity. |
| AssertionLedger | Schema version 1, owner, saved UTC, record map, uncertainty marker and bounded journal reconciliation context | <=4096 records and <=1 MiB serialized UTF-8; key/record identity coherence; atomic replacement, no active-record eviction. |
| CoverageAssessment | Required need/request/response/thermal/delivery/quality paths, admitted/excluded rules, per-path current evidence, retained danger count | Separate from operating phase and active fault severity. Full requires every required path proven; retained uncertainty prevents a misleading overall safe result. |
| OperatorEvidence | Rule result/reason, observed/target values/units, source age, elapsed/remaining budget, inhibition, recovery wait, retained provenance | Projection only; bounded details, nullable unknowns, applied generation and disconnect invalidation. |

Commissioning evidence is a reviewable admission input, not a new authority over
physical truth. Runtime freshness and qualified evidence remain required after
commissioning. Signed/certified equipment assertions are not invented by this model.

## State transitions

| Trigger | Required result |
| --- | --- |
| Admitted fresh breach | Pending failure -> active H after its qualified duration, within total budget. |
| Lowered still-unmet target | Preserve episode/debt and evaluate the qualified remaining need. |
| Changed non-comparable evidence | Unevaluable/reconciliation loss with bounded escalation; no indefinite inhibition and no fabricated H or HEAL. |
| Unknown/stale input or storage failure | Preserve active H; expose independent D/coverage loss. |
| Rule/system removed | Current active assertion -> retained active UNEVALUABLE with original identity. |
| Restart | Load/reconcile ledger before initial publication; restore neither timers nor commands. |
| Qualified comparable recovery | Pending recovery -> durable clear commit -> HEAL with original incident identity. |
| Failed clear commit | Remain active, expose persistence D; no HEAL. |
| Corrupt/missing ledger with active journal | Retain unknown active heating danger; journal is a conservative hint, not proof of recovery. |

## Storage ownership

Existing runtime checkpoints retain algorithm/deadline state and bounded sampled
window bookkeeping. The owner ledger is the authoritative active/retained H set,
read even when no heating component is instantiated. Reconciliation is idempotent:
an assertion acknowledged as cleared cannot be resurrected by an older runtime
snapshot; a newer positive assertion cannot be dropped by that snapshot.

Use persisted cause/clear ordering and ledger generation to resolve the two stores.
Bootstrap valid old active runtime records once, under a transaction/marker; do
not overwrite a nonempty authoritative ledger with an incomplete bootstrap. A
failed bootstrap retains uncertainty and active hints rather than publishing safe.

Code targets: `heating/assertion_store.py` (new typed ledger/coordinator),
`heating/state.py` (existing compatibility), SafetyFunctions startup and the
FaultManager integration described in the [lifecycle contract](contracts/lifecycle-and-timing.md).
