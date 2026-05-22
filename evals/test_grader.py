"""Grader unit tests — non-LLM fast path verifications + golden-set accuracy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.agent.grader import Grade, _fast_grade, _normalize


GOLDEN = json.loads((Path(__file__).parent / "golden_set.json").read_text())


def test_normalize_strips_accents_and_punct():
    assert _normalize("¿Cómo estás?") == "como estas"
    assert _normalize("Buenos días.") == "buenos dias"
    assert _normalize("  HOLA  ") == "hola"


def test_fast_grade_exact_match():
    g = _fast_grade("Hola", "Hola")
    assert g is not None and g.correct is True
    assert g.partial == 1.0


def test_fast_grade_accent_stripped():
    # Pure accent strip = exact match after normalization.
    g = _fast_grade("¿Cómo estás?", "Como estas")
    assert g is not None and g.correct is True


def test_fast_grade_punctuation_strip():
    g = _fast_grade("Buenos días.", "buenos días")
    assert g is not None and g.correct is True


def test_fast_grade_silent_h_punts_to_llm():
    # 'Hola' vs 'Ola' — semantically different ('wave' vs 'hello'); fast grader must punt.
    g = _fast_grade("Hola", "Ola")
    assert g is None  # LLM-judge will decide based on mode (pronunciation vs spelling)


def test_fast_grade_gender_swap_punts_to_llm():
    # Single-letter gender flip — must NOT be auto-accepted by fast path.
    g = _fast_grade("Buenos días", "Buenas días")
    assert g is None
    g2 = _fast_grade("La cuenta, por favor", "El cuenta por favor")
    assert g2 is None


def test_fast_grade_wrong():
    g = _fast_grade("siete", "ocho")
    # Different words: fast grader returns None (punt to LLM) OR False.
    if g is not None:
        assert g.correct is False


def test_fast_grade_blank():
    g = _fast_grade("Hola", "")
    assert g is not None and g.correct is False


def test_grade_object_serialization():
    g = Grade(True, 0.95, "Great", "none")
    d = g.to_dict()
    assert d["correct"] is True
    assert d["partial"] == 0.95
    assert d["error_type"] == "none"


@pytest.mark.parametrize(
    "item",
    [c for c in GOLDEN["spanish"] if c["mode"].startswith("spoken")],
)
def test_golden_spanish_spoken(item):
    """Golden-set check using only fast-path (offline). Cases where the fast
    path returns None are skipped (those would invoke LLM in real flow)."""
    g = _fast_grade(item["expected"], item["got"])
    if g is None:
        pytest.skip("fast path punted (LLM-only case)")
    assert g.correct == item["correct"], f"{item}"
