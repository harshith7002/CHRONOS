"""
CHRONOS Fast Response & Floor Controller
Decouples ultra-low-latency acknowledgments & interruption signals from the slow reasoning path.
"""

from __future__ import annotations
import threading
from typing import Any, Callable, Dict, Optional, Tuple
from chronos.protocol.events import Event, EventType, InterruptionLevel
from chronos.protocol.messages import FastAckSignal, AgentResponse
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog


class FloorController:
    """
    Manages conversational turn-taking, floor ownership, and instant fast-path feedback.
    """

    def __init__(self, clock: VirtualClock, event_log: EventLog):
        self.clock = clock
        self.event_log = event_log
        self._lock = threading.RLock()
        
        # Floor ownership: 'USER' or 'AGENT' or 'IDLE'
        self._floor_owner: str = "IDLE"
        self._active_stream_id: Optional[str] = None
        self._listeners = []

    @property
    def floor_owner(self) -> str:
        with self._lock:
            return self._floor_owner

    def user_started_speaking(self) -> None:
        """User seizes the floor immediately."""
        with self._lock:
            self._floor_owner = "USER"

    def user_finished_speaking(self) -> None:
        with self._lock:
            self._floor_owner = "AGENT"

    def agent_finished_turn(self) -> None:
        with self._lock:
            self._floor_owner = "IDLE"

    def generate_fast_ack(
        self,
        level: InterruptionLevel,
        snapshot_id: str,
        slot_updates: Optional[Dict[str, Any]] = None,
        is_cancel: bool = False,
    ) -> Optional[FastAckSignal]:
        """
        Fast path response generated in milliseconds without invoking slow LLM / planning.
        """
        with self._lock:
            now = self.clock.now()
            ack_text = None
            immediate_cancel = False

            if level == InterruptionLevel.LEVEL_0:
                ack_text = "Mm-hmm, got it."
            elif level == InterruptionLevel.LEVEL_1 and slot_updates:
                slots_str = ", ".join([f"{k}: {v}" for k, v in slot_updates.items()])
                ack_text = f"Got it, switching to {slots_str}."
            elif level == InterruptionLevel.LEVEL_2:
                ack_text = "Understood, changing the goal."
                immediate_cancel = True
            elif level == InterruptionLevel.LEVEL_3:
                ack_text = "Stopping all active tasks."
                immediate_cancel = True
            elif level == InterruptionLevel.LEVEL_4:
                ack_text = "Hold on, reconciling the booking state."
                immediate_cancel = True

            if ack_text:
                signal = FastAckSignal(
                    level=level,
                    ack_text=ack_text,
                    immediate_cancel=immediate_cancel,
                    timestamp=now,
                )
                self.event_log.append(
                    Event(
                        event_type=EventType.FAST_ACK,
                        timestamp=now,
                        snapshot_id=snapshot_id,
                        payload={
                            "ack_text": ack_text,
                            "level": level.value,
                            "immediate_cancel": immediate_cancel,
                        },
                    )
                )
                return signal

            return None
