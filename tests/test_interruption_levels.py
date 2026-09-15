"""
Unit tests for the 5-Level Interruption Hierarchy and Debouncing.
"""

import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.state.event_log import EventLog
from chronos.state.branch_manager import TemporalStateManager
from chronos.tools.manifest import create_default_travel_manifest
from chronos.tools.dag import ExecutionDAG
from chronos.tools.scheduler import ToolScheduler
from chronos.interruption.controller import InterruptionController, InterruptionLevel
from chronos.interruption.debouncer import InterruptionDebouncer


def test_interruption_classification_levels():
    clock = VirtualClock()
    log = EventLog()
    state_mgr = TemporalStateManager(log)
    registry = create_default_travel_manifest()
    dag = ExecutionDAG()
    scheduler = ToolScheduler(clock, log, registry, dag)
    controller = InterruptionController(clock, log, state_mgr, dag, scheduler)

    # Level 0: Backchannel
    l0, _ = controller.classify_intent("yeah")
    assert l0 == InterruptionLevel.LEVEL_0
    l0b, _ = controller.classify_intent("okay")
    assert l0b == InterruptionLevel.LEVEL_0

    # Level 1: Slot Correction
    l1, p1 = controller.classify_intent("Actually Mumbai")
    assert l1 == InterruptionLevel.LEVEL_1
    assert p1["slots"]["destination"] == "Mumbai"

    # Level 2: Goal Change
    l2, _ = controller.classify_intent("Don't book it, just show me options")
    assert l2 == InterruptionLevel.LEVEL_2

    # Level 3: Explicit Cancellation
    l3, _ = controller.classify_intent("Stop")
    assert l3 == InterruptionLevel.LEVEL_3

    # Level 4: Irreversible in-flight interruption
    l4, _ = controller.classify_intent("Wait stop", is_in_irreversible_phase=True)
    assert l4 == InterruptionLevel.LEVEL_4


def test_debouncer_coalesces_partial_tokens():
    clock = VirtualClock(mode="stepped")
    debouncer = InterruptionDebouncer(clock, debounce_window_sec=0.2)
    flushed = []
    debouncer.set_on_flush(lambda msg: flushed.append(msg.text))

    # Push streaming tokens rapidly
    debouncer.push_token("Act")
    debouncer.push_token("ually")
    debouncer.push_token("Mum")
    debouncer.push_token("bai")

    assert len(flushed) == 0

    # Advance less than window
    clock.advance(0.1)
    assert len(flushed) == 0

    # Advance past window
    clock.advance(0.15)
    assert len(flushed) == 1
    assert flushed[0] == "Act ually Mum bai"
