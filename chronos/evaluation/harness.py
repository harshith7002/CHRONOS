"""
CHRONOS Evaluation & Replay Harness
Deterministic scenario runner, failure injector, and trace verification harness.
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
        Executes the canonical travel booking interruption and stale injection scenario.
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

        # 8. Verify idempotency: duplicate confirmation / retry must not create a duplicate booking
        # Attempt duplicate commit directly
        dup_commit = self.agent.process_user_input("Yes, please confirm and book")

        # Evaluate complete event log
        events = self.agent.event_log.get_all()
        report = MetricsCollector.evaluate_trace(events)
        return report

    def run_scenario(self, spec: ScenarioSpecification) -> EvaluationReport:
        """
        Runs a custom scenario specification with precise timestamps.
        """
        self.agent.reset()
        sorted_actions = sorted(spec.actions, key=lambda a: a.virtual_time)

        for action in sorted_actions:
            # Advance clock to action time
            delta = action.virtual_time - self.clock.now()
            if delta > 0:
                self.agent.step_time(delta)

            if action.action_type == "USER_INPUT":
                text = action.payload.get("text", "")
                self.agent.process_user_input(text)

            elif action.action_type == "INJECT_STALE":
                self.agent.force_inject_stale_result(
                    call_id=action.payload.get("call_id", "stale_call"),
                    origin_snapshot_id=action.payload.get("snapshot_id", "v1"),
                    tool_name=action.payload.get("tool_name", "search_flights"),
                    output=action.payload.get("output", {}),
                )

            elif action.action_type == "STEP_TIME":
                step_val = action.payload.get("delta", 0.1)
                self.agent.step_time(step_val)

        events = self.agent.event_log.get_all()
        return MetricsCollector.evaluate_trace(events)
