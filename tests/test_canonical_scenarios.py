"""
Tests for the 9 Canonical Public Scenarios and Dual-Queue Asynchronous Agent.
Verifies 100% compliance with Samsung Theme 05 Evaluation Contract.
"""

import pytest
import asyncio
from chronos.queue.schemas import (
    TranscribedTextChunk,
    RawAudioClip,
    VideoFrame,
    InterruptionSignal,
    ToolResultEvent,
    ScenarioToolManifest,
    SpokenFillerAction,
    ToolCallAction,
    ToolCancelAction,
    FinalResponseAction,
)
from chronos.queue.async_agent import DualQueueAgent
from chronos.evaluation.canonical_scenarios import CanonicalScenarioRunner


@pytest.mark.asyncio
async def test_dual_queue_agent_event_flow():
    agent = DualQueueAgent()
    await agent.start()

    # Feed input text chunk
    await agent.input_queue.put(
        TranscribedTextChunk(
            text="Find flights to Delhi under 10000",
            end_of_turn=True,
            timestamp=0.0,
        )
    )
    await agent.step()

    # Output queue should have received SpokenFillerAction and ToolCallAction
    actions = agent.action_trace
    assert len(actions) >= 1
    assert any(isinstance(a, SpokenFillerAction) for a in actions)
    assert any(isinstance(a, ToolCallAction) for a in actions)

    await agent.stop()


@pytest.mark.asyncio
async def test_all_9_canonical_scenarios_pass_with_perfect_scores():
    report = await CanonicalScenarioRunner.run_all_9_canonical_scenarios()

    assert report.total_scenarios == 9
    assert report.scenarios_passed == 9, f"Only {report.scenarios_passed}/9 passed"
    assert report.zero_stale_state_rate == 1.0
    assert report.zero_duplicate_commit_rate == 1.0
    assert report.average_raw_score >= 95.0, f"Average raw score {report.average_raw_score} < 95.0"
    assert report.average_final_score >= 110.0, f"Average final score {report.average_final_score} < 110.0"

    for sc in report.scenario_scorecards:
        assert sc.passed is True
        assert sc.duplicate_mutations == 0
        assert sc.safety_protocol_score == 10.0
        assert sc.response_latency_score == 15.0
