"""
CHRONOS Interruption Debouncer
Buffers streaming partial ASR / text tokens to avoid thrashing and premature cancellations.
"""

from __future__ import annotations
import threading
from typing import Callable, Optional
from chronos.protocol.messages import UserMessage
from chronos.clock.virtual_clock import VirtualClock


class InterruptionDebouncer:
    """
    Debouncer that smooths rapid partial perception inputs.
    """

    def __init__(self, clock: VirtualClock, debounce_window_sec: float = 0.2):
        self.clock = clock
        self.debounce_window_sec = debounce_window_sec
        self._lock = threading.RLock()
        self._current_buffer: str = ""
        self._last_token_time: float = 0.0
        self._scheduled_task = None
        self._on_flush_callback: Optional[Callable[[UserMessage], None]] = None

    def set_on_flush(self, callback: Callable[[UserMessage], None]) -> None:
        with self._lock:
            self._on_flush_callback = callback

    def push_token(self, token: str, is_final: bool = False) -> None:
        with self._lock:
            now = self.clock.now()
            self._last_token_time = now
            self._current_buffer = (self._current_buffer + " " + token.strip()).strip()

            if is_final:
                # Flush immediately for final transcript
                self._flush()
            else:
                # Cancel previous timer and schedule new debounce timer
                if self._scheduled_task:
                    self._scheduled_task.cancelled = True
                self._scheduled_task = self.clock.schedule(
                    self.debounce_window_sec,
                    self._flush,
                )

    def _flush(self) -> None:
        with self._lock:
            if not self._current_buffer:
                return

            text = self._current_buffer
            self._current_buffer = ""
            msg = UserMessage(
                text=text,
                timestamp=self.clock.now(),
                is_partial=False,
                source="asr",
            )
            if self._on_flush_callback:
                self._on_flush_callback(msg)

    def clear(self) -> None:
        with self._lock:
            self._current_buffer = ""
            if self._scheduled_task:
                self._scheduled_task.cancelled = True
