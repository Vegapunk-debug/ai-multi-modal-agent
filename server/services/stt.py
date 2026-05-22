"""Deepgram streaming STT wrapper (multilingual code-switch).

Why Deepgram: Nova-3 supports multi-language detection in one stream (great for
EN/ES/HI code-switching), $200 free credit covers 200+ hours of prototype use,
TTFB under 300ms for interim results.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import AsyncIterator, Callable

import websockets

from server.config import SETTINGS
from server.observability.tracer import log

DEEPGRAM_WS = "wss://api.deepgram.com/v1/listen"


@dataclass
class STTEvent:
    text: str
    is_final: bool
    confidence: float
    language: str | None = None


class DeepgramStream:
    """Bidirectional WebSocket to Deepgram. Caller feeds PCM16 audio, gets transcripts."""

    def __init__(
        self,
        api_key: str,
        languages: list[str] | None = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
    ):
        self.api_key = api_key
        self.languages = languages or ["multi"]
        self.sample_rate = sample_rate
        self.encoding = encoding
        self._ws = None
        self._recv_task: asyncio.Task | None = None
        self._listeners: list[Callable[[STTEvent], None]] = []

    def on_event(self, cb: Callable[[STTEvent], None]) -> None:
        self._listeners.append(cb)

    async def connect(self) -> None:
        # Deepgram accepts language=multi (code-switch) OR a single ISO code.
        # Multi-element hint lists imply code-switching → use "multi".
        if "multi" in self.languages or len(self.languages) > 1:
            lang_param = "multi"
        else:
            lang_param = self.languages[0]
        # `smart_format` and `punctuate` are not supported on multi; drop them there.
        formatting = "" if lang_param == "multi" else "&smart_format=true&punctuate=true"
        # endpointing=400ms — Deepgram waits 400ms of silence before producing
        # an is_final transcript. Combined with our 200ms server debounce,
        # total post-silence wait is ~600ms. Snappy but tolerant of micro-pauses.
        params = (
            f"?model={SETTINGS.stt_model}&language={lang_param}"
            f"&encoding={self.encoding}&sample_rate={self.sample_rate}"
            f"&interim_results=true&endpointing=400{formatting}"
        )
        url = DEEPGRAM_WS + params
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {self.api_key}"},
            max_size=None,
        )
        self._recv_task = asyncio.create_task(self._recv_loop())
        log.info("stt.connected", model=SETTINGS.stt_model, langs=self.languages)

    async def send_audio(self, pcm16: bytes) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(pcm16)
        except websockets.ConnectionClosed:
            log.warning("stt.send_after_close")

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except websockets.ConnectionClosed:
                pass
            await self._ws.close()
        if self._recv_task:
            self._recv_task.cancel()

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                if msg.get("type") != "Results":
                    continue
                channel = msg.get("channel", {})
                alts = channel.get("alternatives", [])
                if not alts:
                    continue
                text = alts[0].get("transcript", "")
                conf = alts[0].get("confidence", 0.0)
                is_final = msg.get("is_final", False)
                lang = (alts[0].get("languages") or [None])[0]
                if not text and not is_final:
                    continue
                event = STTEvent(
                    text=text, is_final=is_final, confidence=conf, language=lang
                )
                for cb in self._listeners:
                    try:
                        cb(event)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("stt.cb_error", err=str(exc))
        except websockets.ConnectionClosed:
            log.info("stt.connection_closed")
        except asyncio.CancelledError:
            pass
