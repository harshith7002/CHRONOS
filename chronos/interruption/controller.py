"""
CHRONOS Interruption Controller
Classifies and processes the 5-level interruption hierarchy with selective invalidation.
"""

from __future__ import annotations
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from chronos.protocol.events import Event, EventType, InterruptionLevel
from chronos.protocol.schemas import CallStatus, ExecutionClass
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.state.branch_manager import TemporalStateManager
from chronos.tools.dag import ExecutionDAG
from chronos.tools.scheduler import ToolScheduler
from chronos.commit.commit_controller import CommitController


class InterruptionResult:
    def __init__(
        self,
        level: InterruptionLevel,
        description: str,
        new_snapshot_id: Optional[str] = None,
        cancelled_call_ids: Optional[Set[str]] = None,
        preserved_call_ids: Optional[Set[str]] = None,
        new_branch_id: Optional[str] = None,
    ):
        self.level = level
        self.description = description
        self.new_snapshot_id = new_snapshot_id
        self.cancelled_call_ids = cancelled_call_ids or set()
        self.preserved_call_ids = preserved_call_ids or set()
        self.new_branch_id = new_branch_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "description": self.description,
            "new_snapshot_id": self.new_snapshot_id,
            "cancelled_call_ids": list(self.cancelled_call_ids),
            "preserved_call_ids": list(self.preserved_call_ids),
            "new_branch_id": self.new_branch_id,
        }


class InterruptionController:
    """
    Evaluates incoming utterances/signals and coordinates state updates,
    branch transitions, and DAG cancellations.
    """

    BACKCHANNEL_PATTERNS = [
        r"^(yeah|yep|yes|ok|okay|sure|mhm|uh-huh|right|got it|cool|i see)$"
    ]
    CANCEL_PATTERNS = [
        r"^(stop|cancel|abort|halt|never mind|forget it|hold on|wait)$"
    ]
    GOAL_CHANGE_PATTERNS = [
        r"(don't book|do not book|just show|just list|switch to|instead of booking|change my goal|look for hotels instead)"
    ]

    def __init__(
        self,
        clock: VirtualClock,
        event_log: EventLog,
        state_mgr: TemporalStateManager,
        dag: ExecutionDAG,
        scheduler: ToolScheduler,
        commit_controller: Optional[CommitController] = None,
    ):
        self.clock = clock
        self.event_log = event_log
        self.state_mgr = state_mgr
        self.dag = dag
        self.scheduler = scheduler
        self.commit_controller = commit_controller
        self._lock = threading.RLock()

    def classify_intent(
        self,
        text: str,
        is_in_irreversible_phase: bool = False,
    ) -> Tuple[InterruptionLevel, Dict[str, Any]]:
        """
        Classifies user utterance into one of the 5 interruption levels.
        Returns: (InterruptionLevel, extracted_parameters)
        """
        cleaned = text.strip().lower()

        # Check Level 4: Interruption during irreversible action / commit phase
        if is_in_irreversible_phase and any(re.search(p, cleaned) for p in (self.CANCEL_PATTERNS + self.GOAL_CHANGE_PATTERNS + [r"wait", r"stop"])):
            return InterruptionLevel.LEVEL_4, {"reason": "User interrupted during irreversible commit"}

        # Check Level 0: Backchannel
        for pattern in self.BACKCHANNEL_PATTERNS:
            if re.match(pattern, cleaned):
                return InterruptionLevel.LEVEL_0, {}

        # Check Level 3: Explicit Cancel
        for pattern in self.CANCEL_PATTERNS:
            if re.match(pattern, cleaned):
                return InterruptionLevel.LEVEL_3, {}

        # Check Level 2: Goal Change
        for pattern in self.GOAL_CHANGE_PATTERNS:
            if re.search(pattern, cleaned):
                return InterruptionLevel.LEVEL_2, {"new_goal": text}

        # Check Level 1: Local slot correction or update
        # Parse slot patterns like "actually X", "change Y to Z", "to Mumbai", "under 5000", etc.
        slot_updates = self._extract_slot_updates(text)
        if slot_updates:
            return InterruptionLevel.LEVEL_1, {"slots": slot_updates}

        # Default fallback for general user inputs: slot update or new intent
        return InterruptionLevel.LEVEL_1, {"slots": slot_updates}

    def _extract_slot_updates(self, text: str) -> Dict[str, Any]:
        """Domain-flexible slot parser for test & demo cases."""
        slots: Dict[str, Any] = {}
        cleaned = text.strip().lower()

        # Destination patterns ("actually Mumbai", "to Mumbai", "destination Mumbai")
        dest_match = re.search(r"(?:actually|to|dest|destination)\s+([a-zA-Z]+)", cleaned)
        if dest_match:
            dest_val = dest_match.group(1).title()
            if dest_val.lower() not in ("the", "a", "my", "me", "book", "it", "cheapest"):
                slots["destination"] = dest_val

        # Date patterns ("tomorrow", "friday", "next monday")
        date_match = re.search(r"\b(tomorrow|friday|saturday|sunday|monday|tuesday|wednesday|thursday|today)\b", cleaned)
        if date_match:
            slots["date"] = date_match.group(1).capitalize()

        # Time of day ("morning", "evening", "afternoon", "night")
        time_match = re.search(r"\b(morning|evening|afternoon|night)\b", cleaned)
        if time_match:
            slots["time_of_day"] = time_match.group(1).capitalize()

        # Price limit ("under 10000", "max 5000", "< 8000", "below 12000")
        price_match = re.search(r"(?:under|max|below|budget|limit|<|less than)\s*(\d+)", cleaned)
        if price_match:
            slots["max_price"] = float(price_match.group(1))

        # Passenger name ("passenger John Doe", "name is Alice")
        passenger_match = re.search(r"(?:passenger|name is|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
        if passenger_match:
            slots["passenger_name"] = passenger_match.group(1)

        # Selection criterion ("cheapest", "earliest", "fastest")
        crit_match = re.search(r"\b(cheapest|earliest|fastest)\b", cleaned)
        if crit_match:
            slots["criterion"] = crit_match.group(1)

        # Multimodal indicator / diagnostic correction patterns
        if "power led" in cleaned or "power indicator" in cleaned or "power light" in cleaned:
            slots["indicator_type"] = "power_led"
        elif "overheating" in cleaned or "temp warning" in cleaned or "coolant" in cleaned:
            slots["indicator_type"] = "temp_warning"

        return slots

    def handle_interruption(
        self,
        text: str,
        is_in_irreversible_phase: bool = False,
    ) -> InterruptionResult:
        """
        Main entry point for handling incoming user speech/text during execution.
        """
        with self._lock:
            now = self.clock.now()
            current_snap = self.state_mgr.get_current_snapshot()

            level, params = self.classify_intent(text, is_in_irreversible_phase)

            # Record INTERRUPTION event
            self.event_log.append(
                Event(
                    event_type=EventType.INTERRUPTION,
                    timestamp=now,
                    snapshot_id=current_snap.snapshot_id,
                    branch_id=current_snap.branch_id,
                    payload={
                        "level": level.value,
                        "text": text,
                        "params": params,
                    },
                )
            )

            # LEVEL 0: Backchannel / Acknowledgment
            if level == InterruptionLevel.LEVEL_0:
                return InterruptionResult(
                    level=level,
                    description="Backchannel acknowledged; no state change",
                    new_snapshot_id=current_snap.snapshot_id,
                )

            # LEVEL 1: Local Slot Correction
            if level == InterruptionLevel.LEVEL_1:
                slot_updates = params.get("slots", {})
                
                # Compute selective invalidation on DAG
                to_invalidate, to_preserve = self.dag.compute_selective_invalidation(
                    modified_slots=slot_updates,
                    current_snapshot_id=current_snap.snapshot_id,
                )

                # Selectively cancel invalidated calls
                if to_invalidate:
                    self.scheduler.cancel_calls(to_invalidate, reason="Slot correction invalidation")

                # Create evolved snapshot v(N+1)
                new_snap = self.state_mgr.create_new_snapshot(
                    timestamp=now,
                    slot_updates=slot_updates,
                    new_cancelled_calls=to_invalidate,
                )

                # Record INTENT_UPDATE event
                self.event_log.append(
                    Event(
                        event_type=EventType.INTENT_UPDATE,
                        timestamp=now,
                        snapshot_id=new_snap.snapshot_id,
                        branch_id=new_snap.branch_id,
                        payload={
                            "updated_slots": slot_updates,
                            "invalidated_calls": list(to_invalidate),
                            "preserved_calls": list(to_preserve),
                        },
                    )
                )

                return InterruptionResult(
                    level=level,
                    description=f"Slot correction: updated {list(slot_updates.keys())}",
                    new_snapshot_id=new_snap.snapshot_id,
                    cancelled_call_ids=to_invalidate,
                    preserved_call_ids=to_preserve,
                )

            # LEVEL 2: Goal Change
            if level == InterruptionLevel.LEVEL_2:
                # Cancel all active calls in current branch
                cancelled_count = self.scheduler.cancel_all_active(reason="Goal change branch switch")
                
                # Create a new branch
                new_branch_name = f"branch_{self.clock.now():.1f}"
                new_snap = self.state_mgr.branch(
                    new_branch_id=new_branch_name,
                    timestamp=now,
                    goal_override=params.get("new_goal", text),
                )

                return InterruptionResult(
                    level=level,
                    description=f"Goal change: branched to {new_branch_name}",
                    new_snapshot_id=new_snap.snapshot_id,
                    new_branch_id=new_branch_name,
                )

            # LEVEL 3: Explicit Interruption / Cancellation
            if level == InterruptionLevel.LEVEL_3:
                # Immediately cancel all pending/running calls
                active_calls = self.scheduler.get_active_calls()
                cancelled_ids = {c.call_id for c in active_calls}
                self.scheduler.cancel_calls(cancelled_ids, reason="User explicit stop")

                new_snap = self.state_mgr.create_new_snapshot(
                    timestamp=now,
                    new_cancelled_calls=cancelled_ids,
                )

                return InterruptionResult(
                    level=level,
                    description="Explicit cancellation: stopped all pending work",
                    new_snapshot_id=new_snap.snapshot_id,
                    cancelled_call_ids=cancelled_ids,
                )

            # LEVEL 4: Irreversible In-Flight Interruption
            if level == InterruptionLevel.LEVEL_4:
                # Stop progression
                active_calls = self.scheduler.get_active_calls()
                cancelled_ids = {c.call_id for c in active_calls}
                self.scheduler.cancel_calls(cancelled_ids, reason="Interrupted during commit")

                # If commit controller is attached, inspect tokens
                reconciliation_note = "Halted commit progression"
                if self.commit_controller:
                    for token in self.commit_controller.get_all_tokens():
                        if token.snapshot_id == current_snap.snapshot_id:
                            token.confirmed = False

                new_snap = self.state_mgr.create_new_snapshot(
                    timestamp=now,
                    new_cancelled_calls=cancelled_ids,
                )

                return InterruptionResult(
                    level=level,
                    description=f"Level 4 emergency halt: {reconciliation_note}",
                    new_snapshot_id=new_snap.snapshot_id,
                    cancelled_call_ids=cancelled_ids,
                )

            return InterruptionResult(level=level, description="Processed")
