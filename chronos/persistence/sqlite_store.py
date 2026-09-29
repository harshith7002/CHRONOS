"""
In-Memory and SQLite Persistence Backends for CHRONOS.
"""

from __future__ import annotations
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from chronos.protocol.events import Event
from chronos.state.snapshot import StateSnapshot
from chronos.persistence.base import EventStore, SnapshotStore


class MemoryEventStore(EventStore):
    """Ultra-low latency in-memory event store with thread safety."""

    def __init__(self):
        self._events: List[Event] = []
        self._lock = threading.RLock()

    def append_event(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)

    def get_events(self, limit: int = 1000, offset: int = 0) -> List[Event]:
        with self._lock:
            return list(self._events[offset : offset + limit])

    def get_events_for_snapshot(self, snapshot_id: str) -> List[Event]:
        with self._lock:
            return [e for e in self._events if getattr(e, "snapshot_id", None) == snapshot_id]


class MemorySnapshotStore(SnapshotStore):
    """In-memory snapshot repository."""

    def __init__(self):
        self._snapshots: Dict[str, StateSnapshot] = {}
        self._lock = threading.RLock()

    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def list_snapshots(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "snapshot_id": s.snapshot_id,
                    "parent_id": s.parent_snapshot_id,
                    "version": s.version,
                    "created_at": s.created_at,
                }
                for s in self._snapshots.values()
            ]


class SQLiteStore(EventStore, SnapshotStore):
    """
    Production-ready SQLite append-only event ledger and immutable snapshot archive.
    Enables instant cold-start replay and audit compliance.
    """

    def __init__(self, db_path: str = "chronos_ledger.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chronos_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    snapshot_id TEXT,
                    payload_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_snap ON chronos_events(snapshot_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chronos_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    parent_snapshot_id TEXT,
                    version INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.commit()

    def append_event(self, event: Event) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chronos_events (event_id, event_type, timestamp, snapshot_id, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    event.timestamp,
                    getattr(event, "snapshot_id", None),
                    json.dumps(event.model_dump()),
                ),
            )
            conn.commit()

    def get_events(self, limit: int = 1000, offset: int = 0) -> List[Event]:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT payload_json FROM chronos_events ORDER BY timestamp ASC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            events = []
            for row in cursor.fetchall():
                data = json.loads(row["payload_json"])
                events.append(Event(**data))
            return events

    def get_events_for_snapshot(self, snapshot_id: str) -> List[Event]:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT payload_json FROM chronos_events WHERE snapshot_id = ? ORDER BY timestamp ASC",
                (snapshot_id,),
            )
            return [Event(**json.loads(row["payload_json"])) for row in cursor.fetchall()]

    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chronos_snapshots (snapshot_id, parent_snapshot_id, version, created_at, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.parent_snapshot_id,
                    snapshot.version,
                    snapshot.created_at,
                    json.dumps(snapshot.model_dump()),
                ),
            )
            conn.commit()

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM chronos_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            row = cursor.fetchone()
            if row:
                return StateSnapshot(**json.loads(row["data_json"]))
            return None

    def list_snapshots(self) -> List[Dict[str, Any]]:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT snapshot_id, parent_snapshot_id, version, created_at FROM chronos_snapshots ORDER BY created_at ASC"
            )
            return [dict(row) for row in cursor.fetchall()]
