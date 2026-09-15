"""
CHRONOS Tool Scheduler
Asynchronous tool dispatch, speculative execution, cancellation tokens, and stale detection.
"""

from __future__ import annotations
import asyncio
import threading
import traceback
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from chronos.protocol.schemas import (
    CallStatus,
    ExecutionClass,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from chronos.protocol.events import Event, EventType
from chronos.clock.virtual_clock import VirtualClock, ScheduledTask
from chronos.state.event_log import EventLog
from chronos.tools.manifest import ToolRegistry
from chronos.tools.dag import ExecutionDAG, DAGNode


class ToolScheduler:
    """
    Schedules and executes tools based on dependency DAG and intent versions.
    """

    def __init__(
        self,
        clock: VirtualClock,
        event_log: EventLog,
        registry: ToolRegistry,
        dag: ExecutionDAG,
    ):
        self.clock = clock
        self.event_log = event_log
        self.registry = registry
        self.dag = dag
        self._lock = threading.RLock()
        
        # Active calls: {call_id: ToolCall}
        self._active_calls: Dict[str, ToolCall] = {}
        # In-flight cancellation tokens: {call_id: threading.Event / bool}
        self._cancellation_tokens: Dict[str, bool] = {}
        # Scheduled tasks on clock: {call_id: ScheduledTask}
        self._scheduled_clock_tasks: Dict[str, ScheduledTask] = {}
        # Completed results: {call_id: ToolResult}
        self._completed_results: Dict[str, ToolResult] = {}
        # Stale results log: List[ToolResult]
        self._stale_results: List[ToolResult] = []

    def dispatch(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        snapshot_id: str,
        branch_id: str = "main",
        slot_inputs: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
        override_duration: Optional[float] = None,
    ) -> ToolCall:
        """
        Dispatch a tool call. Validates execution class and schedules execution on virtual clock.
        """
        with self._lock:
            tool_defn = self.registry.get_tool(tool_name)
            if not tool_defn:
                raise ValueError(f"Tool '{tool_name}' not found in registry")

            call = ToolCall(
                tool_name=tool_name,
                snapshot_id=snapshot_id,
                branch_id=branch_id,
                arguments=arguments,
                depends_on=depends_on or [],
                slot_inputs=slot_inputs or {},
                idempotency_key=idempotency_key,
                created_at=self.clock.now(),
                status=CallStatus.DISPATCHED,
                execution_class=tool_defn.execution_class,
            )

            self._active_calls[call.call_id] = call
            self._cancellation_tokens[call.call_id] = False

            # Add to DAG
            self.dag.add_node(
                call_id=call.call_id,
                tool_name=tool_name,
                snapshot_id=snapshot_id,
                branch_id=branch_id,
                arguments=arguments,
                slot_bindings=slot_inputs or {},
                depends_on=depends_on,
            )
            self.dag.update_status(call.call_id, CallStatus.DISPATCHED)

            # Record event
            self.event_log.append(
                Event(
                    event_type=EventType.TOOL_DISPATCHED,
                    timestamp=self.clock.now(),
                    snapshot_id=snapshot_id,
                    branch_id=branch_id,
                    payload={
                        "call_id": call.call_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "execution_class": tool_defn.execution_class.value,
                        "idempotency_key": idempotency_key,
                    },
                )
            )

            # Schedule completion on virtual clock
            duration = override_duration if override_duration is not None else tool_defn.estimated_duration
            task = self.clock.schedule(
                duration,
                self._execute_and_complete,
                call.call_id,
            )
            self._scheduled_clock_tasks[call.call_id] = task

            return call

    def _execute_and_complete(self, call_id: str) -> Optional[ToolResult]:
        """Executed when tool duration elapses on the virtual clock."""
        with self._lock:
            call = self._active_calls.get(call_id)
            if not call:
                return None

            is_cancelled = self._cancellation_tokens.get(call_id, False) or call.status == CallStatus.CANCELLED
            if is_cancelled:
                # Call was already cancelled before completion
                return None

            handler = self.registry.get_handler(call.tool_name)
            dispatched_at = call.created_at
            now = self.clock.now()

            try:
                if handler:
                    output = handler(**call.arguments)
                else:
                    output = {"status": "success", "mock": True}

                result = ToolResult(
                    call_id=call_id,
                    tool_name=call.tool_name,
                    snapshot_id=call.snapshot_id,
                    branch_id=call.branch_id,
                    status=CallStatus.COMPLETED,
                    output=output,
                    error=None,
                    dispatched_at=dispatched_at,
                    completed_at=now,
                    idempotency_key=call.idempotency_key,
                )
            except Exception as ex:
                result = ToolResult(
                    call_id=call_id,
                    tool_name=call.tool_name,
                    snapshot_id=call.snapshot_id,
                    branch_id=call.branch_id,
                    status=CallStatus.FAILED,
                    output=None,
                    error=str(ex),
                    dispatched_at=dispatched_at,
                    completed_at=now,
                    idempotency_key=call.idempotency_key,
                )

        return self.process_tool_result(result)

    def process_tool_result(self, result: ToolResult, current_snapshot_id: Optional[str] = None) -> ToolResult:
        """
        Processes an arriving tool result.
        Strictly enforces stale result detection:
        If result.snapshot_id != current_snapshot_id, or if the call was cancelled, rejects it as STALE.
        """
        with self._lock:
            call_id = result.call_id
            call = self._active_calls.get(call_id)
            is_cancelled = self._cancellation_tokens.get(call_id, False) or (call and call.status == CallStatus.CANCELLED)

            # Check staleness: if current_snapshot_id is provided and differs, or if the snapshot is obsolete
            is_stale = False
            if is_cancelled:
                is_stale = True
            elif current_snapshot_id is not None and result.snapshot_id != current_snapshot_id:
                is_stale = True

            if is_stale:
                result.status = CallStatus.STALE_REJECTED
                self._stale_results.append(result)
                if call:
                    call.status = CallStatus.STALE_REJECTED
                self.dag.update_status(call_id, CallStatus.STALE_REJECTED, result)

                self.event_log.append(
                    Event(
                        event_type=EventType.STALE_RESULT_REJECTED,
                        timestamp=self.clock.now(),
                        snapshot_id=result.snapshot_id,
                        branch_id=result.branch_id,
                        payload={
                            "call_id": result.call_id,
                            "tool_name": result.tool_name,
                            "origin_snapshot_id": result.snapshot_id,
                            "current_snapshot_id": current_snapshot_id,
                            "reason": "Snapshot superseded or call cancelled prior to arrival",
                        },
                    )
                )
                return result

            # Valid result
            if result.status == CallStatus.COMPLETED:
                if call:
                    call.status = CallStatus.COMPLETED
                self._completed_results[call_id] = result
                self.dag.update_status(call_id, CallStatus.COMPLETED, result)

                self.event_log.append(
                    Event(
                        event_type=EventType.TOOL_COMPLETED,
                        timestamp=self.clock.now(),
                        snapshot_id=result.snapshot_id,
                        branch_id=result.branch_id,
                        payload={
                            "call_id": result.call_id,
                            "tool_name": result.tool_name,
                            "output": result.output,
                        },
                    )
                )
            else:
                if call:
                    call.status = CallStatus.FAILED
                self.dag.update_status(call_id, CallStatus.FAILED, result)
                self.event_log.append(
                    Event(
                        event_type=EventType.TOOL_FAILED,
                        timestamp=self.clock.now(),
                        snapshot_id=result.snapshot_id,
                        branch_id=result.branch_id,
                        payload={
                            "call_id": result.call_id,
                            "tool_name": result.tool_name,
                            "error": result.error,
                        },
                    )
                )

            return result

    def cancel_call(self, call_id: str, reason: str = "Interruption / Invalidation") -> bool:
        """Cancel a specific active tool call."""
        with self._lock:
            call = self._active_calls.get(call_id)
            if not call:
                return False

            if call.status in (CallStatus.COMPLETED, CallStatus.CANCELLED, CallStatus.FAILED):
                return False

            self._cancellation_tokens[call_id] = True
            call.status = CallStatus.CANCELLED
            self.dag.update_status(call_id, CallStatus.CANCELLED)

            # Cancel clock task if pending
            if call_id in self._scheduled_clock_tasks:
                self._scheduled_clock_tasks[call_id].cancelled = True

            self.event_log.append(
                Event(
                    event_type=EventType.TOOL_CANCELLED,
                    timestamp=self.clock.now(),
                    snapshot_id=call.snapshot_id,
                    branch_id=call.branch_id,
                    payload={
                        "call_id": call_id,
                        "tool_name": call.tool_name,
                        "reason": reason,
                    },
                )
            )
            return True

    def cancel_calls(self, call_ids: Set[str], reason: str = "Selective Invalidation") -> int:
        """Cancel multiple tool calls."""
        with self._lock:
            count = 0
            for cid in call_ids:
                if self.cancel_call(cid, reason=reason):
                    count += 1
            return count

    def cancel_all_active(self, reason: str = "Global Interruption") -> int:
        """Cancel all currently running/dispatched calls."""
        with self._lock:
            active_ids = {
                cid for cid, c in self._active_calls.items()
                if c.status in (CallStatus.PENDING, CallStatus.DISPATCHED, CallStatus.RUNNING)
            }
            return self.cancel_calls(active_ids, reason=reason)

    def get_active_calls(self) -> List[ToolCall]:
        with self._lock:
            return [
                c for c in self._active_calls.values()
                if c.status in (CallStatus.PENDING, CallStatus.DISPATCHED, CallStatus.RUNNING)
            ]

    def get_cancelled_calls(self) -> List[ToolCall]:
        with self._lock:
            return [c for c in self._active_calls.values() if c.status == CallStatus.CANCELLED]

    def get_stale_results(self) -> List[ToolResult]:
        with self._lock:
            return list(self._stale_results)

    def get_completed_results(self) -> Dict[str, ToolResult]:
        with self._lock:
            return dict(self._completed_results)

    def clear(self) -> None:
        with self._lock:
            self._active_calls.clear()
            self._cancellation_tokens.clear()
            self._scheduled_clock_tasks.clear()
            self._completed_results.clear()
            self._stale_results.clear()
