"""
Unit tests for 4-Stage Commit Controller and Strict Idempotency Deduplication.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.state.branch_manager import TemporalStateManager
from chronos.tools.manifest import create_default_travel_manifest
from chronos.tools.dag import ExecutionDAG
from chronos.tools.scheduler import ToolScheduler
from chronos.commit.idempotency import IdempotencyRegistry
from chronos.commit.commit_controller import CommitController
from chronos.protocol.schemas import CommitState


def test_commit_safety_and_idempotency():
    clock = VirtualClock(mode="stepped")
    log = EventLog()
    state_mgr = TemporalStateManager(log)
    registry = create_default_travel_manifest()
    dag = ExecutionDAG()
    scheduler = ToolScheduler(clock, log, registry, dag)
    idempotency = IdempotencyRegistry()

    controller = CommitController(
        clock=clock,
        event_log=log,
        state_mgr=state_mgr,
        idempotency=idempotency,
        registry=registry,
        scheduler=scheduler,
    )

    # 1. Create snapshot v1 with booking slots
    snap_v1 = state_mgr.create_new_snapshot(
        timestamp=0.0,
        slot_updates={"flight_id": "BOM-101", "passenger_name": "Alice"},
    )

    # 2. Prepare irreversible action (book_flight)
    token = controller.prepare_action(
        tool_name="book_flight",
        arguments={"flight_id": "BOM-101", "passenger_name": "Alice", "amount": 8500},
        snapshot_id="v1",
    )
    assert token.state == CommitState.CONFIRMATION
    assert token.confirmed is False

    # 3. Attempt to commit WITHOUT confirmation -> MUST FAIL
    success, call, errors = controller.commit(token.token_id)
    assert success is False
    assert any("confirmation missing" in err.lower() for err in errors)

    # 4. User provides explicit confirmation
    controller.confirm_action(token.token_id, confirmed=True)
    assert token.confirmed is True

    # 5. Commit with confirmation -> MUST SUCCEED
    success2, call2, errors2 = controller.commit(token.token_id)
    assert success2 is True
    assert call2 is not None

    # 6. Attempt DUPLICATE commit (retry / late arrival) -> MUST BE DEDUPLICATED VIA IDEMPOTENCY KEY
    success3, call3, errors3 = controller.commit(token.token_id)
    assert success3 is True
    assert call3 is None  # Suppressed duplicate execution!
    assert any("duplicate" in err.lower() for err in errors3)
