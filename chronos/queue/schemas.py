"""
CHFONOS Dual-Queue Interface Schemas
Defines structured Input and Output queue messages as specified in the Theme 05 Evaluation Contract.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import uuid


class InputEventType(str, Enum):
    TRANSCRIBED_TEXT = "TRANSCRIBED_TEXT"
    RAW_AUDIO = "RAW_AUDIO"
    VIDEO_FRAME = "VIDEO_FRAME"
    INTERRUPTION_SIGNAL = "INTERRUPTION_SIGNAL"
    TOOL_RESULT = "TOOL_RESULT"
    TOOL_MANIFEST = "TOOL_MANIFEST"


class OutputActionType(str, Enum):
    SPOKEN_FILLER = "SPOKEN_FILLER"
    TOOL_CALL = "TOOL_CALL"
    TOOL_CANCEL = "TOOL_CANCEL"
    CLARIFICATION_REQUEST = "CLARIFICATION_REQUEST"
    FINAL_RESPONSE = "FINAL_RESPONSE"


# ==========================================================================
# 3.1 INPUT STREAM CONTRACT
# ==========================================================================

class TranscribedTextChunk(BaseModel):
    event_type: InputEventType = InputEventType.TRANSCRIBED_TEXT
    text: str
    end_of_turn: bool = True
    confidence: float = 1.0
    timestamp: float


class RawAudioClip(BaseModel):
    event_type: InputEventType = InputEventType.RAW_AUDIO
    audio_data: Union[bytes, str] = Field(default=b"")
    format: str = "WAV"
    sample_rate: int = 16000
    duration: float = 0.5
    transcription: Optional[str] = None
    timestamp: float


class VideoFrame(BaseModel):
    event_type: InputEventType = InputEventType.VIDEO_FRAME
    frame_data: Union[bytes, str] = Field(default=b"")
    format: str = "PNG"
    detected_objects: List[Dict[str, Any]] = Field(default_factory=list)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float


class InterruptionSignal(BaseModel):
    event_type: InputEventType = InputEventType.INTERRUPTION_SIGNAL
    reason: str = "user_barge_in"
    source: str = "audio_vad"
    timestamp: float


class ToolResultEvent(BaseModel):
    event_type: InputEventType = InputEventType.TOOL_RESULT
    call_id: str
    tool_name: str
    snapshot_id: str
    output: Optional[Any] = None
    error: Optional[str] = None
    timestamp: float


class ScenarioToolManifest(BaseModel):
    event_type: InputEventType = InputEventType.TOOL_MANIFEST
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: float


InputEvent = Union[
    TranscribedTextChunk,
    RawAudioClip,
    VideoFrame,
    InterruptionSignal,
    ToolResultEvent,
    ScenarioToolManifest,
]


# =========================================================================
# 3.1 OUTPUT STREAM CONTRACT
# =========================================================================

class SpokenFillerAction(BaseModel):
    action_type: OutputActionType = OutputActionType.SPOKEN_FILLER
    text: str
    filler_type: str = "fast_ack"
    snapshot_id: str = "v0"
    timestamp: float


class ToolCallAction(BaseModel):
    action_type: OutputActionType = OutputActionType.TOOL_CALL
    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    snapshot_id: str
    is_state_modifying: bool = False
    idempotency_key: Optional[str] = None
    timestamp: float


class ToolCancelAction(BaseModel):
    action_type: OutputActionType = OutputActionType.TOOL_CANCEL
    call_id: str
    reason: str
    snapshot_id: str
    timestamp: float


class ClarificationRequestAction(BaseModel):
    action_type: OutputActionType = OutputActionType.CLARIFICATION_REQUEST
    question: str
    ambiguous_slots: List[str] = Field(default_factory=list)
    snapshot_id: str
    timestamp: float


class FinalResponseAction(BaseModel):
    action_type: OutputActionType = OutputActionType.FINAL_RESPONSE
    text: str
    snapshot_id: str
    intent: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float


OutputAction = Union[
    SpokenFillerAction,
    ToolCallAction,
    ToolCancelAction,
    ClarificationRequestAction,
    FinalResponseAction,
]
