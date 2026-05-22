"""Server-side Silero VAD gate.

Wraps Pipecat's SileroVADAnalyzer to provide stateful speech/silence detection
on incoming PCM-16 audio frames. Used by the pipeline to:
  1. Suppress STT cost during silence (don't forward non-speech to Deepgram).
  2. Fire `on_speech_start` / `on_speech_end` events for clean endpointing
     and barge-in cancellation — independent of Deepgram's own endpointing.

Audio in: 16kHz mono PCM-16 LE.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Awaitable, Callable

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState

from server.observability.tracer import log


class SileroVAD:
    """Stateful gate. Caller feeds PCM-16 LE @ 16kHz. Emits start/end events."""

    def __init__(
        self,
        sample_rate: int = 16000,
        confidence: float = 0.85,
        min_volume: float = 0.7,
        start_secs: float = 0.8,
        stop_secs: float = 0.6,
    ):
        self.sample_rate = sample_rate
        self.analyzer = SileroVADAnalyzer(
            sample_rate=sample_rate,
            params=VADParams(
                confidence=confidence,
                min_volume=min_volume,
                start_secs=start_secs,
                stop_secs=stop_secs,
            ),
        )
        # SileroVADAnalyzer needs an explicit set_sample_rate call before its
        # internal sample_rate property is populated. Without this, the analyzer
        # silently emits QUIET for every chunk because the window size is wrong.
        self.analyzer.set_sample_rate(sample_rate)
        self.frames_per_chunk = self.analyzer.num_frames_required()  # 512 @ 16k
        self.bytes_per_chunk = self.frames_per_chunk * 2  # int16
        self._buf = bytearray()
        self._prev_state = VADState.QUIET
        self._on_speech_start: Callable[[], Awaitable[None]] | None = None
        self._on_speech_end: Callable[[], Awaitable[None]] | None = None
        self._lock = asyncio.Lock()

    def on_speech_start(self, cb: Callable[[], Awaitable[None]]) -> None:
        self._on_speech_start = cb

    def on_speech_end(self, cb: Callable[[], Awaitable[None]]) -> None:
        self._on_speech_end = cb

    async def feed(self, audio: bytes) -> bool:
        """Feed raw PCM-16 LE bytes. Returns True if current state is speech.

        Caller can use the return value to decide whether to forward audio to STT.
        """
        async with self._lock:
            self._buf.extend(audio)
            in_speech_now = self._prev_state in (VADState.SPEAKING, VADState.STARTING)

            while len(self._buf) >= self.bytes_per_chunk:
                chunk = bytes(self._buf[: self.bytes_per_chunk])
                del self._buf[: self.bytes_per_chunk]
                try:
                    state = await self.analyzer.analyze_audio(chunk)
                except Exception as exc:  # noqa: BLE001
                    log.warning("vad.analyze_failed", err=str(exc))
                    continue

                if state != self._prev_state:
                    # Transition detected.
                    if (
                        state in (VADState.SPEAKING, VADState.STARTING)
                        and self._prev_state in (VADState.QUIET, VADState.STOPPING)
                    ):
                        in_speech_now = True
                        if self._on_speech_start:
                            asyncio.create_task(self._on_speech_start())
                    elif (
                        state in (VADState.QUIET, VADState.STOPPING)
                        and self._prev_state in (VADState.SPEAKING, VADState.STARTING)
                    ):
                        if self._on_speech_end:
                            asyncio.create_task(self._on_speech_end())
                        in_speech_now = state == VADState.STOPPING
                    self._prev_state = state

            return in_speech_now
