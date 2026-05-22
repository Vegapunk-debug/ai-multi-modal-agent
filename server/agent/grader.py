"""Semantic grading for learner responses.

Two-tier: fast heuristic (normalize + fuzzy) for short fixed-form answers,
LLM-judge fallback for free-form and ambiguous cases.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from server.agent.pronunciation import hint_for as pronunciation_hint_for


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[¿?¡!.,;:'\"]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class Grade:
    correct: bool
    partial: float  # 0..1
    feedback: str
    error_type: str = "none"  # 'gender' | 'verb_form' | 'vocab' | 'pronunciation' | 'other' | 'none'

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "partial": self.partial,
            "feedback": self.feedback,
            "error_type": self.error_type,
        }


def _fast_grade(expected: str, response: str) -> Grade | None:
    """Conservative fast path. Only auto-accepts identical normalized strings.
    Anything near-but-not-identical is punted to the LLM judge so subtle gender,
    article, or conjugation errors aren't waved through."""
    e = _normalize(expected)
    r = _normalize(response)
    if not r:
        return Grade(False, 0.0, "I didn't catch that. Could you try again?", "other")
    if e == r:
        return Grade(True, 1.0, "Perfect.", "none")
    char_ratio = fuzz.ratio(e, r) / 100
    # Far-off: definite no.
    if char_ratio < 0.55:
        return Grade(False, char_ratio, f"Not quite. Expected '{expected}'.", "vocab")
    # Anything in the grey zone punts to LLM judge — that's where gender/conjugation
    # errors live and we don't want to misclassify them here.
    return None


GRADER_SYSTEM = """You are a strict but fair language tutor grading a learner's response.
Return ONLY a single JSON object, no prose, with fields:
  correct (bool), partial (0..1), feedback (string, ≤25 words, actionable, speak-friendly),
  error_type ('gender' | 'verb_form' | 'vocab' | 'pronunciation' | 'other' | 'none').
Accept paraphrases that preserve meaning. For pronunciation mode, focus feedback on specific sounds.
Do not invent vocabulary the learner didn't say. Do not lecture."""


async def llm_grade(
    llm,
    expected: str,
    response: str,
    mode: str,
    language: str,
) -> Grade:
    user = (
        f"Language being learned: {language}\n"
        f"Grading mode: {mode}\n"
        f"Expected: {expected}\n"
        f"Learner said: {response}\n"
        f"Return JSON now."
    )
    raw = await llm.complete(
        messages=[
            {"role": "system", "content": GRADER_SYSTEM},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        temperature=0.1,
        max_tokens=200,
    )
    try:
        data = json.loads(raw)
        return Grade(
            correct=bool(data.get("correct", False)),
            partial=float(data.get("partial", 0.0)),
            feedback=str(data.get("feedback", "Try again.")),
            error_type=str(data.get("error_type", "other")),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return Grade(False, 0.0, "Let's try that one more time.", "other")


async def grade(
    expected: str,
    response: str,
    mode: str,
    language: str,
    llm,
) -> Grade:
    """Public grading entry point. Attaches actionable pronunciation feedback
    on incorrect spoken-target answers."""
    result: Grade
    if mode in {"spoken_target", "translation_en_to_target", "translation_target_to_en",
                "translation_en_to_es", "translation_es_to_en",
                "translation_en_to_hi", "translation_hi_to_en"}:
        fast = _fast_grade(expected, response)
        if fast is not None:
            result = fast
        else:
            result = await llm_grade(llm, expected, response, mode, language)
    else:
        result = await llm_grade(llm, expected, response, mode, language)

    # Augment incorrect spoken-target attempts with a specific pronunciation tip.
    if not result.correct and mode in {"spoken_target", "pronunciation"}:
        tip = pronunciation_hint_for(expected, response)
        if tip is not None:
            result.feedback = f"{result.feedback} {tip.hint}".strip()
            if result.error_type in {"other", "none"}:
                result.error_type = "pronunciation"
    return result
