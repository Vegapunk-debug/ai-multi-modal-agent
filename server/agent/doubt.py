"""Doubt detection + handling.

Detection: keyword pre-filter (cheap) → LLM intent classification fallback.
Handling: push FSM state, answer in EN, then pop state to resume.
"""
from __future__ import annotations

import re

DOUBT_TRIGGERS_EN = [
    r"\bwait\b", r"\bwhy\b", r"\bwhat does\b", r"\bwhat is\b", r"\bi don'?t understand\b",
    r"\bcan you explain\b", r"\bi have a doubt\b", r"\bi'?m confused\b",
    r"\bhow come\b", r"\bquestion\b", r"\bclarify\b",
]
DOUBT_TRIGGERS_ES = [
    r"\bespera\b", r"\bpor qué\b", r"\bno entiendo\b", r"\bqué significa\b",
    r"\btengo una duda\b", r"\bexplica\b",
]
DOUBT_TRIGGERS_HI = [
    r"\bruko\b", r"\bkyun\b", r"\bkya matlab\b", r"\bsamajh nahi aaya\b",
    r"\bdoubt\b", r"\bclear nahi\b", r"\bphir se\b",
]


def is_doubt(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    for pattern_set in (DOUBT_TRIGGERS_EN, DOUBT_TRIGGERS_ES, DOUBT_TRIGGERS_HI):
        for pat in pattern_set:
            if re.search(pat, t):
                return True
    return False


DOUBT_SYSTEM = """You are a language tutor handling a learner's doubt mid-lesson.
Answer concisely IN ENGLISH (regardless of target language).
Rules:
- ≤3 sentences.
- Plain prose, no markdown.
- Use one mini-example in the target language only if it directly clarifies.
- Do NOT change topic. Do NOT lecture.
- End by gently offering to resume: 'Want to continue?'"""
