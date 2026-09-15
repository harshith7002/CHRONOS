"""
CHRONOS Immutable Event Log
Thread-safe, append-only event store for event sourcing.
"""

from __future__ import annotations
import threading
from typing import Any, Callable, Dict, List, Optional
from chronos.protocol.events import Event, EventType


class EventLog:
    """
    Append-only immutable event log.
    """

    def __init__(self):
        self._events: List[Event] = []
        self._lock = threading.RLock()
        self._listeners: List[Callable[[Event], None]] = []

    def append(self, event: Event) -> Event:
        """Append an event to the log and notify all subscribers."""
        with self._lock:
            self._events.append(event)
            self._notify(event)
            return event

    def subscribe(self, listener: Callable[[Event], None]) -> None:
        """Subscribe to real-time events."""
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[Event], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify(self, event: Event) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    def get_all(self) -> List[Event]:
        with self._lock:
            return list(self._events)

    def filter_by(
        self,
        event_type: Optional[EventType] = None,
        snapshot_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        min_timestamp: Optional[float] = None,
        max_timestamp: Optional[float] = None,
    ) -> List[Event]:
        with self._lock:
            res = self._events
            if event_type is not None:
                res = [e for e in res if e.event_type == event_type]
            if snapshot_id is not None:
                res = [e for e in res if e.snapshot_id == snapshot_id]
            if branch_id is not None:
                res = [e for e in res if e.branch_id == branch_id]
            if min_timestamp is not None:
                res = [e for e in res if e.timestamp >= min_timestamp]
            if max_timestamp is not None:
                res = [e for e in res if e.timestamp <= max_timestamp]
            return list(res)

    def count(self) -> int:
        with self._lock:
            return len(self._events)

    def clear(self) -> None:
        """Used for test reset."""
        with self._lock:
            self._events.clear()
