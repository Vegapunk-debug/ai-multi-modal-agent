"""Lesson Finite-State Machine.

Why FSM over LangGraph: lesson flow is small (5 states), deterministic, and we need
a state stack for doubt-interrupt resume — easier to reason about with explicit code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    IDLE = "idle"
    TEACHING = "teaching"
    QUIZ = "quiz"
    CONVERSATION = "conversation"
    DOUBT = "doubt"
    SESSION_END = "session_end"


@dataclass
class LessonState:
    lesson_id: str
    step_index: int = 0
    consecutive_correct: int = 0
    consecutive_wrong: int = 0
    score: float = 0.0


@dataclass
class QuizState:
    topic: str
    questions: list[dict[str, Any]] = field(default_factory=list)
    current: int = 0
    score: int = 0
    total: int = 0


@dataclass
class SessionState:
    mode: Mode = Mode.IDLE
    active_persona: str = "teacher"
    lesson: LessonState | None = None
    quiz: QuizState | None = None
    # Stack: snapshots for doubt-interrupt resume.
    stack: list[dict[str, Any]] = field(default_factory=list)
    introduced_vocab: list[str] = field(default_factory=list)
    session_mistakes: list[dict[str, Any]] = field(default_factory=list)

    def push_for_doubt(self) -> None:
        self.stack.append(
            {
                "mode": self.mode,
                "persona": self.active_persona,
                "lesson": self.lesson,
                "quiz": self.quiz,
            }
        )
        self.mode = Mode.DOUBT

    def pop_after_doubt(self) -> None:
        if not self.stack:
            self.mode = Mode.IDLE
            return
        snap = self.stack.pop()
        self.mode = snap["mode"]
        self.active_persona = snap["persona"]
        self.lesson = snap["lesson"]
        self.quiz = snap["quiz"]

    def adapt_difficulty(self) -> str:
        """Return a difficulty hint for the prompt: 'simplify' | 'advance' | 'maintain'."""
        if not self.lesson:
            return "maintain"
        if self.lesson.consecutive_wrong >= 2:
            return "simplify"
        if self.lesson.consecutive_correct >= 3:
            return "advance"
        return "maintain"

    def add_mistake(self, mistake: dict[str, Any]) -> None:
        self.session_mistakes.append(mistake)
        if self.lesson:
            self.lesson.consecutive_wrong += 1
            self.lesson.consecutive_correct = 0

    def add_correct(self) -> None:
        if self.lesson:
            self.lesson.consecutive_correct += 1
            self.lesson.consecutive_wrong = 0
            self.lesson.score += 1
