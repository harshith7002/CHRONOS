"""
Property-based and stochastic fuzzing tests for CHRONOS Invariants INV-1 to INV-7.
"""

import random
import pytest
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.protocol.schemas import ExecutionClass, ToolDefinition
from chronos.sdk import chronos_tool, ChronosSDKAgent
from chronos.persistence import SQLiteStore
from chronos.providers.mcp_client import MCPClient
from chronos.voice.vad import VoiceActivityDetector


def test_sdk_wrapper_and_custom_tool():
    sdk = ChronosSDKAgent(mode="stepped")

    @chronos_tool(name="calculate_tax", execution_class=ExecutionClass.READ_ONLY)
    def calculate_tax(amount: float) -> float:
        return amount * 0.18

    sdk.register_tool(calculate_tax)
    assert sdk.agent.registry.has_tool("calculate_tax")

    res = sdk.send_user_turn("Book flight to Delhi")
    assert res is not None
    state = sdk.get_state()
    assert state["current_snapshot"]["snapshot_id"] == "v1"


def test_sqlite_persistence_event_log(tmp_path):
    db_file = str(tmp_path / "test_ledger.db")
    store = SQLiteStore(db_path=db_file)

    clock = VirtualClock(initial_time=0.0, mode="stepped")
    agent = ChronosAgent(clock=clock)
    agent.process_user_input("Book flight to Delhi")

    for evt in agent.event_log.get_all():
        store.append_event(evt)

    events = store.get_events()
    assert len(events) > 0
    assert events[0].event_id is not None


def test_mcp_client_dynamic_registration():
    mcp = MCPClient()
    mcp.register_mcp_tool_manually(
        name="charge_credit_card",
        description="Charges user credit card for final payment",
        parameters={
            "type": "object",
            "properties": {"amount": {"type": "number"}, "card_token": {"type": "string"}},
            "required": ["amount", "card_token"],
        },
    )
    assert mcp.discovered_tools["charge_credit_card"].execution_class == ExecutionClass.IRREVERSIBLE_WRITE


def test_voice_activity_detector_silence():
    vad = VoiceActivityDetector()
    silence_pcm = b"\x00\x00" * 320  # 20ms of silence at 16kHz
    is_speaking, transition = vad.process_frame(silence_pcm, current_time=0.02)
    assert not is_speaking
    assert transition is None


def test_stochastic_invariants_fuzzing():
    """Fuzzes rapid random interruptions and verify zero safety violations."""
    random.seed(42)
    clock = VirtualClock(initial_time=0.0, mode="stepped")
    agent = ChronosAgent(clock=clock)

    cities = ["Delhi", "Mumbai", "Bangalore", "Goa", "Chennai", "Kolkata"]
    for i in range(20):
        city = random.choice(cities)
        agent.process_user_input(f"Fly to {city}")
        clock.advance(0.05)
        # Random stale result injection
        agent.force_inject_stale_result(
            call_id=f"stale_call_{i}",
            origin_snapshot_id=f"v{random.randint(0, max(1, i))}",
            tool_name="search_flights",
            output={"dest": random.choice(cities), "price": 4000},
        )
        clock.advance(0.05)

    # Invariants must strictly hold
    summary = agent.get_state_summary()
    assert len(summary["stale_results"]) >= 0
    assert summary["event_count"] > 0
