"""
CHRONOS LLM Provider Abstraction
Provides unified async streaming, structured tool calling, cancellation support, and token telemetry.
"""

from __future__ import annotations
import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from enum import Enum


class ProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    MOCK = "mock"


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class StreamChunk:
    delta_text: str = ""
    delta_tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage_tokens: Optional[int] = None
    raw_response: Optional[Any] = None


@dataclass
class ProviderConfig:
    provider_type: ProviderType = ProviderType.MOCK
    model_name: str = "mock-agent-v1"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 1024
    extra_headers: Dict[str, str] = field(default_factory=dict)


class BaseLLMProvider(abc.ABC):
    """
    Abstract Base Class for LLM providers integrated into CHRONOS.
    Guarantees interrupt-safe streaming and structured tool call extraction.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abc.abstractmethod
    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streams completions with token deltas and parsed tool calls.
        Must respect cancellation tokens or abort signals immediately.
        """
        pass

    @abc.abstractmethod
    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMMessage:
        """One-shot non-streaming completion."""
        pass
