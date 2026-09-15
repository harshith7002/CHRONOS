"""
Unit tests for Fast-Path Floor Controller.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.floor.fast_path import FloorController
from chronos.protocol.events import InterruptionLevel, EventType


def test_fast_ack_generation():
    clock = VirtualClock()
    log = EventLog()
    floor = FloorController(clock, log)

    # Fast ack for level 0
    ack0 = floor.generate_fast_ack(InterruptionLevel.LEVEL_0, snapshot_id="v1")
    assert ack0 is not None
    assert "got it" in ack0.ack_text.lower()
    assert ack0.immediate_cancel is False

    # Fast ack for level 3
    ack3 = floor.generate_fast_ack(InterruptionLevel.LEVEL_3, snapshot_id="v1", is_cancel=True)
    assert ack3 is not None
    assert "stopping" in ack3.ack_text.lower()
    assert ack3.immediate_cancel is True

    # Check FAST_ACK event emitted in event log
    events = log.filter_by(event_type=EventType.FAST_ACK)
    assert len(events) == 2
