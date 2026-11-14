# Contract: Heating Assertion Lifecycle and Timing

## Trusted startup and authority

SafetyFunctions shall open the heating owner ledger after runtime validation and
before initial fault/system MQTT publication. This occurs independently of the
current C-HVAC enablement, selected profile, rooms or system registry.

Resolve each retained rule's stable fault/severity through trusted `RULES`, validate
IDs and incident UUIDs, and restore active UNEVALUABLE contributors into FaultManager.
Register trusted heating fault identities for retained contributors even if no
current component supplies definitions. Missing/corrupt state with active journal
evidence creates bounded unknown active danger and persistence uncertainty.

Then attach the component to the same coordinator before enabling its mechanisms.
Historical records never replay notifications, timers, consent, proposals or
commands. A newly observed qualified condition may enter the normal notification
lifecycle; that is distinct from replaying an old command or delivery attempt.

## Ledger consistency and failure asymmetry

The `heating_assertions` namespace is versioned, closed and bounded as specified
in the [data model](../data-model.md). Existing SQLite supplies atomic transactions.
Validate counts/bytes before replacement; commit success before acknowledging a
durable transition. Do not delete unknown active records to make a write fit.

Use one bounded storage worker: one in-flight and one coalesced pending ledger
generation, with ordered completion returned to the component callback. No
unbounded write/lock wait occurs on the safety callback. On SET, retain evidence
in memory immediately and await successful commit before normal publication only
within the validated decision/reconciliation allowance. Failure or expiry of that
allowance publishes positive H alongside persistence D; do not claim durability.
Failures must not block other safety paths. Admission/timing tests include the
actual write acknowledgement stage; the 56 s example is valid only when it fits
the specified two reconciliation stages and decision reserve.
On CLEAR, require current comparable positive recovery and durable clear ordering;
a failed necessary commit leaves H active. The old runtime checkpoint cannot
overwrite a newer ledger clear or resurrect stale assertion generations.
Late CLEAR acknowledgement cannot clear a newer SET: verify generation, incident,
cause watermarks and current recovery evidence again before publishing HEAL.

Removed contracts remain retained active UNEVALUABLE, not just a review D. Restore
does not count downtime as observed healthy samples. No operator acknowledgement
or removal flag is a substitute for qualified recovery evidence.

## Deadline semantics

R03/R04 retain their original onset and total debt across target, phase and bounded
inhibition changes. A lower but still-unmet qualified target must reach a bounded
failure decision within the original budget. If the target/source context becomes
non-comparable, explicit coverage/reconciliation loss must be raised by that
deadline without inventing an unobserved mechanical cause. No indefinite
`target_changed`/INHIBITED result is permitted after budget exhaustion.

An already active H cannot HEAL merely because its target or permission changed.
Recovery still needs its validated comparable predicate and observed duration.

## Timing allocation

| Path | Bound and accounting |
| --- | --- |
| SG-003 source supervision | <=60 s including original age, acquisition/scheduling, failure confirmation, both reconciliation stages, decision and notification reserve. |
| SG-010/012 heating loss | <=1800 s from unresolved need with all startup/inhibition/sample windows and reserves accounted without renewing onset. |
| R10/R11 equipment thermal protection | Equipment-specific reviewed allocation and manufacturer limits; neither a generic 30 min nor occupied-room budget is substituted. |
| Recovery | Full comparable source-observed interval; downtime and cached samples contribute no observation coverage. |

With 5 s cadence, the illustrative 10+5+10+1+30=56 s source path fits the first
bound. Admission validates actual values. HA acceptance is the bounded transport
claim; confirmed phone receipt and physical recovery remain separate evidence.

## Acceptance matrix

Use deadline-1, exact deadline and deadline+1 for lowered targets; repeat changes,
restart and source gaps. Cover active/pending/recovery states across rule/profile/
room/system removal and C-HVAC disable. Test missing/corrupt/oversized stores,
failed SET/CLEAR, cause-order conflicts and old checkpoint bootstrap. Assert no
initial false safe publication, lost H, refreshed downtime evidence or actuator
calls. Verify notification/recovery identity and unrelated faults remain intact.
