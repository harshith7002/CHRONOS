"""
CHRONOS Temporal State Snapshot
Immutable snapshots representing system state at distinct intent version points.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class SnapshotValidity(str, Enum):
    VALID = "VALID"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


class StateSnapshot(BaseModel):
    """
    Immutable snapshot of the agent state at a specific version point.
    """
    snapshot_id: str = Field(..., description="e.g. 'v1', 'v2', 'v3'")
    version_number: int = Field(..., description="Monotonically increasing integer version")
    parent_snapshot_id: Optional[str] = None
    timestamp: float = Field(..., description="Virtual time created")
    branch_id: str = Field(default="main", description="Branch identifier")
    validity_status: SnapshotValidity = Field(default=SnapshotValidity.VALID)
    
    # Intent slots: {slot_name: value}
    intent_slots: Dict[str, Any] = Field(default_factory=dict)
    
    # Active tool calls at this snapshot: {call_id: tool_name}
    active_tool_calls: Dict[str, str] = Field(default_factory=dict)
    
    # Completed tool call outputs mapped by call_id or tool_name
    completed_tool_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Cancelled tool calls
    cancelled_tool_calls: Set[str] = Field(default_factory=set)

    # Goal description
    goal: Optional[str] = None

    @property
    def slots(self) -> Dict[str, Any]:
        return self.intent_slots

    @property
    def intent_name(self) -> str:
        return self.goal or "travel_booking"

    model_config = {
        "frozen": True  # Never mutate historical snapshots
    }

    def evolve(
        self,
        new_snapshot_id: str,
        new_version_number: int,
        timestamp: float,
        slot_updates: Optional[Dict[str, Any]] = None,
        new_active_calls: Optional[Dict[str, str]] = None,
        new_completed_results: Optional[Dict[str, Any]] = None,
        new_cancelled_calls: Optional[Set[str]] = None,
        branch_id: Optional[str] = None,
        validity_status: Optional[SnapshotValidity] = None,
        goal: Optional[str] = None,
    ) -> StateSnapshot:
        """Derive a new immutable snapshot from this parent."""
        updated_slots = dict(self.intent_slots)
        if slot_updates is not None:
            for k, v in slot_updates.items():
                if v is None and k in updated_slots:
                    del updated_slots[k]
                else:
                    updated_slots[k] = v

        updated_active = dict(self.active_tool_calls) if new_active_calls is None else dict(new_active_calls)
        updated_results = dict(self.completed_tool_results) if new_completed_results is None else dict(new_completed_results)
        updated_cancelled = set(self.cancelled_tool_calls) if new_cancelled_calls is None else set(new_cancelled_calls)

        return StateSnapshot(
            snapshot_id=new_snapshot_id,
            version_number=new_version_number,
            parent_snapshot_id=self.snapshot_id,
            timestamp=timestamp,
            branch_id=branch_id or self.branch_id,
            validity_status=validity_status or SnapshotValidity.VALID,
            intent_slots=updated_slots,
            active_tool_calls=updated_active,
            completed_tool_results=updated_results,
            cancelled_tool_calls=updated_cancelled,
            goal=goal if goal is not None else self.goal,
        )
