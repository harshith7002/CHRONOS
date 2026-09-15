"""
CHRONOS Agent Orchestrator
Integrated Temporal Control Plane coordinating perception, state, scheduler, interruption, and commit pipeline.
"""

from __future__ import annotations
import threading
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from chronos.protocol.events import Event, EventType, InterruptionLevel
from chronos.protocol.schemas import (
    CallStatus,
    CommitState,
    ExecutionClass,
    ToolCall,
    ToolResult,
)
from chronos.protocol.messages import UserMessage, FastAckSignal, AgentResponse
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.state.snapshot import StateSnapshot
from chronos.state.branch_manager import TemporalStateManager
from chronos.tools.manifest import ToolRegistry, create_default_travel_manifest
from chronos.tools.dag import ExecutionDAG, DAGNode
from chronos.tools.scheduler import ToolScheduler
from chronos.commit.idempotency import IdempotencyRegistry
from chronos.commit.commit_controller import CommitController, PrepareToken
from chronos.interruption.controller import InterruptionController, InterruptionResult
from chronos.floor.fast_path import FloorController
from chronos.perception.adapter import PerceptionAdapter
from chronos.perception.grounding import MultimodalGrounder


class ChronosAgent:
    """
    Production-grade prototype of the CHRONOS Temporal Control Plane.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        clock: Optional[VirtualClock] = None,
    ):
        self._lock = threading.RLock()

        # 1. Clock
        self.clock = clock or VirtualClock(initial_time=0.0, mode="stepped")

        # 2. State & Event Log
        self.event_log = EventLog()
        self.state_mgr = TemporalStateManager(self.event_log)

        # 3. Dynamic Tool Subsystem
        self.registry = tool_registry or create_default_travel_manifest()
        self.dag = ExecutionDAG()
        self.scheduler = ToolScheduler(self.clock, self.event_log, self.registry, self.dag)

        # 4. Commit Controller & Idempotency
        self.idempotency = IdempotencyRegistry()
        self.commit_controller = CommitController(
            clock=self.clock,
            event_log=self.event_log,
            state_mgr=self.state_mgr,
            idempotency=self.idempotency,
            registry=self.registry,
            scheduler=self.scheduler,
        )

        # 5. Interruption Controller & Floor Controller
        self.interruption_controller = InterruptionController(
            clock=self.clock,
            event_log=self.event_log,
            state_mgr=self.state_mgr,
            dag=self.dag,
            scheduler=self.scheduler,
            commit_controller=self.commit_controller,
        )
        self.floor_controller = FloorController(self.clock, self.event_log)

        # 6. Perception Adapter & Grounding
        self.perception = PerceptionAdapter(self.clock, on_message=self._handle_user_message)
        self.grounder = MultimodalGrounder()

        # Active prepare tokens awaiting confirmation
        self._pending_prepare_token: Optional[PrepareToken] = None
        self._last_final_response: Optional[AgentResponse] = None

    def _handle_user_message(self, message: UserMessage) -> None:
        """Internal handler invoked when perception produces a flushed user turn."""
        self.process_user_input(message.text)

    def process_user_input(self, text: str) -> Dict[str, Any]:
        """
        Processes incoming user input through the full temporal control plane.
        """
        with self._lock:
            now = self.clock.now()
            current_snap = self.state_mgr.get_current_snapshot()
            
            # Record USER_INPUT event
            self.event_log.append(
                Event(
                    event_type=EventType.USER_INPUT,
                    timestamp=now,
                    snapshot_id=current_snap.snapshot_id,
                    branch_id=current_snap.branch_id,
                    payload={"text": text},
                )
            )

            # Check if this input is a confirmation response (e.g. "yes", "confirm", "proceed", "book it")
            cleaned = text.strip().lower()
            is_confirmation_turn = False
            if self._pending_prepare_token and any(kw in cleaned for kw in ("yes", "confirm", "proceed", "book", "sure")):
                is_confirmation_turn = True
                token = self.commit_controller.confirm_action(self._pending_prepare_token.token_id, confirmed=True)
                success, call, errors = self.commit_controller.commit(token.token_id)
                self._pending_prepare_token = None
                
                resp = AgentResponse(
                    response_id=f"resp_{self.clock.now():.2f}",
                    snapshot_id=self.state_mgr.current_snapshot_id,
                    text="Action committed successfully." if success else f"Commit rejected: {', '.join(errors)}",
                    is_provisional=False,
                    requires_confirmation=False,
                    timestamp=self.clock.now(),
                )
                self._last_final_response = resp
                return {
                    "action": "commit",
                    "success": success,
                    "errors": errors,
                    "response": resp.text,
                    "snapshot_id": self.state_mgr.current_snapshot_id,
                }

            # Otherwise, route through Interruption Controller
            is_in_irreversible = self._pending_prepare_token is not None
            level, extracted = self.interruption_controller.classify_intent(text, is_in_irreversible_phase=is_in_irreversible)

            # 1. Fast Path: Low-latency ack
            fast_ack = self.floor_controller.generate_fast_ack(
                level=level,
                snapshot_id=current_snap.snapshot_id,
                slot_updates=extracted.get("slots"),
                is_cancel=(level in (InterruptionLevel.LEVEL_2, InterruptionLevel.LEVEL_3, InterruptionLevel.LEVEL_4)),
            )

            # 2. Slow Path / State Evolution
            interruption_res = self.interruption_controller.handle_interruption(text, is_in_irreversible_phase=is_in_irreversible)
            new_snap = self.state_mgr.get_current_snapshot()

            # 3. Dynamic Planning & Tool Dispatch on New Snapshot
            scheduled_calls = self._plan_and_dispatch(new_snap, text)

            return {
                "level": level.value,
                "fast_ack": fast_ack.ack_text if fast_ack else None,
                "interruption": interruption_res.to_dict(),
                "snapshot_id": new_snap.snapshot_id,
                "scheduled_calls": [c.call_id for c in scheduled_calls],
            }

    def _plan_and_dispatch(self, snapshot: StateSnapshot, user_text: str) -> List[ToolCall]:
        """
        Dynamically derives plan from snapshot intent slots and available tools in manifest.
        """
        dispatched: List[ToolCall] = []
        slots = snapshot.intent_slots

        # If new booking intent is present (e.g., "book the cheapest one", "book flight"), avoid triggering on pure confirmation phrases
        cleaned_text = user_text.lower().strip()
        is_pure_confirmation = any(cleaned_text.startswith(kw) for kw in ("yes", "confirm", "proceed", "sure", "ok", "yep"))
        if "book" in cleaned_text and not is_pure_confirmation and not self._pending_prepare_token:
            # Check if we have flights in completed results matching current destination
            available_flights = None
            target_dest = slots.get("destination")
            for res in self.scheduler.get_completed_results().values():
                if res.tool_name == "search_flights" and res.output and res.status == CallStatus.COMPLETED:
                    # Verify destination matches
                    if not target_dest or any(f.get("dest", "").lower() == target_dest.lower() for f in (res.output if isinstance(res.output, list) else [])):
                        available_flights = res.output
                        break

            if available_flights:
                best_flight = self.grounder.ground_flight_selection(user_text, available_flights)
                if best_flight:
                    flight_id = best_flight.get("flight_id")
                    price = best_flight.get("price", 0)
                    # Prepare irreversible write
                    prepare_tok = self.commit_controller.prepare_action(
                        tool_name="book_flight",
                        arguments={
                            "flight_id": flight_id,
                            "passenger_name": slots.get("passenger_name", "Passenger"),
                            "amount": price,
                        },
                        snapshot_id=snapshot.snapshot_id,
                        branch_id=snapshot.branch_id,
                    )
                    self._pending_prepare_token = prepare_tok
                    return dispatched

        # If destination slot is present, dispatch search_flights if not already running for this snapshot
        if "destination" in slots and self.registry.has_tool("search_flights"):
            # Check if already dispatched for this snapshot
            already_dispatched = any(
                c.snapshot_id == snapshot.snapshot_id and c.tool_name == "search_flights"
                for c in self.scheduler.get_active_calls()
            )
            if not already_dispatched:
                call = self.scheduler.dispatch(
                    tool_name="search_flights",
                    arguments={
                        "destination": slots["destination"],
                        "date": slots.get("date"),
                        "time_of_day": slots.get("time_of_day"),
                        "max_price": slots.get("max_price"),
                    },
                    snapshot_id=snapshot.snapshot_id,
                    branch_id=snapshot.branch_id,
                    slot_inputs=dict(slots),
                )
                dispatched.append(call)

        return dispatched

    def step_time(self, delta_seconds: float) -> List[Any]:
        """
        Advance virtual clock and trigger completed tool executions & downstream flows.
        """
        with self._lock:
            # Advance clock
            results = self.clock.advance(delta_seconds)
            
            # Check if any completed tool enables a final response or downstream step
            current_snap = self.state_mgr.get_current_snapshot()
            for res in self.scheduler.get_completed_results().values():
                if res.snapshot_id == current_snap.snapshot_id and res.status == CallStatus.COMPLETED:
                    if res.tool_name == "search_flights" and not self._last_final_response:
                        resp_text = f"Found {len(res.output or [])} options for {current_snap.intent_slots.get('destination', 'your trip')}."
                        self.event_log.append(
                            Event(
                                event_type=EventType.FINAL_RESPONSE,
                                timestamp=self.clock.now(),
                                snapshot_id=current_snap.snapshot_id,
                                branch_id=current_snap.branch_id,
                                payload={"text": resp_text, "flights": res.output},
                            )
                        )
            return results

    def force_inject_stale_result(
        self,
        call_id: str,
        origin_snapshot_id: str,
        tool_name: str,
        output: Any,
    ) -> ToolResult:
        """
        Directly inject a late-arriving tool result to verify stale rejection.
        """
        with self._lock:
            fake_result = ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                snapshot_id=origin_snapshot_id,
                status=CallStatus.COMPLETED,
                output=output,
                dispatched_at=0.0,
                completed_at=self.clock.now(),
            )
            return self.scheduler.process_tool_result(
                fake_result,
                current_snapshot_id=self.state_mgr.current_snapshot_id,
            )

    def get_state_summary(self) -> Dict[str, Any]:
        """
        Produces complete observable state for evaluation metrics and UI control plane.
        """
        with self._lock:
            current_snap = self.state_mgr.get_current_snapshot()
            active_calls = self.scheduler.get_active_calls()
            cancelled_calls = self.scheduler.get_cancelled_calls()
            stale_results = self.scheduler.get_stale_results()
            events = self.event_log.get_all()
            tokens = self.commit_controller.get_all_tokens()

            commit_status_str = "IDLE"
            if self._pending_prepare_token:
                commit_status_str = f"AWAITING_CONFIRMATION ({self._pending_prepare_token.tool_name})"
            elif any(t.state == CommitState.COMMIT for t in tokens):
                commit_status_str = "COMMITTED"

            return {
                "virtual_time": round(self.clock.now(), 3),
                "clock_mode": self.clock.mode,
                "current_snapshot": {
                    "snapshot_id": current_snap.snapshot_id,
                    "version_number": current_snap.version_number,
                    "parent_snapshot_id": current_snap.parent_snapshot_id,
                    "branch_id": current_snap.branch_id,
                    "validity_status": current_snap.validity_status.value,
                    "timestamp": current_snap.timestamp,
                    "goal": current_snap.goal,
                },
                "intent_slots": current_snap.intent_slots,
                "active_tool_calls": [
                    {
                        "call_id": c.call_id,
                        "tool_name": c.tool_name,
                        "snapshot_id": c.snapshot_id,
                        "arguments": c.arguments,
                        "status": c.status.value,
                        "execution_class": c.execution_class.value,
                        "created_at": c.created_at,
                    }
                    for c in active_calls
                ],
                "cancelled_tool_calls": [
                    {
                        "call_id": c.call_id,
                        "tool_name": c.tool_name,
                        "snapshot_id": c.snapshot_id,
                        "arguments": c.arguments,
                    }
                    for c in cancelled_calls
                ],
                "stale_results": [
                    {
                        "call_id": r.call_id,
                        "tool_name": r.tool_name,
                        "origin_snapshot_id": r.snapshot_id,
                        "status": r.status.value,
                        "completed_at": r.completed_at,
                    }
                    for r in stale_results
                ],
                "branches": self.state_mgr.get_all_branches(),
                "all_snapshots": [s.model_dump() for s in self.state_mgr.get_all_snapshots()],
                "commit_status": commit_status_str,
                "commit_tokens": [t.model_dump() for t in tokens],
                "event_count": len(events),
                "recent_events": [e.model_dump() for e in events[-50:]],
            }

    def get_last_response(self) -> Optional[AgentResponse]:
        with self._lock:
            return self._last_final_response

    def reset(self) -> None:
        with self._lock:
            self.clock.reset()
            self.event_log.clear()
            self.state_mgr.reset()
            self.dag.clear()
            self.scheduler.clear()
            self.idempotency.clear()
            self.commit_controller.clear()
            self._pending_prepare_token = None
            self._last_final_response = None
