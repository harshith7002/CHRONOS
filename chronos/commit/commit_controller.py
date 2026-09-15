"""
CHRONOS Commit Controller
4-Stage Irreversible Action Gatekeeper: SPECULATIVE -> PREPARE -> CONFIRMATION -> COMMIT.
"""

from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import uuid

from chronos.protocol.events import Event, EventType
from chronos.protocol.schemas import CommitState, ExecutionClass, ToolCall, ToolResult
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.state.branch_manager import TemporalStateManager
from chronos.commit.idempotency import IdempotencyRegistry
from chronos.tools.manifest import ToolRegistry
from chronos.tools.scheduler import ToolScheduler


class PrepareToken(BaseModel):
    token_id: str = Field(default_factory=lambda: f"tok_{uuid.uuid4().hex[:8]}")
    tool_name: str
    arguments: Dict[str, Any]
    snapshot_id: str
    branch_id: str
    idempotency_key: str
    created_at: float
    confirmed: bool = False
    state: CommitState = CommitState.SPECULATIVE
    verification_errors: List[str] = Field(default_factory=list)


class CommitController:
    """
    Guarantees that irreversible actions only execute with explicit confirmation,
    valid non-stale snapshot binding, and strict idempotency deduplication.
    """

    def __init__(
        self,
        clock: VirtualClock,
        event_log: EventLog,
        state_mgr: TemporalStateManager,
        idempotency: IdempotencyRegistry,
        registry: ToolRegistry,
        scheduler: ToolScheduler,
    ):
        self.clock = clock
        self.event_log = event_log
        self.state_mgr = state_mgr
        self.idempotency = idempotency
        self.registry = registry
        self.scheduler = scheduler
        self._lock = threading.RLock()
        
        # In-flight tokens: {token_id: PrepareToken}
        self._tokens: Dict[str, PrepareToken] = {}
        # Completed commits: {idempotency_key: Any}
        self._committed_keys: Dict[str, Any] = {}

    def prepare_action(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        snapshot_id: Optional[str] = None,
        branch_id: Optional[str] = None,
    ) -> PrepareToken:
        """
        Stage 1 & 2: SPECULATIVE -> PREPARE.
        Validates the tool and generates prepare token + idempotency key.
        """
        with self._lock:
            now = self.clock.now()
            current_snap = self.state_mgr.get_current_snapshot()
            target_snapshot_id = snapshot_id or current_snap.snapshot_id
            target_branch_id = branch_id or current_snap.branch_id

            tool_defn = self.registry.get_tool(tool_name)
            if not tool_defn:
                raise ValueError(f"Unknown tool '{tool_name}'")

            idempotency_key = self.idempotency.generate_key(tool_name, target_snapshot_id, arguments)

            token = PrepareToken(
                tool_name=tool_name,
                arguments=arguments,
                snapshot_id=target_snapshot_id,
                branch_id=target_branch_id,
                idempotency_key=idempotency_key,
                created_at=now,
                confirmed=not tool_defn.requires_confirmation,  # auto-confirmed if read-only
                state=CommitState.PREPARE if not tool_defn.requires_confirmation else CommitState.CONFIRMATION,
            )
            self._tokens[token.token_id] = token

            # If tool requires confirmation, request it
            if tool_defn.requires_confirmation:
                self.event_log.append(
                    Event(
                        event_type=EventType.CONFIRMATION_REQUESTED,
                        timestamp=now,
                        snapshot_id=target_snapshot_id,
                        branch_id=target_branch_id,
                        payload={
                            "token_id": token.token_id,
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "idempotency_key": idempotency_key,
                        },
                    )
                )

            return token

    def confirm_action(self, token_id: str, confirmed: bool = True) -> PrepareToken:
        """
        Stage 3: CONFIRMATION.
        Records user confirmation signal.
        """
        with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                raise ValueError(f"Token '{token_id}' not found")

            token.confirmed = confirmed
            now = self.clock.now()

            self.event_log.append(
                Event(
                    event_type=EventType.CONFIRMATION_RECEIVED,
                    timestamp=now,
                    snapshot_id=token.snapshot_id,
                    branch_id=token.branch_id,
                    payload={
                        "token_id": token.token_id,
                        "confirmed": confirmed,
                        "tool_name": token.tool_name,
                    },
                )
            )
            return token

    def verify_preconditions(self, token: PrepareToken) -> Tuple[bool, List[str]]:
        """
        Rigorous safety checks before executing COMMIT.
        """
        errors = []
        current_snap = self.state_mgr.get_current_snapshot()
        tool_defn = self.registry.get_tool(token.tool_name)

        # 1. Snapshot validity & non-superseded check
        if current_snap.snapshot_id != token.snapshot_id:
            errors.append(
                f"Stale snapshot: token was prepared on '{token.snapshot_id}', but current state is '{current_snap.snapshot_id}'"
            )

        # 2. Explicit confirmation check for irreversible actions
        if tool_defn and tool_defn.requires_confirmation and not token.confirmed:
            errors.append("Explicit confirmation missing for irreversible action")

        # 3. Slot argument consistency
        for slot_dep in (tool_defn.slot_dependencies if tool_defn else []):
            if slot_dep in current_snap.intent_slots and slot_dep in token.arguments:
                if current_snap.intent_slots[slot_dep] != token.arguments[slot_dep]:
                    errors.append(
                        f"Slot argument mismatch for '{slot_dep}': slot is '{current_snap.intent_slots[slot_dep]}', token has '{token.arguments[slot_dep]}'"
                    )

        return len(errors) == 0, errors

    def commit(self, token_id: str) -> Tuple[bool, Optional[ToolCall], List[str]]:
        """
        Stage 4: COMMIT.
        Verifies preconditions, prevents duplicates, dispatches call, and records COMMIT event.
        """
        with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                return False, None, [f"Token '{token_id}' not found"]

            now = self.clock.now()

            # Idempotency check: if already committed, return success without duplicate execution
            if self.idempotency.has_committed(token.idempotency_key):
                return True, None, ["Duplicate commit suppressed via idempotency key"]

            # Precondition Verification
            is_valid, errors = self.verify_preconditions(token)
            if not is_valid:
                token.state = CommitState.REJECTED
                token.verification_errors = errors
                return False, None, errors

            # Idempotency check
            is_new, record = self.idempotency.register_or_get(
                idempotency_key=token.idempotency_key,
                call_id=f"commit_{token.token_id}",
                snapshot_id=token.snapshot_id,
                tool_name=token.tool_name,
                arguments=token.arguments,
                created_at=now,
            )

            if not is_new and record and record.status == "COMMITTED":
                # Already committed: return cached without duplicate execution
                return True, None, ["Duplicate commit suppressed via idempotency key"]

            # Dispatch tool call via ToolScheduler
            call = self.scheduler.dispatch(
                tool_name=token.tool_name,
                arguments=token.arguments,
                snapshot_id=token.snapshot_id,
                branch_id=token.branch_id,
                slot_inputs=self.state_mgr.get_current_snapshot().intent_slots,
                idempotency_key=token.idempotency_key,
            )

            token.state = CommitState.COMMIT

            # Record COMMIT event
            self.event_log.append(
                Event(
                    event_type=EventType.COMMIT,
                    timestamp=now,
                    snapshot_id=token.snapshot_id,
                    branch_id=token.branch_id,
                    payload={
                        "token_id": token.token_id,
                        "call_id": call.call_id,
                        "tool_name": token.tool_name,
                        "arguments": token.arguments,
                        "idempotency_key": token.idempotency_key,
                    },
                )
            )

            # Mark in idempotency ledger
            self.idempotency.mark_committed(token.idempotency_key, now, {"call_id": call.call_id})

            return True, call, []

    def get_token(self, token_id: str) -> Optional[PrepareToken]:
        with self._lock:
            return self._tokens.get(token_id)

    def get_all_tokens(self) -> List[PrepareToken]:
        with self._lock:
            return list(self._tokens.values())

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()
            self._committed_keys.clear()
