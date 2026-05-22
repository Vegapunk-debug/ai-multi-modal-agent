"""Doubt-detection keyword filter coverage."""
from __future__ import annotations

import pytest

from server.agent.doubt import is_doubt


@pytest.mark.parametrize(
    "utterance",
    [
        "Wait, why is it 'la' and not 'el'?",
        "Why does this work?",
        "I don't understand what 'cuenta' means.",
        "Can you explain again?",
        "I have a doubt.",
        "I'm confused about gender.",
        "What does 'mujhe' mean?",
        "kya matlab hai uska?",
        "ruko, samajh nahi aaya",
        "Espera, no entiendo",
    ],
)
def test_doubt_triggers(utterance):
    assert is_doubt(utterance) is True


@pytest.mark.parametrize(
    "utterance",
    [
        "Hola, profesora",
        "Quisiera un café",
        "Buenos días",
        "next lesson",
        "namaste",
    ],
)
def test_non_doubt(utterance):
    assert is_doubt(utterance) is False


def test_empty_string_not_doubt():
    assert is_doubt("") is False
    assert is_doubt(None) is False  # type: ignore[arg-type]
