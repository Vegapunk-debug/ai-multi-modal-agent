"""Quiz engine — generates and scores adaptive quizzes."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from server.curriculum.loader import Curriculum, Lesson


@dataclass
class QuizQuestion:
    qid: str
    type: str  # 'translation_en_to_target' | 'translation_target_to_en' | 'listening' | 'spoken_target'
    prompt: str
    expected: str
    expected_alts: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "qid": self.qid,
            "type": self.type,
            "prompt": self.prompt,
            "expected": self.expected,
            "expected_alts": self.expected_alts,
            "metadata": self.metadata,
        }


def build_quiz(
    curriculum: Curriculum,
    lesson_id: str | None = None,
    n_questions: int = 5,
) -> list[QuizQuestion]:
    """Pull vocab from one lesson (or all) and produce mixed question types."""
    lessons = (
        [curriculum.get_lesson(lesson_id)]
        if lesson_id
        else list(curriculum.lessons)
    )
    lessons = [l for l in lessons if l is not None]
    if not lessons:
        return []

    pool: list[tuple[Lesson, dict[str, Any]]] = []
    for lesson in lessons:
        for v in lesson.vocab:
            pool.append((lesson, v))

    random.shuffle(pool)
    pool = pool[:n_questions]

    types_cycle = [
        "translation_en_to_target",
        "translation_target_to_en",
        "spoken_target",
        "listening",
        "translation_en_to_target",
    ]
    questions: list[QuizQuestion] = []
    for i, (lesson, vocab) in enumerate(pool):
        qtype = types_cycle[i % len(types_cycle)]
        target = vocab.get("target", "")
        english = vocab.get("english", "")
        roman = vocab.get("roman", "")
        alts = [target]
        if roman:
            alts.append(roman)

        if qtype == "translation_en_to_target":
            prompt = f"Translate to {curriculum.language.title()}: '{english}'"
            expected = target
        elif qtype == "translation_target_to_en":
            speak = target + (f" ({roman})" if roman else "")
            prompt = f"What does '{speak}' mean in English?"
            expected = english
            alts = [english.lower()]
        elif qtype == "listening":
            prompt = f"Listen carefully and repeat: <{curriculum.voice.language_code}>{target}</{curriculum.voice.language_code}>"
            expected = target
        else:  # spoken_target
            prompt = f"Say '{english}' in {curriculum.language.title()}."
            expected = target

        questions.append(
            QuizQuestion(
                qid=f"q{i+1}",
                type=qtype,
                prompt=prompt,
                expected=expected,
                expected_alts=alts,
                metadata={"lesson_id": lesson.id, "vocab": vocab},
            )
        )
    return questions
