"""
Unit tests for Dependency DAG and Selective Invalidation.
"""

import pytest
from chronos.tools.dag import ExecutionDAG
from chronos.protocol.schemas import CallStatus


def test_selective_invalidation_preserves_reusable_work():
    dag = ExecutionDAG()

    # search_flights node depends on destination = "Delhi"
    node1 = dag.add_node(
        call_id="call_search",
        tool_name="search_flights",
        snapshot_id="v1",
        branch_id="main",
        arguments={"destination": "Delhi", "date": "Tomorrow"},
        slot_bindings={"destination": "Delhi", "date": "Tomorrow"},
    )

    # get_user_profile node depends only on passenger_id = "user_123" (unrelated to destination)
    node2 = dag.add_node(
        call_id="call_profile",
        tool_name="get_user_profile",
        snapshot_id="v1",
        branch_id="main",
        arguments={"user_id": "user_123"},
        slot_bindings={"user_id": "user_123"},
    )

    # Downstream filter node depends on search_flights
    node3 = dag.add_node(
        call_id="call_filter",
        tool_name="filter_flights",
        snapshot_id="v1",
        branch_id="main",
        arguments={"max_price": 10000},
        slot_bindings={"max_price": 10000},
        depends_on=["call_search"],
    )

    # Slot correction: destination changed to Mumbai
    to_invalidate, to_preserve = dag.compute_selective_invalidation(
        modified_slots={"destination": "Mumbai"},
        current_snapshot_id="v2",
    )

    # Invalidation must include call_search AND its downstream call_filter
    assert "call_search" in to_invalidate
    assert "call_filter" in to_invalidate

    # Reusable work (call_profile) MUST be preserved!
    assert "call_profile" in to_preserve
    assert "call_profile" not in to_invalidate
