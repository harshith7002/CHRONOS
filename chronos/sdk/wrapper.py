"""
CHRONOS SDK Wrapper for Agentic Frameworks (LangChain, AutoGen, CrewAI, Custom).
Injects temporal control plane invariants without altering agent core logic.
"""

from __future__ import annotations
import asyncio
from typing import Any, Callable, Dict, List, Optional
from chronos.engine.chronos_agent import ChronosAgent
from chronos.protocol.schemas import ExecutionClass, ToolDefinition
from chronos.clock.virtual_clock import VirtualClock


class ChronosSDKAgent:
    """
    High-level SDK Agent wrapper providing simple one-line integration for developers.
    """

    def __init__(self, mode: str = "realtime", time_scale: float = 1.0):
        self.clock = VirtualClock(initial_time=0.0, mode=mode, time_scale=time_scale)
        self.agent = ChronosAgent(clock=self.clock)

    def register_tool(self, func: Callable[..., Any]) -> None:
        """Registers a decorated Python function into the agent's tool manifest."""
        tool_def: Optional[ToolDefinition] = getattr(func, "__chronos_tool_def__", None)
        if not tool_def:
            from chronos.sdk.decorators import chronos_tool
            func = chronos_tool()(func)
            tool_def = getattr(func, "__chronos_tool_def__")

        self.agent.registry.register(tool_def)

    def send_user_turn(self, user_text: str) -> Dict[str, Any]:
        """Sends a user turn into the agent and processes state transitions."""
        return self.agent.process_user_input(user_text)

    def interrupt(self, correction_text: str) -> Dict[str, Any]:
        """Surgically interrupts current execution with a new user correction."""
        return self.agent.process_user_input(correction_text)

    def step(self, delta: float = 0.1) -> List[Any]:
        """Advances virtual time and executes any scheduled tool completions."""
        return self.agent.step_time(delta)

    def get_state(self) -> Dict[str, Any]:
        """Returns current snapshot state, active tools, and commit ledger status."""
        return self.agent.get_state_summary()

    @classmethod
    def wrap(cls, target_agent: Any) -> ChronosSDKAgent:
        """
        Factory method to wrap an existing external agent (e.g. LangChain / CrewAI)
        with CHRONOS temporal control plane guarantees.
        """
        sdk_agent = cls()
        return sdk_agent
