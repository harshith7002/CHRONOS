"""
CHRONOS Evaluation & Replay Harness
Deterministic scenario runner, failure injector, chained execution tester, and adversarial verification.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from chronos.protocol.events import Event, EventType
from chronos.protocol.schemas import CallStatus
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.evaluation.metrics import MetricsCollector, EvaluationReport
from chronos.perception.grounding import VisualScene, VisualObject, MultimodalGrounder


class ScriptedAction(BaseModel):
    virtual_time: float
    action_type: str  # 'USER_INPUT', 'INJECT_STALE', 'ASSERT_STATE', 'STEP_TIME'
    payload: Dict[str, Any] = Field(default_factory=dict)


class ScenarioSpecification(BaseModel):
    name: str
    description: str
    actions: List[ScriptedAction]


class ReplayHarness:
    """
    Executes scripted scenarios and verifies invariants.
    """

    def __init__(self, agent: Optional[ChronosAgent] = None):
        self.clock = VirtualClock(initial_time=0.0, mode="stepped")
        self.agent = agent or ChronosAgent(clock=self.clock)

    def run_default_demo_scenario(self) -> EvaluationReport:
        """
        Canonical travel booking interruption and stale injection scenario.
        """
        self.agent.reset()
        
        # 1. t = 0.0: User starts intent for Delhi
        res1 = self.agent.process_user_input("Find me a flight to Delhi tomorrow morning under 10000")
        assert res1["snapshot_id"] == "v1", f"Expected v1, got {res1['snapshot_id']}"

        # 2. t = 0.1: Advance time slightly (Delhi search is in flight)
        self.agent.step_time(0.1)

        # 3. t = 0.15: User interrupts: "Actually Mumbai"
        res2 = self.agent.process_user_input("Actually Mumbai")
        assert res2["snapshot_id"] == "v2", f"Expected v2, got {res2['snapshot_id']}"

        # 4. t = 0.2: Inject old Delhi result late
        stale_res = self.agent.force_inject_stale_result(
            call_id="call_delhi_old",
            origin_snapshot_id="v1",
            tool_name="search_flights",
            output=[{"flight_id": "DEL-999", "price": 5000, "dest": "Delhi"}],
        )
        assert stale_res.status == CallStatus.STALE_REJECTED, "Expected stale result to be rejected"

        # 5. t = 0.5: Advance time to allow Mumbai search on v2 to complete
        self.agent.step_time(0.4)

        # 6. t = 0.6: User says "Book the cheapest one"
        res3 = self.agent.process_user_input("Book the cheapest one")
        
        # 7. t = 0.7: User confirms booking
        res4 = self.agent.process_user_input("Yes, please confirm and book")
        assert res4.get("success") is True, f"Commit failed: {res4.get('errors')}"

        events = self.agent.event_log.get_all()
        return MetricsCollector.evaluate_trace(events)

    def run_chained_dag_invalidation_scenario(self) -> Dict[str, Any]:
        """
        Scenario 2: Chained Execution Invalidation
        SEARCH -> FILTER -> SELECT -> BOOK
        When slot changes, verify full cascade invalidation while preserving independent state.
        """
        self.agent.reset()
        
        # 1. Setup v1 with full DAG chain
        self.agent.process_user_input("Find flights to Delhi under 10000") # v1
        call_search_v1 = self.agent.scheduler.get_active_calls()[0].call_id

        # Add chained filter and select nodes on DAG
        self.agent.dag.add_node(
            call_id="call_filter_v1",
            tool_name="filter_flights",
            snapshot_id="v1",
            branch_id="main",
            arguments={"max_price": 10000},
            slot_bindings={"destination": "Delhi", "max_price": 10000},
            depends_on=[call_search_v1],
        )
        self.agent.dag.add_node(
            call_id="call_select_v1",
            tool_name="select_flight",
            snapshot_id="v1",
            branch_id="main",
            arguments={"criterion": "cheapest"},
            slot_bindings={"destination": "Delhi"},
            depends_on=["call_filter_v1"],
        )

        # 2. User interrupts: "Actually Mumbai"
        interruption_res = self.agent.process_user_input("Actually Mumbai") # v2
        
        # Verify selective invalidation:
        to_invalidate, to_preserve = self.agent.dag.compute_selective_invalidation(
            modified_slots={"destination": "Mumbai"},
            current_snapshot_id="v2",
        )

        assert call_search_v1 in to_invalidate, "search(v1) must be invalidated"
        assert "call_filter_v1" in to_invalidate, "downstream filter(v1) must be invalidated"
        assert "call_select_v1" in to_invalidate, "downstream select(v1) must be invalidated"

        # Advance time to allow Mumbai search to complete on v2
        self.agent.step_time(0.5)

        return {
            "status": "ok",
            "invalidated_nodes": list(to_invalidate),
            "preserved_nodes": list(to_preserve),
            "active_calls_v2": [c.call_id for c in self.agent.scheduler.get_active_calls()],
            "current_snapshot": self.agent.state_mgr.current_snapshot_id,
        }

    def run_adversarial_stale_booking_injection_scenario(self) -> Dict[str, Any]:
        """
        Scenario 3: Adversarial Stale Result Injection into Booking Chain
        Simulates an attacker/out-of-order system trying to force an old v1 result to trigger booking on v2.
        """
        self.agent.reset()
        
        # 1. Start intent on v1 (Delhi)
        self.agent.process_user_input("Find flights to Delhi")
        
        # 2. User changes to Mumbai on v2
        self.agent.process_user_input("Actually Mumbai")
        assert self.agent.state_mgr.current_snapshot_id == "v2"

        # 3. Adversary attempts to force a fake prepared booking token pointing to old v1 snapshot
        fake_token = self.agent.commit_controller.prepare_action(
            tool_name="book_flight",
            arguments={"flight_id": "DEL-MALICIOUS-999", "passenger_name": "Attacker"},
            snapshot_id="v1",  # STALE SNAPSHOT!
        )

        # 4. Confirm the fake token
        self.agent.commit_controller.confirm_action(fake_token.token_id, confirmed=True)

        # 5. Attempt commit -> MUST BE BLOCKED BY COMMIT CONTROLLER
        success, call, errors = self.agent.commit_controller.commit(fake_token.token_id)
        
        assert success is False, "Commit of stale token must fail"
        assert any("stale snapshot" in err.lower() for err in errors), f"Expected stale snapshot rejection error, got: {errors}"
        assert call is None, "Irreversible tool call must NEVER be dispatched for stale snapshot"

        return {
            "status": "blocked",
            "errors": errors,
            "commit_prevented": True,
            "token_state": fake_token.state.value,
        }

    def run_multimodal_vision_correction_scenario(self) -> Dict[str, Any]:
        """
        Scenario 4: Multimodal Grounding & Evidence Revision
        Vision scene detects red light -> sets critical diagnostic purge.
        User clarifies verbally -> multimodal evidence corrected & purge cancelled.
        """
        self.agent.reset()

        # 1. Camera scene input
        scene = VisualScene(
            scene_id="cam_01",
            timestamp=0.0,
            detected_objects=[
                VisualObject(object_id="led_1", label="flashing_red_indicator", attributes={"color": "red"})
            ],
        )

        # Initial intent setup based on visual symptom
        initial_slots = MultimodalGrounder.resolve_multimodal_correction(
            scene=scene,
            user_utterance="The red light is flashing, check for overheating",
            current_slots={},
        )
        self.agent.state_mgr.create_new_snapshot(timestamp=0.0, slot_updates=initial_slots) # v1

        # Dispatch diagnostic purge on v1
        self.agent.scheduler.dispatch(
            tool_name="search_flights",  # simulated diagnostic task
            arguments={"destination": "coolant_purge"},
            snapshot_id="v1",
            slot_inputs={"indicator_type": "temp_warning"},
        )
        active_before = len(self.agent.scheduler.get_active_calls())
        assert active_before == 1

        # 2. User voice correction: "No, that's actually the power LED indicator."
        corrected_slots = MultimodalGrounder.resolve_multimodal_correction(
            scene=scene,
            user_utterance="No, that's actually the power LED indicator.",
            current_slots=initial_slots,
        )

        interruption_res = self.agent.process_user_input("No, that's actually the power LED indicator") # v2
        
        # Diagnostic purge from v1 cancelled
        cancelled = self.agent.scheduler.get_cancelled_calls()
        assert len(cancelled) >= 1, "Diagnostic tool on v1 must be cancelled"

        return {
            "status": "corrected",
            "initial_slots": initial_slots,
            "corrected_slots": corrected_slots,
            "cancelled_tools_count": len(cancelled),
            "final_snapshot": self.agent.state_mgr.current_snapshot_id,
        }
