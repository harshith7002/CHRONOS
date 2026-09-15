"""
Unit tests for Deterministic Virtual Clock.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock


def test_virtual_clock_stepping():
    clock = VirtualClock(initial_time=10.0, mode="stepped")
    assert clock.now() == 10.0

    clock.advance(0.5)
    assert clock.now() == 10.5

    clock.advance_to(15.0)
    assert clock.now() == 15.0


def test_scheduled_task_execution():
    clock = VirtualClock(initial_time=0.0, mode="stepped")
    executed = []

    def callback(val):
        executed.append((clock.now(), val))

    clock.schedule(0.2, callback, "first")
    clock.schedule(0.5, callback, "second")

    assert len(executed) == 0

    clock.advance(0.1)
    assert len(executed) == 0

    clock.advance(0.15)  # now at 0.25 -> "first" executed at 0.2
    assert len(executed) == 1
    assert executed[0] == (0.2, "first")

    clock.advance(0.3)  # now at 0.55 -> "second" executed at 0.5
    assert len(executed) == 2
    assert executed[1] == (0.5, "second")


def test_scheduled_task_cancellation():
    clock = VirtualClock(initial_time=0.0, mode="stepped")
    executed = []

    task = clock.schedule(0.5, lambda: executed.append(1))
    task.cancelled = True

    clock.advance(1.0)
    assert len(executed) == 0
