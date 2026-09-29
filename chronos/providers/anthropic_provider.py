"""
Anthropic Claude Provider implementation.
"""

from __future__ import annotations
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from chronos.providers.base import BaseLLMProvider, LLMMessage, ProviderConfig, StreamChunk


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude 3.5 / 3.7 Sonnet streaming connector.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig())
        self.api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.api_base = self.config.api_base or "https://api.anthropic.com/v1"

    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            if self.config.extra_headers:
                headers.update(self.config.extra_headers)

            system_prompt = ""
            formatted_messages = []
            for m in messages:
                if m.role == "system":
                    system_prompt += m.content + "\n"
                else:
                    formatted_messages.append({"role": m.role, "content": m.content})

            payload: Dict[str, Any] = {
                "model": self.config.model_name or "claude-3-5-sonnet-20241022",
                "messages": formatted_messages,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "stream": True,
            }
            if system_prompt:
                payload["system"] = system_prompt.strip()
            if tools:
                payload["tools"] = tools

            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST", f"{self.api_base.rstrip('/')}/messages", headers=headers, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        yield StreamChunk(delta_text=f"[Anthropic Error: {resp.status_code} - {err_text.decode('utf-8', errors='ignore')}]")
                        return

                    async for line in resp.aiter_lines():
                        if cancellation_token and getattr(cancellation_token, "is_cancelled", False):
                            break
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        try:
                            event_data = json.loads(data_str)
                            event_type = event_data.get("type")
                            if event_type == "content_block_delta":
                                delta = event_data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield StreamChunk(delta_text=delta.get("text", ""))
                            elif event_type == "message_stop":
                                yield StreamChunk(finish_reason="end_turn")
                        except json.JSONDecodeError:
                            continue
        except ImportError:
            yield StreamChunk(delta_text=f"Simulated Anthropic response for: {messages[-1].content if messages else ''}")

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMMessage:
        full_text = []
        async for chunk in self.stream_chat(messages, tools):
            if chunk.delta_text:
                full_text.append(chunk.delta_text)
        return LLMMessage(role="assistant", content="".join(full_text))
