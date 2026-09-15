"""
Unit tests for Temporal State Snapshots, Branching, and Garbage Collection.
"""

import pytest
from chronos.state.event_log import EventLog
from chronos.state.snapshot import StateSnapshot, SnapshotValidity
from chronos.state.branch_manager import TemporalStateManager


def test_snapshot_lineage_and_immutability():
    log = EventLog()
    mgr = TemporalStateManager(log)

    root = mgr.get_current_snapshot()
    assert root.snapshot_id == "v0"
    assert root.intent_slots == {}

    # Evolve to v1
    v1 = mgr.create_new_snapshot(
        timestamp=1.0,
        slot_updates={"destination": "Delhi", "date": "Tomorrow"},
    )
    assert v1.snapshot_id == "v1"
    assert v1.parent_snapshot_id == "v0"
    assert v1.intent_slots == {"destination": "Delhi", "date": "Tomorrow"}

    # Historical v0 must be unchanged
    assert root.intent_slots == {}

    # Evolve to v2 (update destination only)
    v2 = mgr.create_new_snapshot(
        timestamp=2.0,
        slot_updates={"destination": "Mumbai"},
    )
    assert v2.snapshot_id == "v2"
    assert v2.parent_snapshot_id == "v1"
    assert v2.intent_slots == {"destination": "Mumbai", "date": "Tomorrow"}

    # Verify v1 is still Delhi
    v1_rechecked = mgr.get_snapshot("v1")
    assert v1_rechecked.intent_slots["destination"] == "Delhi"


def test_branching_and_garbage_collection():
    log = EventLog()
    mgr = TemporalStateManager(log)

    # Branch to experimental
    b_snap = mgr.branch("experimental", timestamp=1.5, goal_override="Explore train options")
    assert b_snap.branch_id == "experimental"
    assert mgr.active_branch_id == "experimental"

    branches = mgr.get_all_branches()
    assert len(branches) == 2
    main_b = [b for b in branches if b["branch_id"] == "main"][0]
    assert main_b["status"] == "SUPERSEDED"
