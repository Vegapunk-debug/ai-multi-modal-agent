"""Runtime config loaded from env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    gemini_api_key: str
    deepgram_api_key: str
    target_lang: str
    user_id: str
    log_level: str
    traces_dir: Path
    db_path: Path
    llm_model: str
    llm_provider: str
    stt_model: str
    stt_language: str
    vad_aggressiveness: int
    host: str
    port: int
    allow_origin: str


def load_settings() -> Settings:
    traces = Path(os.getenv("TRACES_DIR", "./traces"))
    traces.mkdir(parents=True, exist_ok=True)
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        target_lang=os.getenv("TARGET_LANG", "spanish").lower(),
        user_id=os.getenv("USER_ID", "demo-user"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        traces_dir=traces,
        db_path=Path(os.getenv("DB_PATH", "./tutor.sqlite")),
        llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        llm_provider=os.getenv("LLM_PROVIDER", "groq").lower(),
        stt_model=os.getenv("STT_MODEL", "nova-3"),
        stt_language=os.getenv("STT_LANGUAGE", "multi"),
        vad_aggressiveness=int(os.getenv("VAD_AGGRESSIVENESS", "2")),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        allow_origin=os.getenv("ALLOW_ORIGIN", "http://localhost:3000"),
    )


SETTINGS = load_settings()
