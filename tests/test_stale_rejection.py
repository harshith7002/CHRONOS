"""
Unit tests for Stale Result Detection and Rejection Invariants.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.protocol.schemas import CallStatus
from chronos.protocol.events import EventType


def test_late_arriving_result_rejected_as_stale():
    clock = VirtualClock(mode="stepped")
    agent = ChronosAgent(clock=clock)

    # 1. Dispatch search for Delhi on v1
    agent.process_user_input("Find me a flight to Delhi tomorrow")
    assert agent.state_mgr.current_snapshot_id == "v1"

    # Step clock slightly (tool is running)
    agent.step_time(0.05)

    # 2. Interruption: switch to Mumbai on v2
    agent.process_user_input("Actually Mumbai")
    assert agent.state_mgr.current_snapshot_id == "v2"

    # 3. Force old Delhi v1 result to arrive late
    stale_res = agent.force_inject_stale_result(
        call_id="call_delhi_delayed",
        origin_snapshot_id="v1",
        tool_name="search_flights",
        output=[{"flight_id": "DEL-101", "price": 5000}],
    )

    # Invariants:
    # 1. Result must be classified as STALE_REJECTED
    assert stale_res.status == CallStatus.STALE_REJECTED

    # 2. Event log must contain STALE_RESULT_REJECTED event
    stale_events = agent.event_log.filter_by(event_type=EventType.STALE_RESULT_REJECTED)
    assert len(stale_events) == 1
    assert stale_events[0].payload["origin_snapshot_id"] == "v1"

    # 3. Current snapshot v2 must NOT be contaminated with Delhi data
    current_snap = agent.state_mgr.get_current_snapshot()
    assert current_snap.intent_slots["destination"] == "Mumbai"
    assert "DEL-101" not in str(current_snap.completed_tool_results)
