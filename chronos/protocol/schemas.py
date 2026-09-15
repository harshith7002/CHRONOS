"""
CHRONOS Protocol Schemas
Defines execution classes, tool definitions, tool calls, and intent schemas.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
import uuid


class ExecutionClass(str, Enum):
    READ_ONLY = "READ_ONLY"                  # Safe for speculative execution
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"    # May execute under controlled speculative rollback
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"  # Must strictly pass commit controller & confirmation


class CallStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    STALE_REJECTED = "STALE_REJECTED"


class CommitState(str, Enum):
    SPECULATIVE = "SPECULATIVE"
    PREPARE = "PREPARE"
    CONFIRMATION = "CONFIRMATION"
    COMMIT = "COMMIT"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class BranchStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    COMPLETED = "COMPLETED"
    DISCARDED = "DISCARDED"


class ToolDefinition(BaseModel):
    """Dynamic tool definition loaded from tool manifest."""
    name: str
    description: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    execution_class: ExecutionClass = ExecutionClass.READ_ONLY
    reversible: bool = True
    idempotent: bool = True
    requires_confirmation: bool = False
    slot_dependencies: List[str] = Field(default_factory=list, description="Intent slots this tool depends on")
    compensation_tool: Optional[str] = Field(default=None, description="Rollback tool name for reversible writes")
    estimated_duration: float = Field(default=0.1, description="Estimated duration in virtual seconds")


class ToolCall(BaseModel):
    """An instance of a scheduled or executing tool call."""
    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    tool_name: str
    snapshot_id: str
    branch_id: str = "main"
    arguments: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list, description="List of upstream call_ids")
    slot_inputs: Dict[str, Any] = Field(default_factory=dict, description="Captured slot values at dispatch time")
    idempotency_key: Optional[str] = None
    created_at: float
    status: CallStatus = CallStatus.PENDING
    execution_class: ExecutionClass = ExecutionClass.READ_ONLY


class ToolResult(BaseModel):
    """The result returned from tool execution."""
    call_id: str
    tool_name: str
    snapshot_id: str
    branch_id: str = "main"
    status: CallStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    dispatched_at: float
    completed_at: float
    idempotency_key: Optional[str] = None
