"""
CHRONOS Virtual Clock
Provides a deterministic virtual time abstraction for repeatable simulation, replay, and wall-clock sync.
"""

from __future__ import annotations
import asyncio
import heapq
import threading
import time
from typing import Callable, List, Optional, Tuple, Any


class ScheduledTask:
    def __init__(self, trigger_time: float, task_id: int, callback: Callable[..., Any], args: Tuple[Any, ...], kwargs: dict):
        self.trigger_time = trigger_time
        self.task_id = task_id
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.cancelled = False

    def __lt__(self, other: ScheduledTask) -> bool:
        return self.trigger_time < other.trigger_time


class VirtualClock:
    """
    Deterministic Virtual Clock.
    In stepped/simulated mode: time only advances when explicitly requested (or driven by event queues).
    In wall-clock mode: advances based on monotonic time multiplied by time_scale.
    """

    def __init__(self, initial_time: float = 0.0, mode: str = "stepped", time_scale: float = 1.0):
        self._current_time: float = initial_time
        self._mode: str = mode  # "stepped" or "realtime"
        self._time_scale: float = time_scale
        self._lock = threading.RLock()
        self._task_counter = 0
        self._task_queue: List[ScheduledTask] = []
        self._wall_start_monotonic: float = time.monotonic()
        self._clock_start_time: float = initial_time
        self._listeners: List[Callable[[float], None]] = []

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str, time_scale: float = 1.0) -> None:
        with self._lock:
            now = self.now()
            self._mode = mode
            self._time_scale = time_scale
            self._current_time = now
            self._clock_start_time = now
            self._wall_start_monotonic = time.monotonic()

    def now(self) -> float:
        """Get current virtual time in seconds."""
        with self._lock:
            if self._mode == "realtime":
                elapsed = (time.monotonic() - self._wall_start_monotonic) * self._time_scale
                self._current_time = self._clock_start_time + elapsed
            return self._current_time

    def advance_to(self, target_time: float) -> List[Any]:
        """Advance time to target_time in stepped mode, firing any scheduled tasks due."""
        results = []
        with self._lock:
            if target_time < self._current_time:
                raise ValueError(f"Cannot rewind virtual clock from {self._current_time} to {target_time}")
            
            while self._task_queue and self._task_queue[0].trigger_time <= target_time:
                task = heapq.heappop(self._task_queue)
                if not task.cancelled:
                    self._current_time = task.trigger_time
                    res = task.callback(*task.args, **task.kwargs)
                    results.append(res)
                    self._notify_listeners(self._current_time)

            self._current_time = target_time
            self._notify_listeners(self._current_time)
        return results

    def advance(self, delta_seconds: float) -> List[Any]:
        """Advance time by delta_seconds in stepped mode."""
        return self.advance_to(self.now() + delta_seconds)

    def schedule(self, delay: float, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> ScheduledTask:
        """Schedule a callback to run after delay virtual seconds."""
        with self._lock:
            self._task_counter += 1
            trigger_time = self.now() + delay
            task = ScheduledTask(trigger_time, self._task_counter, callback, args, kwargs)
            heapq.heappush(self._task_queue, task)
            return task

    def add_listener(self, listener: Callable[[float], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _notify_listeners(self, current_time: float) -> None:
        for listener in self._listeners:
            try:
                listener(current_time)
            except Exception:
                pass

    def reset(self, initial_time: float = 0.0) -> None:
        with self._lock:
            self._current_time = initial_time
            self._clock_start_time = initial_time
            self._wall_start_monotonic = time.monotonic()
            self._task_queue.clear()
            self._task_counter = 0
