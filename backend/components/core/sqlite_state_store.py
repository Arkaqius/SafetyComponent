"""Transactional record storage and one-time import of legacy state files."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, RLock, get_ident, local
from time import monotonic
from typing import Any, Callable, Iterable, Iterator, Mapping
from weakref import WeakValueDictionary

_SCHEMA_VERSION = 1
_APPLICATION_ID = 0x53414645
_BUSY_TIMEOUT_SECONDS = 0.05
BACKGROUND_WRITE_SECONDS = 0.5
# Primary SQLite result codes are stable, including on Python 3.10, which
# does not expose the sqlite3 result-code constants or exception attributes.
_SQLITE_STORAGE_CODES = {
    5: "SQLITE_BUSY",
    6: "SQLITE_LOCKED",
    8: "SQLITE_READONLY",
    10: "SQLITE_IOERR",
    11: "SQLITE_CORRUPT",
    13: "SQLITE_FULL",
    14: "SQLITE_CANTOPEN",
    26: "SQLITE_NOTADB",
}
_SQLITE_LEGACY_MESSAGES = {
    "database is locked": "SQLITE_BUSY",
    "database table is locked": "SQLITE_LOCKED",
    "attempt to write a readonly database": "SQLITE_READONLY",
    "disk I/O error": "SQLITE_IOERR",
    "database disk image is malformed": "SQLITE_CORRUPT",
    "database or disk is full": "SQLITE_FULL",
    "unable to open database file": "SQLITE_CANTOPEN",
    "file is not a database": "SQLITE_NOTADB",
}


class SqliteStateError(OSError):
    """Expose a SQLite result family while retaining the storage error contract."""

    def __init__(self, operation: str, error: sqlite3.Error) -> None:
        code = getattr(error, "sqlite_errorcode", None)
        if code is not None:
            self.sqlite_errorname: str = _SQLITE_STORAGE_CODES.get(
                code & 0xFF, getattr(error, "sqlite_errorname", "SQLITE_ERROR")
            )
        elif type(error) in (sqlite3.OperationalError, sqlite3.DatabaseError):
            self.sqlite_errorname = _SQLITE_LEGACY_MESSAGES.get(str(error), "SQLITE_ERROR")
        else:
            self.sqlite_errorname = "SQLITE_ERROR"
        super().__init__(f"SQLite state storage {operation} failed ({self.sqlite_errorname}): {error}")


class SupersededStorageWrite(Exception):
    """An unsent worker attempt lost its infrastructure owner or revision."""


@dataclass
class _WriteBudget:
    seconds: float
    background: bool = False
    current: Callable[[], bool] | None = None

    def remaining(self) -> float:
        if self.current is not None and not self.current():
            raise SupersededStorageWrite()
        if self.seconds <= 0:
            raise SqliteStateError("admission", sqlite3.OperationalError("database is locked"))
        return self.seconds

    def consume(self, seconds: float) -> None:
        self.seconds -= max(0, seconds)


def _budget_local() -> Any:
    return builtins.__dict__.setdefault("_safety_sqlite_budget_v1", local())


@contextmanager
def storage_write_budget(
    current: Callable[[], bool] | None = None,
) -> Iterator[_WriteBudget]:
    """Share one contention budget across coordination and SQLite lock waits.

    Only the existing background worker supplies a current-generation check.
    Foreground callers retain their original 50 ms contention budget.
    """
    state = _budget_local()
    previous = getattr(state, "budget", None)
    budget = previous or _WriteBudget(
        BACKGROUND_WRITE_SECONDS if current is not None else _BUSY_TIMEOUT_SECONDS,
        background=current is not None, current=current,
    )
    state.budget = budget
    try:
        yield budget
    finally:
        state.budget = previous


class _WriteCoordinator:
    """Serialize mutations with foreground priority and finite admission waits."""

    def __init__(self) -> None:
        self.condition = Condition(RLock())
        self.owner: int | None = None
        self.depth = 0
        self.foreground_waiters = 0

    @contextmanager
    def mutation(self, budget: _WriteBudget) -> Iterator[None]:
        identity = get_ident()
        with self.condition:
            foreground = not budget.background
            if foreground:
                self.foreground_waiters += 1
                self.condition.notify_all()
            try:
                while self.owner not in (None, identity) or (
                    self.owner is None and budget.background and self.foreground_waiters
                ):
                    started = monotonic()
                    self.condition.wait(timeout=min(0.01, budget.remaining()))
                    budget.consume(monotonic() - started)
                budget.remaining()
                self.owner = identity
                self.depth += 1
            finally:
                if foreground:
                    self.foreground_waiters -= 1
                self.condition.notify_all()
        try:
            yield
        finally:
            with self.condition:
                self.depth -= 1
                if not self.depth:
                    self.owner = None
                self.condition.notify_all()


def _database_coordinator(path: Path) -> _WriteCoordinator:
    lock = builtins.__dict__.setdefault("_safety_sqlite_registry_lock_v1", RLock())
    with lock:
        coordinators = builtins.__dict__.setdefault(
            "_safety_sqlite_coordinators_v1", WeakValueDictionary()
        )
        key = os.path.normcase(str(path.resolve()))
        coordinator = coordinators.get(key)
        if coordinator is None:
            coordinator = _WriteCoordinator()
            coordinators[key] = coordinator
        return coordinator


@dataclass(frozen=True)
class _EncodedSection:
    kind: str
    scalar: str | None
    records: dict[str, tuple[int, str]]


def state_database_path(legacy_path: str | Path) -> Path:
    """Keep the database outside the app image, beside existing state files."""
    return Path(legacy_path).parent / "safety_state.sqlite3"


class SqliteStateDatabase:
    """Share one database while retaining independent component transactions."""

    def __init__(self, path: str | Path) -> None:
        self.path: Path = Path(path)
        self._coordinator = _database_coordinator(self.path)

    @contextmanager
    def _mutation_access(self, connection: sqlite3.Connection) -> Iterator[None]:
        """Coordinate both ordinary transactions and initial WAL conversion."""
        with storage_write_budget() as budget, self._coordinator.mutation(budget):
            timeout_ms = max(0, int(min(_BUSY_TIMEOUT_SECONDS, budget.remaining()) * 1000))
            connection.execute(f"PRAGMA busy_timeout = {timeout_ms}")
            yield

    @contextmanager
    def write_transaction(self, connection: sqlite3.Connection) -> Iterator[None]:
        """Keep all namespace mutations in one bounded process admission policy.

        @relation(SWR-NOT-017, scope=function, role=Implementation)
        """
        with self._mutation_access(connection):
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                yield

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a callback-local connection with bounded lock contention."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            budget = getattr(_budget_local(), "budget", None)
            timeout = min(_BUSY_TIMEOUT_SECONDS, budget.remaining()) if budget else _BUSY_TIMEOUT_SECONDS
            connection = sqlite3.connect(self.path, timeout=timeout)
        except sqlite3.Error as exc:
            raise SqliteStateError("open", exc) from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            # Read both header values from the same committed snapshot. Release
            # the reader before a possible schema initialization.
            with connection:
                connection.execute("BEGIN")
                application_id = connection.execute("PRAGMA application_id").fetchone()[0]
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id not in (0, _APPLICATION_ID) or version not in (
                0,
                _SCHEMA_VERSION,
            ):
                raise ValueError("Unsupported SafetyComponent state database")
            if version == 0:
                self._initialize(connection)
            elif application_id != _APPLICATION_ID:
                raise ValueError("Missing SafetyComponent database identity")
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if mode != "wal":
                with self._mutation_access(connection):
                    mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode != "wal":
                raise ValueError("SafetyComponent state requires WAL journaling")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        except sqlite3.Error as exc:
            raise SqliteStateError("transaction", exc) from exc
        finally:
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        """Create the schema atomically; reject an unrelated existing database."""
        with self.write_transaction(connection):
            # Another callback may have initialized it while this one waited.
            if (
                connection.execute("PRAGMA user_version").fetchone()[0]
                == _SCHEMA_VERSION
            ):
                if (
                    connection.execute("PRAGMA application_id").fetchone()[0]
                    != _APPLICATION_ID
                ):
                    raise ValueError("Foreign state database")
                return
            if connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchone():
                raise ValueError("Refusing to adopt an existing unrelated database")
            connection.execute(
                "CREATE TABLE stores (name TEXT PRIMARY KEY, legacy_path TEXT, "
                "legacy_sha256 TEXT)"
            )
            connection.execute(
                "CREATE TABLE sections (store TEXT NOT NULL REFERENCES stores(name), "
                "name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('scalar','list','dict')), "
                "value TEXT, PRIMARY KEY(store,name))"
            )
            connection.execute(
                "CREATE TABLE records (store TEXT NOT NULL, section TEXT NOT NULL, "
                "record_key TEXT NOT NULL, position INTEGER NOT NULL, value TEXT NOT NULL, "
                "PRIMARY KEY(store,section,record_key), FOREIGN KEY(store,section) "
                "REFERENCES sections(store,name) ON DELETE CASCADE)"
            )
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    def store(
        self,
        name: str,
        legacy_path: str | Path,
        *,
        max_bytes: int | None = None,
        legacy_validator: Callable[[dict[str, Any]], Any] | None = None,
    ) -> SqliteStateStore:
        """Bind a component to its own rows and legacy import source."""
        return SqliteStateStore(
            self,
            name,
            legacy_path,
            max_bytes=max_bytes,
            legacy_validator=legacy_validator,
        )

    def record_store(self, name: str, *, max_bytes: int) -> SqliteStateStore:
        """Bind a new bounded namespace without any legacy file import path."""
        return SqliteStateStore(self, name, None, max_bytes=max_bytes)


class SqliteStateStore:
    """Adapt existing snapshots to individually addressable collection records."""

    def __init__(
        self,
        database: SqliteStateDatabase,
        name: str,
        legacy_path: str | Path | None,
        *,
        max_bytes: int | None = None,
        legacy_validator: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.database: SqliteStateDatabase = database
        self.name: str = name
        self.legacy_path: Path | None = Path(legacy_path) if legacy_path is not None else None
        self.max_bytes: int | None = max_bytes
        self.legacy_validator: Callable[[dict[str, Any]], Any] | None = legacy_validator

    def load(self) -> dict[str, Any]:
        """Import once, then read one coherent committed component snapshot."""
        with self.database.connect() as connection:
            self._ensure_imported(connection)
            with connection:
                connection.execute("BEGIN")
                return self._read(connection)

    def save(self, snapshot: Mapping[str, Any]) -> None:
        """Commit changed records together; never acknowledge an uncommitted write.

        @relation(SWR-REC-006, scope=function, role=Implementation)
        """
        payload = json.loads(
            json.dumps(dict(snapshot), ensure_ascii=False, default=str)
        )
        self._check_size(payload)
        sections = self._encode_sections(payload)
        with self.database.connect() as connection:
            self._ensure_imported(connection)
            with self.database.write_transaction(connection):
                # Compare only at the serialized SQLite write turn: another
                # instance or an in-flight B may have replaced previously saved A.
                if self._stored_sections(connection) != sections:
                    self._write(connection, sections)

    def _check_size(self, payload: Mapping[str, Any]) -> None:
        if (
            self.max_bytes is not None
            and len(
                json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                )
            )
            > self.max_bytes
        ):
            raise ValueError("State exceeds configured storage bound")

    def _ensure_imported(self, connection: sqlite3.Connection) -> None:
        if connection.execute(
            "SELECT 1 FROM stores WHERE name=?", (self.name,)
        ).fetchone():
            return
        payload: dict[str, Any] = {}
        digest = None
        if self.legacy_path is not None and self.legacy_path.exists():
            if (
                self.max_bytes is not None
                and self.legacy_path.stat().st_size > self.max_bytes
            ):
                raise ValueError("Legacy state exceeds configured storage bound")
            raw = self.legacy_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Legacy state root must be an object")
            self._check_size(payload)
            if self.legacy_validator is not None:
                self.legacy_validator(payload)
            digest = hashlib.sha256(raw).hexdigest()
        sections = self._encode_sections(payload)
        with self.database.write_transaction(connection):
            if connection.execute(
                "SELECT 1 FROM stores WHERE name=?", (self.name,)
            ).fetchone():
                return
            connection.execute(
                "INSERT INTO stores VALUES (?,?,?)",
                (self.name, str(self.legacy_path) if self.legacy_path is not None else None, digest),
            )
            self._write(connection, sections)

    def _stored_sections(self, connection: sqlite3.Connection) -> dict[str, _EncodedSection]:
        """Read exact encoded content while the caller owns the write transaction."""
        records: dict[str, dict[str, tuple[int, str]]] = {}
        for section, key, position, value in connection.execute(
            "SELECT section,record_key,position,value FROM records WHERE store=?", (self.name,)
        ):
            records.setdefault(section, {})[key] = (position, value)
        return {
            section: _EncodedSection(kind, value, records.get(section, {}))
            for section, kind, value in connection.execute(
                "SELECT name,kind,value FROM sections WHERE store=?", (self.name,)
            )
        }

    def _read(self, connection: sqlite3.Connection) -> dict[str, Any]:
        if self.max_bytes is not None:
            section_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(name AS BLOB)) + "
                "COALESCE(length(CAST(value AS BLOB)),0)),0) "
                "FROM sections WHERE store=?",
                (self.name,),
            ).fetchone()[0]
            record_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(r.value AS BLOB)) + "
                "CASE WHEN s.kind='dict' THEN length(CAST(r.record_key AS BLOB)) "
                "ELSE 0 END),0) FROM records r JOIN sections s "
                "ON r.store=s.store AND r.section=s.name WHERE r.store=?",
                (self.name,),
            ).fetchone()[0]
            # Reject oversized corrupt evidence before constructing Python records.
            if section_bytes + record_bytes > self.max_bytes:
                raise ValueError("State exceeds configured storage bound")
        snapshot: dict[str, Any] = {}
        for section, kind, value in connection.execute(
            "SELECT name,kind,value FROM sections WHERE store=? ORDER BY name",
            (self.name,),
        ):
            if kind == "scalar":
                snapshot[section] = json.loads(value)
                continue
            rows = connection.execute(
                "SELECT record_key,value FROM records WHERE store=? AND section=? "
                "ORDER BY position",
                (self.name, section),
            ).fetchall()
            snapshot[section] = (
                [json.loads(item) for _, item in rows]
                if kind == "list"
                else {key: json.loads(item) for key, item in rows}
            )
        self._check_size(snapshot)
        return snapshot

    @staticmethod
    def _encode_sections(snapshot: Mapping[str, Any]) -> dict[str, _EncodedSection]:
        """Encode the detached snapshot before taking SQLite's shared writer lock."""
        sections = {}
        for section, value in snapshot.items():
            items: Iterable[tuple[Any, Any]]
            scalar = None
            if isinstance(value, dict):
                kind = "dict"
                items = value.items()
            elif isinstance(value, list):
                kind = "list"
                items = enumerate(value)
            else:
                kind = "scalar"
                items = []
                scalar = json.dumps(value, ensure_ascii=False, sort_keys=True)
            records = {
                str(key): (position, json.dumps(item, ensure_ascii=False, sort_keys=True))
                for position, (key, item) in enumerate(items)
            }
            sections[section] = _EncodedSection(kind, scalar, records)
        return sections

    def _write(
        self, connection: sqlite3.Connection, sections: dict[str, _EncodedSection]
    ) -> None:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sections WHERE store=?", (self.name,)
            )
        }
        for section, encoded in sections.items():
            connection.execute(
                "INSERT INTO sections VALUES (?,?,?,?) ON CONFLICT(store,name) DO UPDATE "
                "SET kind=excluded.kind,value=excluded.value "
                "WHERE kind!=excluded.kind OR value IS NOT excluded.value",
                (self.name, section, encoded.kind, encoded.scalar),
            )
            connection.executemany(
                "INSERT INTO records VALUES (?,?,?,?,?) "
                "ON CONFLICT(store,section,record_key) DO UPDATE "
                "SET position=excluded.position,value=excluded.value "
                "WHERE position!=excluded.position OR value!=excluded.value",
                (
                    (self.name, section, key, position, value)
                    for key, (position, value) in encoded.records.items()
                ),
            )
            old_keys = {
                row[0]
                for row in connection.execute(
                    "SELECT record_key FROM records WHERE store=? AND section=?",
                    (self.name, section),
                )
            }
            connection.executemany(
                "DELETE FROM records WHERE store=? AND section=? AND record_key=?",
                [(self.name, section, key) for key in old_keys - encoded.records.keys()],
            )
        connection.executemany(
            "DELETE FROM sections WHERE store=? AND name=?",
            [(self.name, section) for section in existing - sections.keys()],
        )
