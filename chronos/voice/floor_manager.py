"""
CHRONOS Audio Stream Processor and Real-Time Turn-Taking Floor Manager.
Coordinates VAD, interruption debouncing, and ASR token streaming.
"""

from __future__ import annotations
import asyncio
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from chronos.voice.vad import VoiceActivityDetector
from chronos.interruption.debouncer import InterruptionDebouncer
from chronos.protocol.events import InterruptionLevel
from chronos.clock.virtual_clock import VirtualClock


class FloorState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


class VoiceTurnEvent(BaseModel):
    state: FloorState
    timestamp: float
    transcript_delta: str = ""
    is_final: bool = False
    interruption_level: Optional[InterruptionLevel] = None


class VoiceFloorManager:
    """
    Manages the conversational floor, VAD transitions, interruption debouncing,
    and fast path turn-taking responses.
    """

    def __init__(
        self,
        clock: Optional[VirtualClock] = None,
        on_interruption: Optional[Callable[[str, InterruptionLevel], Any]] = None,
        on_final_turn: Optional[Callable[[str], Any]] = None,
    ):
        self.clock = clock or VirtualClock(initial_time=0.0, mode="realtime")
        self.state = FloorState.IDLE
        self.vad = VoiceActivityDetector()
        self.debouncer = InterruptionDebouncer(clock=self.clock, debounce_window_sec=0.25)
        self.on_interruption = on_interruption
        self.on_final_turn = on_final_turn
        self.current_turn_text = ""

        if self.on_final_turn:
            self.debouncer.set_on_flush(lambda msg: self.on_final_turn(msg.text))

    def handle_audio_frame(self, pcm_bytes: bytes, timestamp: float) -> Optional[VoiceTurnEvent]:
        """Processes incoming audio frame and returns state change if any."""
        is_speech, transition = self.vad.process_frame(pcm_bytes, timestamp)
        
        if transition == "SPEECH_START":
            prev_state = self.state
            if self.state == FloorState.SPEAKING:
                self.state = FloorState.INTERRUPTED
                return VoiceTurnEvent(state=self.state, timestamp=timestamp)
            else:
                self.state = FloorState.LISTENING
                return VoiceTurnEvent(state=self.state, timestamp=timestamp)

        elif transition == "SPEECH_END":
            if self.state in (FloorState.LISTENING, FloorState.INTERRUPTED):
                self.state = FloorState.THINKING
                final_text = self.current_turn_text.strip()
                self.current_turn_text = ""
                if final_text and self.on_final_turn:
                    self.on_final_turn(final_text)
                return VoiceTurnEvent(state=self.state, timestamp=timestamp, is_final=True)

        return None

    def feed_asr_token(self, token: str, is_final: bool = False) -> None:
        """
        Feeds streaming ASR token into debouncer.
        """
        self.current_turn_text += (" " if self.current_turn_text else "") + token
        self.debouncer.push_token(token, is_final=is_final)
        
        if self.state in (FloorState.SPEAKING, FloorState.THINKING):
            self.state = FloorState.INTERRUPTED
            if self.on_interruption:
                self.on_interruption(token, InterruptionLevel.LEVEL_1_SLOT_CORRECTION)
