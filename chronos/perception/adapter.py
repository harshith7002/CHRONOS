"""
CHRONOS Perception Adapter
Bridges text, streaming ASR tokens, and multimodal inputs to the control plane.
"""

from __future__ import annotations
import threading
from typing import Any, Callable, Dict, List, Optional
from chronos.protocol.messages import UserMessage
from chronos.clock.virtual_clock import VirtualClock
from chronos.interruption.debouncer import InterruptionDebouncer


class PerceptionAdapter:
    """
    Ingests multimodal and audio/text streams and handles debouncing before dispatching to the agent.
    """

    def __init__(self, clock: VirtualClock, on_message: Optional[Callable[[UserMessage], None]] = None):
        self.clock = clock
        self.debouncer = InterruptionDebouncer(clock)
        self._on_message = on_message
        self._lock = threading.RLock()
        
        if on_message:
            self.debouncer.set_on_flush(on_message)

    def set_on_message(self, callback: Callable[[UserMessage], None]) -> None:
        with self._lock:
            self._on_message = callback
            self.debouncer.set_on_flush(callback)

    def receive_text(self, text: str) -> None:
        """Immediate full text message ingestion."""
        msg = UserMessage(
            text=text,
            timestamp=self.clock.now(),
            is_partial=False,
            source="text",
        )
        if self._on_message:
            self._on_message(msg)

    def receive_streaming_token(self, token: str, is_final: bool = False) -> None:
        """Stream token into the debouncer."""
        self.debouncer.push_token(token, is_final=is_final)
