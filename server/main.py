"""FastAPI entry: serves WebSocket audio endpoint + health + metrics."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from server.config import SETTINGS
from server.curriculum.loader import load_curriculum
from server.db.repo import Repo
from server.observability.metrics import METRICS
from server.observability.tracer import configure_logging, log
from server.pipeline import run_session

configure_logging()

app = FastAPI(title="Voice Tutor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[SETTINGS.allow_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "lang_default": SETTINGS.target_lang,
        "deepgram_configured": bool(SETTINGS.deepgram_api_key),
        "groq_configured": bool(SETTINGS.groq_api_key),
        "gemini_configured": bool(SETTINGS.gemini_api_key),
    }


@app.get("/metrics")
async def metrics():
    """Rolling 200-sample latency P50/P95/max/mean per stage."""
    return METRICS.snapshot()


@app.get("/session_recovery")
async def session_recovery(user_id: str = Query("demo-user"), lang: str = Query("spanish")):
    """Returns the learner's last in-progress lesson + due-vocab queue.
    Used by the client to seed a returning session."""
    repo = Repo()
    await repo.init()
    summary = await repo.progress_summary(user_id, lang)
    due = await repo.get_due_vocab(user_id, lang, limit=10)
    in_progress = [l for l in summary.get("lessons", []) if l.get("status") == "started"]
    return {
        "user_id": user_id,
        "in_progress": in_progress[:1],
        "due_vocab": due,
        "weak_areas": summary.get("weak_areas", []),
    }


@app.get("/api/curriculum/{lang}")
async def get_curriculum(lang: str):
    try:
        cur = load_curriculum(lang)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return {
        "language": cur.language,
        "lessons": [
            {
                "id": l.id,
                "title": l.title,
                "objective": l.objective,
                "vocab_count": len(l.vocab),
                "step_count": len(l.steps),
            }
            for l in cur.lessons
        ],
        "personas": {
            key: {"name": p.name, "voice_id": p.voice_id}
            for key, p in cur.voice.personas.items()
        },
    }


@app.get("/api/progress/{user_id}")
async def get_progress(user_id: str, lang: str = Query("spanish")):
    repo = Repo()
    await repo.init()
    return await repo.progress_summary(user_id, lang)


@app.get("/api/traces/{session_id}", response_class=PlainTextResponse)
async def get_traces(session_id: str):
    path = SETTINGS.traces_dir / f"{session_id}.jsonl"
    if not path.exists():
        return PlainTextResponse("not found", status_code=404)
    return path.read_text()


@app.websocket("/ws/audio")
async def ws_audio(
    ws: WebSocket,
    user_id: str = Query("demo-user"),
    lang: str = Query("spanish"),
):
    await ws.accept()
    log.info("ws.accept", user_id=user_id, lang=lang)
    try:
        await run_session(ws, user_id=user_id, target_lang=lang)
    except Exception as exc:  # noqa: BLE001
        log.error("ws.error", err=str(exc))
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


@app.get("/")
async def root():
    return {"name": "voice-tutor", "version": "0.1.0", "ws": "/ws/audio?user_id=...&lang=spanish|hindi"}
