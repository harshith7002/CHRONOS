"""
Google Gemini & Ollama Local Providers.
"""

from __future__ import annotations
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from chronos.providers.base import BaseLLMProvider, LLMMessage, ProviderConfig, StreamChunk


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini 2.0 Flash / Pro streaming connector.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig())
        self.api_key = self.config.api_key or os.getenv("GEMINI_API_KEY", "")

    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx
            model = self.config.model_name or "gemini-2.0-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={self.api_key}&alt=sse"

            contents = []
            for m in messages:
                role = "user" if m.role in ("user", "system") else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})

            payload: Dict[str, Any] = {"contents": contents}

            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        yield StreamChunk(delta_text=f"[Gemini Error: {resp.status_code} - {err_text.decode('utf-8', errors='ignore')}]")
                        return

                    async for line in resp.aiter_lines():
                        if cancellation_token and getattr(cancellation_token, "is_cancelled", False):
                            break
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        try:
                            data = json.loads(line[6:])
                            candidates = data.get("candidates", [{}])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    if "text" in p:
                                        yield StreamChunk(delta_text=p["text"])
                        except json.JSONDecodeError:
                            continue
        except ImportError:
            yield StreamChunk(delta_text=f"Simulated Gemini response for: {messages[-1].content if messages else ''}")

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMMessage:
        full = []
        async for chunk in self.stream_chat(messages, tools):
            if chunk.delta_text:
                full.append(chunk.delta_text)
        return LLMMessage(role="assistant", content="".join(full))


class OllamaProvider(BaseLLMProvider):
    """
    Ollama / Local vLLM streaming provider.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig())
        self.api_base = self.config.api_base or os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        try:
            import httpx
            payload = {
                "model": self.config.model_name or "llama3.2",
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": True,
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{self.api_base.rstrip('/')}/api/chat", json=payload) as resp:
                    if resp.status_code != 200:
                        yield StreamChunk(delta_text=f"[Ollama Error: {resp.status_code}]")
                        return
                    async for line in resp.aiter_lines():
                        if cancellation_token and getattr(cancellation_token, "is_cancelled", False):
                            break
                        if not line.strip():
                            continue
                        try:
                            parsed = json.loads(line)
                            msg = parsed.get("message", {})
                            delta = msg.get("content", "")
                            yield StreamChunk(delta_text=delta, finish_reason=parsed.get("done_reason"))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            yield StreamChunk(delta_text=f"Local Ollama simulated output for: {messages[-1].content if messages else ''}")

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMMessage:
        full = []
        async for chunk in self.stream_chat(messages, tools):
            if chunk.delta_text:
                full.append(chunk.delta_text)
        return LLMMessage(role="assistant", content="".join(full))
