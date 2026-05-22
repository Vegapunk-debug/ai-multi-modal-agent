"""Deterministic intent router.

Replaces the LLM tool-call path for mode transitions. Keyword + phrase matching
to one of a fixed set of intents. If matched, the pipeline executes the action
deterministically (start_lesson, start_quiz, etc.) without an LLM round-trip.

Why: Llama-4-scout occasionally emits malformed tool calls or skips them
entirely on borderline phrasings ("can you teach me hello"). The intent router
makes lesson commands 100% reliable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    NONE = "none"
    TEACH = "teach"
    QUIZ = "quiz"
    CONVO = "convo"
    DOUBT = "doubt"
    RESUME = "resume"
    STOP = "stop"
    RESET_ALL = "reset_all"
    RESET_WEAK = "reset_weak"
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    REPEAT = "repeat"


@dataclass
class IntentMatch:
    intent: Intent
    confidence: float
    lesson_id: Optional[str] = None
    topic_hint: Optional[str] = None


# Keyword sets (lowercased). Match whole-word boundaries to avoid "teaching" → TEACH.
INTENT_PATTERNS: dict[Intent, list[str]] = {
    Intent.TEACH: [
        r"\bteach\b", r"\blesson\b", r"\blearn\b", r"\bteach me\b",
        r"\bstart lesson\b", r"\bsikha\b",
    ],
    Intent.QUIZ: [
        r"\bquiz\b", r"\btest me\b", r"\btest my\b", r"\bcheck my\b",
        r"\bquiz me\b",
    ],
    Intent.CONVO: [
        r"\broleplay\b", r"\brole play\b", r"\bconversation\b",
        r"\blet's chat\b", r"\blet's practice\b", r"\bpractice conversation\b",
        r"\bspeak with me\b", r"\btalk with me\b",
    ],
    Intent.DOUBT: [
        r"\bwait\b", r"\bdoubt\b", r"\bwhy is\b", r"\bwhy does\b", r"\bwhy do\b",
        r"\bi have a question\b", r"\bwhat does\b",
        r"\bwhat's the difference\b", r"\bwhats the difference\b",
        r"\bhow come\b", r"\bi don'?t understand\b", r"\bi'?m confused\b",
    ],
    Intent.RESUME: [
        r"\bcontinue\b", r"\bgo on\b", r"\bback to\b", r"\bresume\b",
        r"\blet's continue\b", r"\bkeep going\b",
    ],
    Intent.STOP: [
        r"\bstop\b", r"\bend session\b", r"\bgoodbye\b",
        r"\bthanks bye\b", r"\bthat's all\b", r"\bend the session\b",
    ],
    Intent.RESET_ALL: [
        r"\breset my progress\b", r"\breset everything\b",
        r"\bforget my progress\b", r"\bstart fresh\b",
        r"\bwipe my progress\b", r"\bclear all my progress\b", r"\breset all\b",
    ],
    Intent.RESET_WEAK: [
        r"\breset weak spots\b", r"\bclear weak spots\b",
        r"\bforget my mistakes\b", r"\breset my mistakes\b",
    ],
    Intent.CONFIRM_YES: [
        r"^yes\b", r"^yeah\b", r"^yep\b", r"\bconfirm\b",
        r"\byes please\b", r"\bgo ahead\b", r"\byes reset\b",
    ],
    Intent.CONFIRM_NO: [
        r"^no\b", r"^nope\b", r"\bcancel\b", r"\bnever mind\b",
        r"\bdon't\b", r"\bdo not\b",
    ],
    Intent.REPEAT: [
        r"\brepeat\b", r"\bsay again\b", r"\bone more time\b", r"\bagain please\b",
    ],
}

# Topic hints → lesson_id mapping. Matched on user text in addition to TEACH intent.
LESSON_TOPIC_MAP: list[tuple[list[str], str]] = [
    (["greet", "hello", "saludo", "hola", "introduce"], "es_greetings"),
    (["number", "count", "número", "numero"], "es_numbers"),
    (["food", "order", "restaurant", "café", "cafe", "menu", "comida"], "es_ordering_food"),
    (["family", "familia", "father", "mother", "brother", "sister"], "es_family"),
    (["day", "week", "time", "clock", "dias", "días", "hora"], "es_days_time"),
    (["direction", "where", "right", "left", "bathroom", "station", "hotel"], "es_directions"),
]


def classify(text: str) -> IntentMatch:
    """Classify user utterance into an intent. Returns Intent.NONE if no match."""
    if not text:
        return IntentMatch(Intent.NONE, 0.0)
    t = text.lower().strip()

    # Match priority order. TEACH and QUIZ + topic combo handled together so
    # the lesson_id can be embedded.
    matched: Intent = Intent.NONE
    for intent, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, t):
                matched = intent
                break
        if matched != Intent.NONE:
            break

    lesson_id = None
    topic_hint = None
    if matched in (Intent.TEACH, Intent.QUIZ):
        for keywords, lid in LESSON_TOPIC_MAP:
            if any(kw in t for kw in keywords):
                lesson_id = lid
                topic_hint = keywords[0]
                break

    # Confidence is a coarse heuristic: 1.0 when an explicit phrase matched,
    # 0.6 if only a single keyword.
    confidence = 0.85 if matched != Intent.NONE else 0.0
    return IntentMatch(intent=matched, confidence=confidence, lesson_id=lesson_id, topic_hint=topic_hint)
