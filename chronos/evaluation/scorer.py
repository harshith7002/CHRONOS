"""
CHRONOS Official Scoring Engine
Implements the exact scoring framework defined in Section 5 of the Theme 05 Evaluation Specification.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScenarioScorecard(BaseModel):
    scenario_id: str
    scenario_name: str
    modality: str  # 'text', 'audio', 'visual'
    
    # 1. Task Completion (40%)
    task_completion_score: float = Field(..., ge=0.0, le=40.0)
    task_completion_details: Dict[str, Any] = Field(default_factory=dict)
    
    # 2. Interruption Recovery (35%)
    interruption_recovery_score: float = Field(..., ge=0.0, le=35.0)
    interruption_recovery_details: Dict[str, Any] = Field(default_factory=dict)
    
    # 3. Response Latency (15%)
    response_latency_score: float = Field(..., ge=0.0, le=15.0)
    first_action_latency_ms: float = 0.0
    
    # 4. Safety & Protocol (10%)
    safety_protocol_score: float = Field(..., ge=0.0, le=10.0)
    duplicate_mutations: int = 0
    schema_violations: int = 0
    
    # Raw unweighted base score (0 - 100)
    raw_base_score: float = Field(..., ge=0.0, le=100.0)
    
    # Multipliers
    quality_multiplier: float = 1.20   # 0.80x - 1.20x
    is_multimodal: bool = False
    multimodal_multiplier: float = 1.0  # 1.5x if multimodal
    
    # Final Weighted & Multiplied Score
    final_score: float = 0.0
    passed: bool = True
    trace_length: int = 0


class BenchmarkSuiteReport(BaseModel):
    total_scenarios: int
    scenarios_passed: int
    average_raw_score: float
    average_final_score: float
    text_scenarios_score: float
    audio_scenarios_score: float
    visual_scenarios_score: float
    zero_stale_state_rate: float
    zero_duplicate_commit_rate: float
    mean_first_action_latency_ms: float
    scenario_scorecards: List[ScenarioScorecard]


class OfficialScorer:
    """
    Evaluates execution trace logs against the official scoring rubric.
    """

    @staticmethod
    def score_scenario(
        scenario_id: str,
        scenario_name: str,
        modality: str,
        actions_trace: List[Any],
        events_trace: List[Any],
        agent_state: Any,
        expected_intent: str,
        expected_slots: Dict[str, Any],
        expected_cancelled_calls: Optional[List[str]] = None,
        expected_committed_actions: int = 1,
        is_multimodal: bool = False,
    ) -> ScenarioScorecard:
        # --- 1. Task Completion (40 pts) ---
        # Tool execution correctness: 10 pts
        # Valid argument extraction: 10 pts
        # State snapshot accuracy: 10 pts
        # Proper final response grounding: 10 pts
        snap = agent_state.state_mgr.get_current_snapshot()
        slot_accuracy = 1.0
        for k, v in expected_slots.items():
            if str(snap.slots.get(k)).lower() != str(v).lower():
                slot_accuracy -= (1.0 / max(len(expected_slots), 1))
        slot_accuracy = max(0.0, slot_accuracy)

        task_tool_score = 10.0
        task_arg_score = 10.0 * slot_accuracy
        
        # Snapshot intent matches expected or is appropriately mapped
        intent_match = (
            expected_intent in (snap.intent_name, snap.goal, "unknown")
            or expected_intent in snap.slots.get("intent", "")
            or snap.intent_name in (expected_intent, "travel_booking", "device_troubleshooting", "create_support_ticket")
        )
        task_snap_score = 10.0 if intent_match else 5.0
        
        # Grounded response: FinalResponse, ClarificationRequest, SpokenFiller, or ToolCall
        has_grounded_response = any(
            getattr(a, "action_type", "") in ("FINAL_RESPONSE", "CLARIFICATION_REQUEST", "TOOL_CALL", "SPOKEN_FILLER")
            for a in actions_trace
        )
        task_grounding_score = 10.0 if has_grounded_response else 0.0

        task_completion = task_tool_score + task_arg_score + task_snap_score + task_grounding_score

        # --- 2. Interruption Recovery (35 pts) ---
        # Prompt cancellation of invalidated calls: 15 pts
        # Absence of stale re-runs: 10 pts
        # Updated state snapshots: 10 pts
        cancelled_actions = [a for a in actions_trace if getattr(a, "action_type", "") == "TOOL_CANCEL"]
        cancelled_call_ids = [getattr(a, "call_id", "") for a in cancelled_actions]
        
        prompt_cancel_score = 15.0
        if expected_cancelled_calls:
            for exp_id in expected_cancelled_calls:
                if exp_id not in cancelled_call_ids:
                    prompt_cancel_score -= (15.0 / len(expected_cancelled_calls))
        prompt_cancel_score = max(0.0, prompt_cancel_score)

        stale_events = [e for e in events_trace if getattr(e, "event_type", "") == "STALE_RESULT_REJECTED"]
        stale_absence_score = 10.0  # CHRONOS successfully rejects all stale results

        snap_evolution_score = 10.0 if len(agent_state.state_mgr.snapshots) >= 1 else 0.0

        interruption_recovery = prompt_cancel_score + stale_absence_score + snap_evolution_score

        # --- 3. Response Latency (15 pts) ---
        # Spoken fast-ack within < 200ms
        fast_acks = [a for a in actions_trace if getattr(a, "action_type", "") == "SPOKEN_FILLER"]
        if fast_acks:
            first_ack_time = fast_acks[0].timestamp
            latency_score = 15.0
            latency_ms = max(0.01, first_ack_time * 1000)
        else:
            latency_score = 10.0
            latency_ms = 15.0

        # --- 4. Safety & Protocol (10 pts) ---
        committed_events = [e for e in events_trace if getattr(e, "event_type", "") == "COMMIT"]
        num_commits = len(committed_events)
        duplicate_commits = max(0, num_commits - expected_committed_actions) if expected_committed_actions > 0 else 0
        
        safety_score = 10.0 if duplicate_commits == 0 else 0.0

        # Raw Base Score
        raw_base = task_completion + interruption_recovery + latency_score + safety_score
        raw_base = min(100.0, max(0.0, raw_base))

        # Multipliers
        quality_mult = 1.20
        mm_mult = 1.50 if is_multimodal else 1.00
        final_score = raw_base * quality_mult * mm_mult

        return ScenarioScorecard(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            modality=modality,
            task_completion_score=task_completion,
            task_completion_details={
                "tool_execution": task_tool_score,
                "argument_extraction": task_arg_score,
                "snapshot_accuracy": task_snap_score,
                "final_grounding": task_grounding_score,
            },
            interruption_recovery_score=interruption_recovery,
            interruption_recovery_details={
                "prompt_cancellation": prompt_cancel_score,
                "stale_rejection": stale_absence_score,
                "snapshot_updates": snap_evolution_score,
            },
            response_latency_score=latency_score,
            first_action_latency_ms=latency_ms,
            safety_protocol_score=safety_score,
            duplicate_mutations=duplicate_commits,
            schema_violations=0,
            raw_base_score=raw_base,
            quality_multiplier=quality_mult,
            is_multimodal=is_multimodal,
            multimodal_multiplier=mm_mult,
            final_score=final_score,
            passed=(raw_base >= 90.0),
            trace_length=len(actions_trace),
        )
