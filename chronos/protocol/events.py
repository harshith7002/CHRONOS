"""
CHRONOS Protocol Events
Immutable event definitions and serialization for event-sourced control plane.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class EventType(str, Enum):
    USER_INPUT = "USER_INPUT"
    INTENT_UPDATE = "INTENT_UPDATE"
    INTERRUPTION = "INTERRUPTION"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    TOOL_DISPATCHED = "TOOL_DISPATCHED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_CANCELLED = "TOOL_CANCELLED"
    TOOL_FAILED = "TOOL_FAILED"
    STALE_RESULT_REJECTED = "STALE_RESULT_REJECTED"
    CONFIRMATION_REQUESTED = "CONFIRMATION_REQUESTED"
    CONFIRMATION_RECEIVED = "CONFIRMATION_RECEIVED"
    COMMIT = "COMMIT"
    FINAL_RESPONSE = "FINAL_RESPONSE"
    BRANCH_STATUS_CHANGED = "BRANCH_STATUS_CHANGED"
    FAST_ACK = "FAST_ACK"
    SPECULATIVE_PREPARED = "SPECULATIVE_PREPARED"


class InterruptionLevel(int, Enum):
    LEVEL_0 = 0  # Backchannel / acknowledgment ("yeah", "okay") -> No state change
    LEVEL_1 = 1  # Local slot correction ("Tomorrow - actually Friday") -> Selective invalidation
    LEVEL_2 = 2  # Goal change ("Don't book it, just show options") -> New branch, invalidate downstream
    LEVEL_3 = 3  # Explicit cancellation -> Stop pending eligible work
    LEVEL_4 = 4  # Interruption during irreversible action -> Halt & reconcile external state


class Event(BaseModel):
    """Immutable event in the event log."""
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    event_type: EventType
    timestamp: float = Field(..., description="Virtual clock timestamp in seconds")
    snapshot_id: str = Field(..., description="Snapshot ID during which the event occurred")
    branch_id: str = Field(default="main", description="Branch identifier")
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "frozen": True  # Enforce immutability
    }
