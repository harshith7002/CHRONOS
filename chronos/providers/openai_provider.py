"""
OpenAI Provider implementation with streaming tool calling and interrupt safety.
"""

from __future__ import annotations
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from chronos.providers.base import BaseLLMProvider, LLMMessage, ProviderConfig, StreamChunk


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI API connector supporting GPT-4o, GPT-4o-mini, and compatible OpenAI endpoints.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig())
        self.api_key = self.config.api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_base = self.config.api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        formatted = []
        for m in messages:
            msg_dict: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                msg_dict["name"] = m.name
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            formatted.append(msg_dict)
        return formatted

    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streams completions from OpenAI. If openai package is not installed, yields mock response safely.
        """
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if self.config.extra_headers:
                headers.update(self.config.extra_headers)

            payload: Dict[str, Any] = {
                "model": self.config.model_name or "gpt-4o-mini",
                "messages": self._convert_messages(messages),
                "temperature": self.config.temperature,
                "stream": True,
            }
            if tools:
                payload["tools"] = tools

            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST", f"{self.api_base.rstrip('/')}/chat/completions", headers=headers, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        yield StreamChunk(delta_text=f"[OpenAI Error: {resp.status_code} - {err_text.decode('utf-8', errors='ignore')}]")
                        return

                    async for line in resp.aiter_lines():
                        if cancellation_token and getattr(cancellation_token, "is_cancelled", False):
                            break
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data_str)
                            choice = parsed.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            tool_calls = delta.get("tool_calls")
                            finish_reason = choice.get("finish_reason")
                            yield StreamChunk(
                                delta_text=content or "",
                                delta_tool_calls=tool_calls,
                                finish_reason=finish_reason,
                                raw_response=parsed,
                            )
                        except json.JSONDecodeError:
                            continue
        except ImportError:
            # Fallback mock generator if httpx not installed
            yield StreamChunk(delta_text=f"Simulated response for: {messages[-1].content if messages else ''}")

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMMessage:
        full_text = []
        all_tool_calls = []
        async for chunk in self.stream_chat(messages, tools):
            if chunk.delta_text:
                full_text.append(chunk.delta_text)
            if chunk.delta_tool_calls:
                all_tool_calls.extend(chunk.delta_tool_calls)
        return LLMMessage(
            role="assistant",
            content="".join(full_text),
            tool_calls=all_tool_calls if all_tool_calls else None,
        )
