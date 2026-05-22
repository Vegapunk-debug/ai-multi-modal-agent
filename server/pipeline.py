"""Real-time voice pipeline.

Per-session asyncio orchestrator:
    Browser ⇄ /ws/audio
      → Deepgram STT (streaming, multi-language)
      → Agent.handle_user_turn (LLM + tools + FSM + grader)
      → Edge TTS (streaming MP3)
      → Browser audio

Design notes:
- All ws.send_* calls go through `safe_send_*` which silently no-op once the
  client has disconnected — prevents the noisy stack traces under tear-down.
- The greeting is awaited inline so it isn't cancelled by ambient noise that
  fires before the playback actually starts.
- Barge-in: client emits `user_speech_start` from WebAudio VAD; we cancel the
  in-flight TTS task. Server-side endpointing comes from Deepgram itself.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from server.agent.core import Agent, AgentEvent
from server.config import SETTINGS
from server.curriculum.loader import Curriculum, load_curriculum
from server.db.repo import Repo
from server.observability.metrics import METRICS
from server.observability.tracer import TurnTrace, log
from server.services.llm import make_llm
from server.services.stt import DeepgramStream, STTEvent
from server.services.tts import stream_tts
from server.services.vad import SileroVAD


@dataclass
class SessionContext:
    session_id: str
    user_id: str
    target_lang: str
    curriculum: Curriculum
    agent: Agent
    stt: DeepgramStream
    vad: SileroVAD
    repo: Repo
    pending_event: asyncio.Event = field(default_factory=asyncio.Event)
    tts_task: asyncio.Task | None = None
    tts_start_ts: float | None = None  # When current/last TTS task began
    tts_end_ts: float | None = None  # When the last TTS task finished (for mic gate tail)
    pending_final: str = ""
    interim_buffer: str = ""
    last_user_speech_end_ts: float | None = None
    connected: bool = True
    metrics: dict[str, list[float]] = field(default_factory=lambda: {
        "tts_ttfb_ms": [],
        "end_to_end_ms": [],
    })


# ----- Safe WS senders (no-op once disconnected) -----

async def safe_send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.client_state != WebSocketState.CONNECTED:
        return
    try:
        await ws.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass


async def safe_send_bytes(ws: WebSocket, data: bytes) -> None:
    if ws.client_state != WebSocketState.CONNECTED:
        return
    try:
        await ws.send_bytes(data)
    except (WebSocketDisconnect, RuntimeError):
        pass


# ----- Session construction -----

async def build_session(user_id: str, target_lang: str) -> SessionContext:
    target_lang = target_lang.lower()
    curriculum = load_curriculum(target_lang)
    repo = Repo()
    await repo.init()
    await repo.ensure_user(user_id, target_lang)
    session_id = str(uuid.uuid4())[:12]
    await repo.start_session(session_id, user_id, target_lang)

    llm = make_llm()
    agent = Agent(curriculum=curriculum, llm=llm, repo=repo, user_id=user_id, session_id=session_id)

    stt = DeepgramStream(
        api_key=SETTINGS.deepgram_api_key,
        languages=curriculum.voice.stt_hint,
    )
    await stt.connect()
    # Silero VAD tuned strict (confidence 0.85 + 800ms sustain) so the agent's
    # own TTS coming back through speakers doesn't false-positive into barge-in.
    # Real user speech sustains for >800ms; speaker echo usually dips out.
    vad = SileroVAD(
        sample_rate=16000, confidence=0.85, min_volume=0.7,
        start_secs=0.8, stop_secs=0.6,
    )
    return SessionContext(
        session_id=session_id,
        user_id=user_id,
        target_lang=target_lang,
        curriculum=curriculum,
        agent=agent,
        stt=stt,
        vad=vad,
        repo=repo,
    )


# ----- Main session driver -----

async def run_session(ws: WebSocket, user_id: str, target_lang: str) -> None:
    ctx = await build_session(user_id, target_lang)
    log.info("session.start", session_id=ctx.session_id, lang=ctx.target_lang)

    welcome_persona = ctx.curriculum.voice.personas.get("teacher")
    welcome_name = welcome_persona.name if welcome_persona else "Tutor"
    await safe_send_json(ws, {
        "type": "session_started",
        "session_id": ctx.session_id,
        "target_lang": ctx.target_lang,
        "personas": {k: {"name": p.name, "voice_id": p.voice_id} for k, p in ctx.curriculum.voice.personas.items()},
        "lessons": [{"id": l.id, "title": l.title} for l in ctx.curriculum.lessons],
        "greeting": welcome_name,
    })

    # Bind STT callbacks BEFORE greeting so any user speech during greeting registers.
    # We DEBOUNCE finalized transcripts: if a new final arrives within 600ms of
    # the previous one, the speaker is mid-thought — we extend the wait. Only
    # when 600ms passes with no new final do we fire the agent. This stops the
    # agent from jumping in on natural mid-sentence pauses.
    debounce_handle: dict[str, asyncio.TimerHandle | None] = {"h": None}
    DEBOUNCE_MS = 200

    def fire_agent() -> None:
        debounce_handle["h"] = None
        ctx.pending_event.set()

    # Accept anything Deepgram tags as English. Indian-accented English sometimes
    # mis-classifies as Hindi under multi-lang; we run English-only model now.
    ALLOWED_LANGS = {"en", "es", "hi", None, ""}

    def on_stt(event: STTEvent) -> None:
        if not event.text:
            return
        # Reject transcripts detected as anything other than English or Spanish.
        # Stops random Hindi / Chinese / etc detections from polluting input.
        if event.language and event.language.split("-")[0].lower() not in ALLOWED_LANGS:
            log.info("stt.dropped_lang", lang=event.language, text=event.text[:40])
            return
        log.info("stt.event", is_final=event.is_final, text=event.text[:60], lang=event.language)
        if event.is_final:
            ctx.pending_final += " " + event.text
            ctx.interim_buffer = ""
            ctx.last_user_speech_end_ts = time.perf_counter()
            # Reset debounce — keep waiting for more.
            if debounce_handle["h"] is not None:
                debounce_handle["h"].cancel()
            loop = asyncio.get_event_loop()
            debounce_handle["h"] = loop.call_later(DEBOUNCE_MS / 1000, fire_agent)
            asyncio.create_task(safe_send_json(ws, {
                "type": "transcript",
                "is_final": True,
                "text": event.text.strip(),
                "language": event.language,
                "confidence": event.confidence,
            }))
        else:
            ctx.interim_buffer = event.text
            asyncio.create_task(safe_send_json(ws, {
                "type": "transcript",
                "is_final": False,
                "text": event.text,
            }))

    ctx.stt.on_event(on_stt)

    # --- Barge-in via Silero VAD during TTS ---
    # We only honor VAD speech-start when TTS is actively playing. Otherwise
    # VAD events are noise. When user genuinely interrupts, cancel TTS so they
    # can speak; the agent will respond to their new utterance.
    async def _on_speech_start() -> None:
        if ctx.tts_task and not ctx.tts_task.done():
            # Suppress barge-in for the first 1.5s of TTS — speakers + room
            # acoustics generate enough audio in that window to trick VAD.
            tts_age = time.perf_counter() - (ctx.tts_start_ts or 0)
            if tts_age < 1.5:
                log.info("bargein.suppressed_early", tts_age=round(tts_age, 2))
                return
            log.info("bargein.vad_triggered", session_id=ctx.session_id)
            await cancel_tts_if_speaking(ws, ctx)
            await safe_send_json(ws, {"type": "vad", "speaking": True})

    async def _on_speech_end() -> None:
        await safe_send_json(ws, {"type": "vad", "speaking": False})

    ctx.vad.on_speech_start(_on_speech_start)
    ctx.vad.on_speech_end(_on_speech_end)

    # Inline-await the greeting so VAD ambient noise can't cancel it before the
    # audio actually begins streaming.
    greeting = f"<en>Hi, I'm {welcome_name}. Ready to learn Spanish?</en>"
    await speak(ws, ctx, greeting, "teacher", TurnTrace(ctx.session_id), time.perf_counter())

    # ----- Agent task draining finalized transcripts -----

    async def agent_loop() -> None:
        while ctx.connected:
            try:
                await asyncio.wait_for(ctx.pending_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            ctx.pending_event.clear()
            text = ctx.pending_final.strip()
            ctx.pending_final = ""
            if not text:
                continue
            await cancel_tts_if_speaking(ws, ctx)

            trace = TurnTrace(ctx.session_id)
            t0 = time.perf_counter()
            try:
                async for event in ctx.agent.handle_user_turn(text, trace=trace):
                    await dispatch_event(ws, ctx, event, trace, started_at=t0)
            except Exception as exc:  # noqa: BLE001
                log.error("agent.loop_error", err=str(exc))
                await safe_send_json(ws, {"type": "error", "where": "agent", "err": str(exc)})
            total = round((time.perf_counter() - t0) * 1000, 2)
            ctx.metrics["end_to_end_ms"].append(total)
            METRICS.add("turn_total_ms", total)
            await safe_send_json(ws, {"type": "metrics", "turn_ms": total})

    agent_task = asyncio.create_task(agent_loop())

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"]:
                tts_active = ctx.tts_task and not ctx.tts_task.done()
                if tts_active:
                    # While TTS plays, feed audio to VAD only (NOT to STT) so
                    # the agent's own echo doesn't get transcribed. VAD detects
                    # confident user speech → cancels TTS → mic re-opens.
                    await ctx.vad.feed(msg["bytes"])
                    continue
                # 250ms tail after TTS ends to swallow speaker reverb.
                if ctx.tts_end_ts and (time.perf_counter() - ctx.tts_end_ts) < 0.25:
                    continue
                await ctx.stt.send_audio(msg["bytes"])
            elif "text" in msg and msg["text"]:
                await handle_control_message(ctx, ws, msg["text"])
    except WebSocketDisconnect:
        pass
    finally:
        ctx.connected = False
        agent_task.cancel()
        if ctx.tts_task and not ctx.tts_task.done():
            ctx.tts_task.cancel()
        try:
            await ctx.stt.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await ctx.repo.end_session(ctx.session_id, "client disconnect")
        except Exception:  # noqa: BLE001
            pass
        log.info("session.end", session_id=ctx.session_id)


# ----- Barge-in helper -----

async def cancel_tts_if_speaking(ws: WebSocket, ctx: SessionContext) -> None:
    if ctx.tts_task and not ctx.tts_task.done():
        log.info("bargein.cancel", session_id=ctx.session_id)
        ctx.tts_task.cancel()
        try:
            await ctx.tts_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await safe_send_json(ws, {"type": "tts_cancelled"})


# ----- Control message handler -----

async def handle_control_message(ctx: SessionContext, ws: WebSocket, text: str) -> None:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return
    cmd = msg.get("type")
    if cmd == "user_speech_start":
        # IGNORE client-side VAD trigger. Speakers + mic create an echo loop
        # where TTS audio fires the client VAD and cancels itself.
        # Barge-in is honored only when STT produces a real transcript while
        # TTS is playing (handled in on_stt below).
        return
    elif cmd == "switch_lang":
        new_lang = (msg.get("lang") or "spanish").lower()
        if new_lang == ctx.target_lang:
            return
        await safe_send_json(ws, {"type": "lang_switching", "lang": new_lang})
        new_curriculum = load_curriculum(new_lang)
        ctx.curriculum = new_curriculum
        ctx.target_lang = new_lang
        ctx.agent.curriculum = new_curriculum
        # Reset session state but keep history threadable
        ctx.agent.state = type(ctx.agent.state)()
        await ctx.repo.ensure_user(ctx.user_id, new_lang)
        try:
            await ctx.stt.close()
        except Exception:  # noqa: BLE001
            pass
        ctx.stt = DeepgramStream(
            api_key=SETTINGS.deepgram_api_key,
            languages=new_curriculum.voice.stt_hint,
        )
        await ctx.stt.connect()
        ctx.stt.on_event(lambda e: None)
        await safe_send_json(ws, {"type": "lang_switched", "lang": new_lang})
    elif cmd == "ping":
        await safe_send_json(ws, {"type": "pong", "ts": time.time()})
    elif cmd == "user_text":
        ctx.pending_final += " " + (msg.get("text") or "")
        ctx.interim_buffer = ""
        ctx.last_user_speech_end_ts = time.perf_counter()
        ctx.pending_event.set()
        await safe_send_json(ws, {
            "type": "transcript",
            "is_final": True,
            "text": msg.get("text") or "",
            "language": "en",
            "confidence": 1.0,
        })


# ----- Event dispatch -----

async def dispatch_event(
    ws: WebSocket,
    ctx: SessionContext,
    event: AgentEvent,
    trace: TurnTrace,
    started_at: float,
) -> None:
    if event.kind == "speak":
        await speak(ws, ctx, event.text, event.persona, trace, started_at)
    elif event.kind == "state":
        await safe_send_json(ws, {"type": "state", **event.payload})
    elif event.kind == "tool":
        await safe_send_json(ws, {"type": "tool", **event.payload})
    elif event.kind == "error":
        await safe_send_json(ws, {"type": "error", "msg": event.text, **event.payload})


# ----- TTS speak -----

async def speak(
    ws: WebSocket,
    ctx: SessionContext,
    text: str,
    persona_key: str,
    trace: TurnTrace,
    started_at: float,
) -> None:
    """Stream MP3 audio for `text` to the client. Cancellable for barge-in."""
    if not ctx.connected:
        return

    async def runner():
        persona = ctx.curriculum.voice.personas.get(persona_key)
        await safe_send_json(ws, {
            "type": "tts_start",
            "persona": persona_key,
            "persona_name": persona.name if persona else persona_key,
            "voice_id": persona.voice_id if persona else "",
            "text": text,
        })
        first_chunk_sent = False
        try:
            async for chunk in stream_tts(text, ctx.curriculum, persona_key):
                if not chunk.audio:
                    continue
                if not first_chunk_sent:
                    ttfb = round((time.perf_counter() - started_at) * 1000, 2)
                    ctx.metrics["tts_ttfb_ms"].append(ttfb)
                    METRICS.add("tts_ttfb_ms", ttfb)
                    trace.event("tts.ttfb", ms=ttfb)
                    await safe_send_json(ws, {"type": "tts_ttfb_ms", "ms": ttfb})
                    first_chunk_sent = True
                await safe_send_bytes(ws, chunk.audio)
        except asyncio.CancelledError:
            await safe_send_json(ws, {"type": "tts_cancelled"})
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("tts.stream_error", err=str(exc))
        finally:
            await safe_send_json(ws, {"type": "tts_end"})

    ctx.tts_start_ts = time.perf_counter()
    ctx.tts_task = asyncio.create_task(runner())
    try:
        await ctx.tts_task
    except asyncio.CancelledError:
        pass
    ctx.tts_task = None
    ctx.tts_end_ts = time.perf_counter()
