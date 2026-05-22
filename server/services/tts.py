"""Deepgram Aura-2 TTS client with per-language span routing.

Inline `<en>...</en>` and `<es>...</es>` tags split the text. English spans go to
the English narrator voice; Spanish spans go to the persona's native Spanish
voice. This means lesson explanations sound like a native English speaker
explaining Spanish, with target words pronounced correctly by a Spanish voice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from server.config import SETTINGS
from server.curriculum.loader import Curriculum
from server.observability.tracer import log

DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"
TAG_RE = re.compile(r"<(es|en|hi)>(.*?)</\1>", re.DOTALL)


@dataclass
class TTSChunk:
    audio: bytes
    text: str
    voice: str


def _split_by_lang(text: str, default_lang: str) -> list[tuple[str, str]]:
    """Walk the text and produce (lang, span) pairs. Untagged text gets the
    `default_lang` (which for our curriculum is "es")."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in TAG_RE.finditer(text):
        pre = text[pos : m.start()].strip()
        if pre:
            out.append((default_lang, pre))
        out.append((m.group(1), m.group(2).strip()))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        out.append((default_lang, tail))
    return out or [(default_lang, text.strip())]


def _voice_for(curriculum: Curriculum, persona_key: str, lang: str) -> str:
    """Pick the right Aura voice for a language span."""
    if lang == "en":
        narrator = curriculum.voice.personas.get("english_narrator")
        if narrator:
            return narrator.voice_id
    # Spanish (or default): use the active persona's voice.
    persona = curriculum.voice.personas.get(persona_key)
    if persona is None:
        persona = next(iter(curriculum.voice.personas.values()))
    return persona.voice_id


async def _speak_span(text: str, voice: str) -> AsyncIterator[TTSChunk]:
    url = f"{DEEPGRAM_SPEAK_URL}?model={voice}&encoding=mp3"
    headers = {
        "Authorization": f"Token {SETTINGS.deepgram_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    log.warning(
                        "tts.aura.http_error",
                        status=r.status_code,
                        body=body[:200].decode("utf-8", errors="replace"),
                        voice=voice,
                    )
                    return
                async for chunk in r.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield TTSChunk(audio=chunk, text=text, voice=voice)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        log.warning("tts.aura.network", err=str(exc), voice=voice)
    except Exception as exc:  # noqa: BLE001
        log.error("tts.aura.failed", err=str(exc), voice=voice)


async def stream_tts(
    text: str,
    curriculum: Curriculum,
    persona_key: str,
) -> AsyncIterator[TTSChunk]:
    """Yield MP3 chunks for `text`, switching voices per language tag."""
    default_lang = curriculum.voice.language_code  # "es"
    spans = _split_by_lang(text, default_lang)
    for lang, segment in spans:
        clean = re.sub(r"<[^>]+>", " ", segment).strip()
        if not clean:
            continue
        voice = _voice_for(curriculum, persona_key, lang)
        async for chunk in _speak_span(clean, voice):
            yield chunk


async def synthesize_to_bytes(
    text: str, curriculum: Curriculum, persona_key: str
) -> bytes:
    """Convenience: collect entire audio response as bytes."""
    buf = bytearray()
    async for chunk in stream_tts(text, curriculum, persona_key):
        buf.extend(chunk.audio)
    return bytes(buf)
