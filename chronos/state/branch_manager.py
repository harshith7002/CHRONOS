"""
CHRONOS Branch & Snapshot Manager
Manages intent version lineage, snapshot history, active branches, and garbage collection.
"""

from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional, Set
from chronos.protocol.schemas import BranchStatus
from chronos.protocol.events import EventType, Event
from chronos.state.snapshot import StateSnapshot, SnapshotValidity
from chronos.state.event_log import EventLog


class Branch:
    def __init__(self, branch_id: str, parent_branch_id: Optional[str] = None, root_snapshot_id: str = "v1"):
        self.branch_id = branch_id
        self.parent_branch_id = parent_branch_id
        self.root_snapshot_id = root_snapshot_id
        self.status = BranchStatus.ACTIVE
        self.snapshot_ids: List[str] = [root_snapshot_id]
        self.created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "parent_branch_id": self.parent_branch_id,
            "root_snapshot_id": self.root_snapshot_id,
            "status": self.status.value,
            "snapshot_ids": list(self.snapshot_ids),
        }


class TemporalStateManager:
    """
    Core state manager managing versioned snapshots and branch lineage.
    """

    def __init__(self, event_log: EventLog):
        self._event_log = event_log
        self._lock = threading.RLock()
        
        # All snapshots indexed by snapshot_id
        self._snapshots: Dict[str, StateSnapshot] = {}
        
        # Branches indexed by branch_id
        self._branches: Dict[str, Branch] = {}
        
        # Current active branch and snapshot pointers
        self._active_branch_id: str = "main"
        self._current_snapshot_id: str = "v0"
        self._version_counter: int = 0
        
        # Initialize root snapshot v0
        self._init_root_snapshot()

    @property
    def snapshots(self) -> Dict[str, StateSnapshot]:
        with self._lock:
            return dict(self._snapshots)

    def _init_root_snapshot(self) -> None:
        root = StateSnapshot(
            snapshot_id="v0",
            version_number=0,
            parent_snapshot_id=None,
            timestamp=0.0,
            branch_id="main",
            validity_status=SnapshotValidity.VALID,
            intent_slots={},
            active_tool_calls={},
            completed_tool_results={},
            cancelled_tool_calls=set(),
            goal=None,
        )
        self._snapshots["v0"] = root
        main_branch = Branch("main", None, "v0")
        self._branches["main"] = main_branch
        self._current_snapshot_id = "v0"

    @property
    def current_snapshot_id(self) -> str:
        with self._lock:
            return self._current_snapshot_id

    @property
    def active_branch_id(self) -> str:
        with self._lock:
            return self._active_branch_id

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def get_current_snapshot(self) -> StateSnapshot:
        with self._lock:
            return self._snapshots[self._current_snapshot_id]

    def get_branch(self, branch_id: str) -> Optional[Branch]:
        with self._lock:
            return self._branches.get(branch_id)

    def get_all_snapshots(self) -> List[StateSnapshot]:
        with self._lock:
            return list(self._snapshots.values())

    def get_all_branches(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [b.to_dict() for b in self._branches.values()]

    def create_new_snapshot(
        self,
        timestamp: float,
        slot_updates: Optional[Dict[str, Any]] = None,
        new_active_calls: Optional[Dict[str, str]] = None,
        new_completed_results: Optional[Dict[str, Any]] = None,
        new_cancelled_calls: Optional[Set[str]] = None,
        branch_id: Optional[str] = None,
        goal: Optional[str] = None,
    ) -> StateSnapshot:
        """
        Creates a new immutable snapshot v(N+1).
        Marks the previous snapshot in this branch as SUPERSEDED.
        """
        with self._lock:
            self._version_counter += 1
            new_id = f"v{self._version_counter}"
            target_branch_id = branch_id or self._active_branch_id
            
            parent_snap = self.get_current_snapshot()
            
            # Evolve new snapshot
            new_snap = parent_snap.evolve(
                new_snapshot_id=new_id,
                new_version_number=self._version_counter,
                timestamp=timestamp,
                slot_updates=slot_updates,
                new_active_calls=new_active_calls,
                new_completed_results=new_completed_results,
                new_cancelled_calls=new_cancelled_calls,
                branch_id=target_branch_id,
                validity_status=SnapshotValidity.VALID,
                goal=goal,
            )
            
            self._snapshots[new_id] = new_snap
            self._current_snapshot_id = new_id

            if target_branch_id not in self._branches:
                self._branches[target_branch_id] = Branch(target_branch_id, parent_snap.branch_id, new_id)
            else:
                self._branches[target_branch_id].snapshot_ids.append(new_id)

            # Record SNAPSHOT_CREATED event
            self._event_log.append(
                Event(
                    event_type=EventType.SNAPSHOT_CREATED,
                    timestamp=timestamp,
                    snapshot_id=new_id,
                    branch_id=target_branch_id,
                    payload={
                        "version": self._version_counter,
                        "parent": parent_snap.snapshot_id,
                        "slots": new_snap.intent_slots,
                        "active_calls": new_snap.active_tool_calls,
                        "goal": new_snap.goal,
                    },
                )
            )

            return new_snap

    def branch(self, new_branch_id: str, timestamp: float, goal_override: Optional[str] = None) -> StateSnapshot:
        """
        Create a new branch from current snapshot, transitioning previous branch to SUPERSEDED.
        """
        with self._lock:
            old_branch_id = self._active_branch_id
            if old_branch_id in self._branches:
                self._branches[old_branch_id].status = BranchStatus.SUPERSEDED
                self._event_log.append(
                    Event(
                        event_type=EventType.BRANCH_STATUS_CHANGED,
                        timestamp=timestamp,
                        snapshot_id=self._current_snapshot_id,
                        branch_id=old_branch_id,
                        payload={"status": BranchStatus.SUPERSEDED.value},
                    )
                )

            self._active_branch_id = new_branch_id
            return self.create_new_snapshot(
                timestamp=timestamp,
                branch_id=new_branch_id,
                goal=goal_override,
            )

    def garbage_collect_branches(self, max_retained_superseded: int = 5) -> List[str]:
        """
        Safely discard superseded branches older than threshold.
        """
        with self._lock:
            discarded = []
            superseded = [b for b in self._branches.values() if b.status == BranchStatus.SUPERSEDED]
            if len(superseded) > max_retained_superseded:
                to_discard = superseded[:-max_retained_superseded]
                for b in to_discard:
                    b.status = BranchStatus.DISCARDED
                    discarded.append(b.branch_id)
            return discarded

    def reset(self) -> None:
        with self._lock:
            self._snapshots.clear()
            self._branches.clear()
            self._version_counter = 0
            self._active_branch_id = "main"
            self._init_root_snapshot()
