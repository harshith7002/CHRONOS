"""
CHRONOS Protocol Messages
Inter-module messaging, perception packets, and fast-path signals.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from chronos.protocol.events import InterruptionLevel


class UserMessage(BaseModel):
    text: str
    timestamp: float
    is_partial: bool = False
    source: str = "text"  # 'text', 'asr', 'multimodal'
    confidence: float = 1.0


class FastAckSignal(BaseModel):
    level: InterruptionLevel
    ack_text: Optional[str] = None
    target_action: Optional[str] = None
    immediate_cancel: bool = False
    timestamp: float


class AgentResponse(BaseModel):
    response_id: str
    snapshot_id: str
    text: str
    is_provisional: bool = False
    requires_confirmation: bool = False
    confirmation_payload: Optional[Dict[str, Any]] = None
    timestamp: float
