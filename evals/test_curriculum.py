"""Curriculum loader sanity checks."""
from __future__ import annotations

import pytest

from server.curriculum.loader import load_curriculum


@pytest.mark.parametrize("lang", ["spanish", "hindi"])
def test_curriculum_loads(lang):
    c = load_curriculum(lang)
    assert c.language == lang
    assert len(c.lessons) >= 3
    assert c.system_prompt
    assert "teacher" in c.voice.personas
    assert "examiner" in c.voice.personas
    assert "companion" in c.voice.personas


@pytest.mark.parametrize("lang", ["spanish", "hindi"])
def test_every_lesson_has_steps_and_vocab(lang):
    c = load_curriculum(lang)
    for l in c.lessons:
        assert l.id
        assert l.title
        assert l.objective
        assert len(l.vocab) > 0
        assert len(l.steps) >= 5  # objective → explain → examples → practice → check at minimum


@pytest.mark.parametrize("lang", ["spanish", "hindi"])
def test_steps_have_required_fields(lang):
    c = load_curriculum(lang)
    for lesson in c.lessons:
        for step in lesson.steps:
            assert "type" in step
            if step["type"] in {"practice", "check"}:
                # Practice/check steps must define expected
                assert step.get("expected") or step.get("mode") == "free_form"


def test_unknown_lang_raises():
    with pytest.raises(ValueError):
        load_curriculum("klingon")
