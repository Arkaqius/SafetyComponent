# Runtime State Storage Architecture

## 1. Purpose and ownership

SQLite stores durable application state outside the deployed image. Domain
managers retain their existing `load`/`save` persistence boundaries, validation,
retention limits, and independent App Health contributors. Sharing a database
does not merge notification, recovery, detector, or fault lifecycles.

Configuration remains YAML. Home Assistant/MQTT/API payloads remain JSON, and
the transient functional-safety diagnostic snapshot remains under `/run`.
The battery-fault retirement catalogue also uses SQLite; its MQTT identity
validation and retirement rules remain separate from detector/battery health.

## 2. Database location and records

The runtime uses `safety_state.sqlite3` in the parent directory of
`app_config.fault_evidence.state_file`. Packaged defaults therefore place it at
`/config/appdaemon/safety_state.sqlite3`, inside the App-specific persistent
configuration volume. It is neither an image asset nor an editable installation
setting, and it requires no database server.

The database separates these store namespaces:

| Namespace | Domain ownership |
| --- | --- |
| `notification_state` | Active notifications, acknowledgement, queue, counters, and bounded submission history. |
| `recovery_state` | Operator-visible recovery proposals and lifecycle state. |
| `fault_evidence_state` | Bounded unified Freeze frame records and lifecycle metadata. |
| `internal_environment_state` | Detector incident/symptom state and safety restrictions. |
| `periodic_test_state` | Operator attestations for notification receipt and backup restoration. |
| `detector_test_state` | Operator-reported detector test results. |
| `battery_fault_catalog` | Active/retired battery-fault identities for MQTT discovery cleanup. |

Records are stored separately rather than as one complete JSON snapshot per
namespace. Flexible nested record values use JSON columns; managers reconstruct
their existing versioned snapshot shape when loading. Domain format versions
remain independent of the SQLite schema version.

## 3. Transactions and failure handling

Each store save commits its replacement records in one transaction. A reader
sees the preceding committed snapshot or the new committed snapshot, never a
partially replaced namespace. Saves of different namespaces are separate
transactions; a notification save and recovery save are not one cross-domain
commit.

SQLite uses write-ahead logging and `synchronous=FULL`. Writer lock waiting is
bounded to 50 ms. A locked, corrupt, incompatible, or unwritable database raises
a storage error to the owning manager's existing App Health diagnostics; it
does not silently switch to memory or resume writing legacy JSON. This bounds
lock contention, not filesystem I/O latency. Storage failure shall not clear
active safety evidence or prevent the existing independent fault-response paths.
An unreadable battery retirement catalogue prevents identity reconciliation and
asserts its own App Health persistence contributor; it does not abort startup
of the independent hazard monitors.

The database validates its application identity and schema version. A foreign
database or a newer unsupported schema is rejected rather than modified.
Configured disabled persistence still uses the existing explicit in-memory
store; failure of enabled persistence is not equivalent to disabling it.

## 4. One-time legacy import

Existing `state_file`, `periodic_test_state_file`,
`detector_test_state_file`, and `battery_fault_catalog_file` configuration keys
remain accepted as legacy import paths. On the first load of a namespace, the
store reads its legacy JSON if present and imports it with the namespace
initialization marker in one
transaction. Missing legacy files initialize an empty namespace. A parsing or
transaction failure does not mark the namespace initialized, so the corrected
source can be retried.

After successful initialization, SQLite is authoritative for that namespace.
Later changes to a legacy file do not replace database state. Legacy JSON files
are left untouched and are not dual-written or automatically deleted. The
import preserves snapshot content; the domain manager still validates its own
version, fields, bounds, and conservative restoration semantics. A structurally
imported snapshot rejected by domain validation remains invalid database state;
editing its old JSON source does not overwrite the initialized namespace.
Battery catalogue identities are validated before importing that namespace.
Restoration does not replay an actuator command, create a fresh fault activation, or attest
a successful operator test.

## 5. Copy, restore, and rollback boundary

Stop the App before copying or restoring its state directory. Preserve
`user_config.yml`, `safety_state.sqlite3`, and any existing SQLite `-wal`/`-shm`
sidecars together; copying only the live main database can omit committed WAL
data. The App's existing cold-backup mode provides the stopped-process boundary
when Supervisor backup is explicitly used.

Retain legacy JSON through the migration review. It records pre-migration state
only: an older JSON-only release cannot read changes made after SQLite import.
Rolling back code alone therefore does not preserve newer acknowledgements,
history, recovery state, or detector restrictions. Review lifecycle continuity
before selecting an older release, and never run old and new publishers together.

## 6. Related contracts and verification

- [Home Assistant App](<Home Assistant App - Architecture.md>): persistent volume and deployment ownership.
- [Mobile Notification Delivery](<Mobile Notification Delivery - Architecture.md>): acknowledgement, attempts, and conservative restore.
- [Recommended Actions and Recovery](<Recommended Actions and Recovery - Architecture.md>): proposal restore without actuator replay.
- [Fault State Policy](<Fault State Policy - Architecture.md>): Freeze frame bounds and activation semantics.
- [Internal Environmental Hazard Monitoring](<Internal Environmental Hazard Monitoring - Architecture.md>): latches, clear ordering, and gas restrictions.
- [System Configuration](<../reference/System Configuration.md>): retained system-owned import paths and limits.

Storage tests shall cover namespace isolation, atomic save/rollback, reopen,
one-time import, failed-import retry, malformed/corrupt data, bounded writer
contention, and incompatible database identity/version. Runtime tests shall
verify persistence failures remain separate App Health contributors and that
restoration preserves the existing negative-actuation and no-false-clear rules.
