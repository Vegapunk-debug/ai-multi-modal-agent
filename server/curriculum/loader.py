"""Load curriculum, voice config, and system prompt for a target language."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CURRICULUM_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Persona:
    name: str
    voice_id: str
    rate: str
    pitch: str
    persona_prompt: str


@dataclass(frozen=True)
class VoiceConfig:
    language_code: str
    stt_hint: list[str]
    personas: dict[str, Persona]


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    level: str
    objective: str
    vocab: list[dict[str, Any]]
    grammar_notes: list[str]
    steps: list[dict[str, Any]]


@dataclass(frozen=True)
class Curriculum:
    language: str
    lessons: list[Lesson]
    voice: VoiceConfig
    system_prompt: str

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        return next((l for l in self.lessons if l.id == lesson_id), None)

    def lesson_ids(self) -> list[str]:
        return [l.id for l in self.lessons]


@lru_cache(maxsize=4)
def load_curriculum(language: str) -> Curriculum:
    lang = language.lower()
    base = CURRICULUM_DIR / lang
    if not base.exists():
        raise ValueError(f"Curriculum for '{lang}' not found at {base}")

    lessons_data = json.loads((base / "lessons.json").read_text())
    voice_data = json.loads((base / "voice_config.json").read_text())
    system_prompt = (base / "system_prompt.md").read_text()

    personas = {
        key: Persona(**val) for key, val in voice_data["personas"].items()
    }
    voice = VoiceConfig(
        language_code=voice_data["language_code"],
        stt_hint=voice_data["stt_hint"],
        personas=personas,
    )
    lessons = [Lesson(**l) for l in lessons_data["lessons"]]
    return Curriculum(
        language=lang,
        lessons=lessons,
        voice=voice,
        system_prompt=system_prompt,
    )
