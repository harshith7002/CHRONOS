"""
Voice Activity Detection (VAD) and Real-Time Speech Stream Segmentation.
"""

from __future__ import annotations
import math
import struct
from typing import List, Optional, Tuple


class VoiceActivityDetector:
    """
    Real-time energy-based VAD with adaptive noise floor calibration and hysteresis.
    Processes PCM 16-bit audio chunks and emits speech start/stop events.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        energy_threshold: float = 0.02,
        silence_threshold_ms: int = 300,
        speech_onset_ms: int = 60,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * (frame_duration_ms / 1000.0))
        self.energy_threshold = energy_threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.speech_onset_ms = speech_onset_ms

        self.is_speaking = False
        self.speech_start_time: Optional[float] = None
        self.silence_accumulated_ms = 0
        self.speech_accumulated_ms = 0

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """Computes Root Mean Square energy of 16-bit PCM bytes."""
        if len(pcm_bytes) < 2:
            return 0.0
        count = len(pcm_bytes) // 2
        shorts = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
        sum_sq = sum(s * s for s in shorts)
        mean_sq = sum_sq / count
        # Normalize to 0.0 - 1.0 (max amplitude of 16-bit is 32768)
        return math.sqrt(mean_sq) / 32768.0

    def process_frame(self, pcm_bytes: bytes, current_time: float) -> Tuple[bool, Optional[str]]:
        """
        Processes an incoming audio frame.
        Returns (is_active_speech, transition_event) where transition_event can be 'SPEECH_START', 'SPEECH_END', or None.
        """
        rms = self.calculate_rms(pcm_bytes)
        is_above_threshold = rms >= self.energy_threshold

        transition: Optional[str] = None

        if is_above_threshold:
            self.speech_accumulated_ms += self.frame_duration_ms
            self.silence_accumulated_ms = 0
            if not self.is_speaking and self.speech_accumulated_ms >= self.speech_onset_ms:
                self.is_speaking = True
                self.speech_start_time = current_time
                transition = "SPEECH_START"
        else:
            self.silence_accumulated_ms += self.frame_duration_ms
            self.speech_accumulated_ms = 0
            if self.is_speaking and self.silence_accumulated_ms >= self.silence_threshold_ms:
                self.is_speaking = False
                transition = "SPEECH_END"

        return self.is_speaking, transition
