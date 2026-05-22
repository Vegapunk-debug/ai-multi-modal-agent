"""Phoneme-aware pronunciation feedback.

Hard-coded hint dictionary keyed on (a) specific high-error Spanish words,
(b) phoneme patterns (silent h, rolled rr, soft c/z, q/qu, gue/güe, ll/y,
word-final d, v/b confusion, ñ).

Output is a single actionable sentence the grader attaches to wrong answers
in spoken_target / pronunciation grading modes. Replaces generic "good job"
feedback with something a learner can act on.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class PronunciationHint:
    severity: str  # 'minor' | 'major'
    word: str | None
    hint: str


# Per-word hints for common high-error vocabulary in our curriculum.
WORD_HINTS: dict[str, str] = {
    "hola": "The 'h' in 'hola' is silent. Say it as 'OH-lah'.",
    "buenos días": "Stress the second syllable of 'días' — 'DEE-ahs'.",
    "buenas tardes": "Make 'tardes' two clear syllables: 'TAR-des'.",
    "buenas noches": "The 'ch' in 'noches' is like English 'church', not 'k'.",
    "perro": "Roll the 'rr' in 'perro' — tongue tip taps the roof of your mouth.",
    "pero": "Single 'r' here is soft — almost a 'd' sound.",
    "agua": "The 'gu' before 'a' is a hard 'g', not 'w'.",
    "guisante": "The 'gui' is just 'gee', the 'u' is silent.",
    "vergüenza": "The umlaut 'ü' means pronounce the 'u' — 'gwen', not 'gen'.",
    "español": "The 'ñ' is like the 'ny' in 'canyon'.",
    "señor": "Same 'ñ' — pronounce 'sen-YOR'.",
    "año": "Critical: 'año' = year, 'ano' = something else entirely. Roll that 'ñ'.",
    "llamo": "Double 'll' in Spain sounds like 'y' — 'YAH-mo'.",
    "ella": "Same: 'EH-yah', not 'EL-lah'.",
    "cuenta": "The 'cue' is 'KWEN' — quick blend.",
    "quisiera": "The 'qu' is just 'k' — 'kee-SYEH-rah'.",
    "ciudad": "Soft 'c' before 'i' — 'syoo-DAHD'. Word-final 'd' is barely there.",
    "gracias": "Stress the first syllable: 'GRAH-syas'.",
    "uno": "Short and clean: 'OO-no'.",
    "siete": "'sye-teh' — two clean syllables, soft 't'.",
    "ocho": "'OH-cho' — 'ch' like 'church'.",
    "diez": "Single syllable, soft 'z' (or 'th' in Castilian).",
    "dieciséis": "Compound: 'dye-thee-SAYS'. Stress on last syllable.",
    "veinte": "'VAYN-teh' — that 'ei' is a diphthong.",
    "mucho": "'MOO-cho' — 'ch' like 'church'.",
    "gusto": "Hard 'g' — 'GOOS-to'.",
}

# Phoneme-pattern hints triggered when an exact word match misses but the
# learner's response contains a known tricky pattern.
PATTERN_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brr"), "Roll the 'rr' — tongue tip flutters against the roof."),
    (re.compile(r"\bh\w"), "Spanish 'h' is silent — drop it entirely."),
    (re.compile(r"ñ"), "The 'ñ' is 'ny' as in 'canyon'."),
    (re.compile(r"ll"), "'ll' sounds like 'y' — 'tortilla' = 'tor-TEE-yah'."),
    (re.compile(r"\bqu"), "'qu' is just 'k' — never a 'kw' sound."),
    (re.compile(r"\bgu[ei]"), "'gue/gui' = hard 'g' + e/i. The 'u' is silent unless ü."),
    (re.compile(r"ü"), "Umlaut 'ü' means: now pronounce the 'u'."),
    (re.compile(r"\bj\w"), "Spanish 'j' is a back-of-throat 'h' sound (like German 'ch')."),
    (re.compile(r"\bc[ei]"), "Soft 'c' before e/i is 's' (Latin Am) or 'th' (Spain)."),
    (re.compile(r"\bz"), "'z' is 's' (Latin Am) or 'th' (Spain)."),
    (re.compile(r"[vb]"), "Spanish 'v' and 'b' sound almost identical — soft 'b'."),
    (re.compile(r"d\b"), "Word-final 'd' is soft, almost like 'th' in 'the'."),
]


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFC", s)  # keep ñ, ü intact
    s = re.sub(r"[¿?¡!.,;:'\"]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def hint_for(expected: str, learner_response: str) -> PronunciationHint | None:
    """Return a specific actionable hint for a wrong pronunciation attempt.

    First tries an exact word match (most accurate).
    Then falls back to phoneme pattern matching on the expected text.
    Returns None if no actionable hint applies.
    """
    if not expected:
        return None
    exp_norm = _normalize(expected)

    # 1. Per-word hints — best signal.
    if exp_norm in WORD_HINTS:
        return PronunciationHint(severity="major", word=exp_norm, hint=WORD_HINTS[exp_norm])
    # Multi-word expected: scan each token.
    for token in exp_norm.split():
        if token in WORD_HINTS:
            return PronunciationHint(severity="minor", word=token, hint=WORD_HINTS[token])

    # 2. Pattern hints — fallback when no word match.
    for pat, hint in PATTERN_HINTS:
        if pat.search(exp_norm):
            return PronunciationHint(severity="minor", word=None, hint=hint)

    return None
