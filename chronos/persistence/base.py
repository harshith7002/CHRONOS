"""
CHRONOS Pluggable Persistence Interface
Guarantees strict append-only audit trail and snapshot immutability (INV-7).
"""

from __future__ import annotations
import abc
from typing import Any, Dict, List, Optional
from chronos.protocol.events import Event
from chronos.state.snapshot import StateSnapshot


class EventStore(abc.ABC):
    """
    Append-only log storage interface for CHRONOS events.
    """

    @abc.abstractmethod
    def append_event(self, event: Event) -> None:
        """Appends a new event to the immutable log."""
        pass

    @abc.abstractmethod
    def get_events(self, limit: int = 1000, offset: int = 0) -> List[Event]:
        """Retrieves events in order."""
        pass

    @abc.abstractmethod
    def get_events_for_snapshot(self, snapshot_id: str) -> List[Event]:
        """Retrieves all events tagged with a specific snapshot lineage."""
        pass


class SnapshotStore(abc.ABC):
    """
    Immutable state snapshot storage interface.
    """

    @abc.abstractmethod
    def save_snapshot(self, snapshot: StateSnapshot) -> None:
        """Persists an immutable snapshot."""
        pass

    @abc.abstractmethod
    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Loads a snapshot by ID."""
        pass

    @abc.abstractmethod
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """Lists metadata of all stored snapshots."""
        pass
