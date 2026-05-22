"""Persona resolution for multi-agent voice handoff."""
from __future__ import annotations

from server.curriculum.loader import Curriculum, Persona


def resolve_persona(curriculum: Curriculum, key: str) -> Persona:
    personas = curriculum.voice.personas
    if key in personas:
        return personas[key]
    return personas.get("teacher") or next(iter(personas.values()))


def english_voice(curriculum: Curriculum) -> Persona:
    return curriculum.voice.personas.get("english_narrator") or resolve_persona(
        curriculum, "teacher"
    )
