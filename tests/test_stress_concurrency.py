"""
Stress & Concurrency edge case tests for CHRONOS.
Tests rapid interleaving, multi-branch switching, stale bombardment, and duplicate safety.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.protocol.schemas import CallStatus
from chronos.protocol.events import EventType


def test_rapid_intent_churn_and_stale_bombardment():
    clock = VirtualClock(mode="stepped")
    agent = ChronosAgent(clock=clock)

    # 1. Rapid sequence of updates
    agent.process_user_input("Find flights to Delhi")   # v1
    agent.process_user_input("Actually Bangalore")       # v2
    agent.process_user_input("Wait no, Chennai")         # v3
    agent.process_user_input("Actually Mumbai")          # v4

    assert agent.state_mgr.current_snapshot_id == "v4"
    assert agent.state_mgr.get_current_snapshot().intent_slots["destination"] == "Mumbai"

    # 2. Bombard with stale results from v1, v2, v3
    res_v1 = agent.force_inject_stale_result("c1", "v1", "search_flights", [{"flight_id": "DEL-1"}])
    res_v2 = agent.force_inject_stale_result("c2", "v2", "search_flights", [{"flight_id": "BLR-1"}])
    res_v3 = agent.force_inject_stale_result("c3", "v3", "search_flights", [{"flight_id": "MAA-1"}])

    # All must be rejected
    assert res_v1.status == CallStatus.STALE_REJECTED
    assert res_v2.status == CallStatus.STALE_REJECTED
    assert res_v3.status == CallStatus.STALE_REJECTED

    # Event log must have 3 STALE_RESULT_REJECTED events
    stale_evts = agent.event_log.filter_by(event_type=EventType.STALE_RESULT_REJECTED)
    assert len(stale_evts) == 3

    # Step time for v4 search to complete
    agent.step_time(0.5)

    # Book and commit for v4
    agent.process_user_input("Book the cheapest one")
    res_commit = agent.process_user_input("Yes confirm booking")
    assert res_commit.get("success") is True

    # Retry storm: 10 duplicate confirmations
    for _ in range(10):
        dup_res = agent.process_user_input("Yes confirm booking")
        # Must not perform additional commits

    commits = agent.event_log.filter_by(event_type=EventType.COMMIT)
    assert len(commits) == 1, "Expected exactly 1 commit event despite retry storm"
