"""
SQLite connection and schema management for the patient records store.

Deliberately plain sqlite3 — no ORM. The schema is small, the queries are the
interesting part, and a clinic PC should not need a dependency tree to open its
own patient file.

THREADING
The FastAPI server touches this from request handlers that may run on different
worker threads, so every connection is opened with check_same_thread=False and
guarded by a lock. SQLite serialises writes anyway; the lock just keeps the
Python-side cursor bookkeeping honest.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "1"

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_PATH = os.path.join(_HERE, "schema.sql")

# Default location: upper_body_ai/data/therayu.db
DEFAULT_DB_PATH = os.path.join(os.path.dirname(_HERE), "data", "therayu.db")


def utc_now() -> str:
    """ISO-8601 UTC timestamp. Stored as text; SQLite has no datetime type."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """One SQLite file, opened once and shared."""

    def __init__(self, path: Optional[str] = None):
        self.path = os.path.abspath(path or DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # WAL lets a report read while a session is still writing, which matters
        # because the doctor may pull a PDF mid-clinic.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA synchronous = NORMAL")

        self._apply_schema()

    # -- schema ---------------------------------------------------------------

    def _apply_schema(self) -> None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            ddl = fh.read()
        with self._lock:
            self._conn.executescript(ddl)
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.commit()

    # -- primitives -----------------------------------------------------------

    def query(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Runs a statement and returns lastrowid."""
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def execute_many(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- convenience ----------------------------------------------------------

    def table_counts(self) -> Dict[str, int]:
        """Row count per table. Used by the health endpoint and the tests."""
        names = [
            r["name"]
            for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {n: self.query_one(f"SELECT COUNT(*) AS c FROM {n}")["c"] for n in names}


# Module-level singleton, so the server and the CLI tools share one handle.
_INSTANCE: Optional[Database] = None
_INSTANCE_LOCK = threading.Lock()


def get_db(path: Optional[str] = None) -> Database:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = Database(path)
        return _INSTANCE


def reset_db_singleton() -> None:
    """Test hook. Drops the shared handle so a fresh path can be opened."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is not None:
            _INSTANCE.close()
        _INSTANCE = None
