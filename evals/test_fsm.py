"""FSM tests — lesson state, doubt stack, difficulty adaptation."""
from __future__ import annotations

from server.agent.fsm import LessonState, Mode, QuizState, SessionState


def test_initial_state():
    s = SessionState()
    assert s.mode == Mode.IDLE
    assert s.active_persona == "teacher"
    assert s.lesson is None


def test_doubt_push_pop_restores_state():
    s = SessionState()
    s.mode = Mode.TEACHING
    s.active_persona = "teacher"
    s.lesson = LessonState(lesson_id="es_greetings", step_index=3, score=2.0)
    s.push_for_doubt()
    assert s.mode == Mode.DOUBT
    s.pop_after_doubt()
    assert s.mode == Mode.TEACHING
    assert s.lesson is not None and s.lesson.step_index == 3
    assert s.lesson.score == 2.0


def test_doubt_pop_with_empty_stack_goes_idle():
    s = SessionState()
    s.pop_after_doubt()
    assert s.mode == Mode.IDLE


def test_difficulty_simplify_after_two_wrong():
    s = SessionState()
    s.lesson = LessonState(lesson_id="es_numbers")
    s.add_mistake({"expected": "siete", "got": "ocho", "error_type": "vocab"})
    s.add_mistake({"expected": "ocho", "got": "siete", "error_type": "vocab"})
    assert s.adapt_difficulty() == "simplify"


def test_difficulty_advance_after_three_correct():
    s = SessionState()
    s.lesson = LessonState(lesson_id="es_numbers")
    for _ in range(3):
        s.add_correct()
    assert s.adapt_difficulty() == "advance"


def test_consecutive_counters_reset():
    s = SessionState()
    s.lesson = LessonState(lesson_id="es_numbers")
    s.add_correct()
    s.add_correct()
    s.add_mistake({"expected": "uno", "got": "dos", "error_type": "vocab"})
    assert s.lesson.consecutive_correct == 0
    assert s.lesson.consecutive_wrong == 1


def test_quiz_state_increment():
    qs = QuizState(topic="es_greetings", questions=[{"qid": "q1"}, {"qid": "q2"}], total=2)
    qs.current = 1
    qs.score = 1
    assert qs.current < qs.total


def test_nested_doubt_stack():
    s = SessionState()
    s.mode = Mode.TEACHING
    s.lesson = LessonState(lesson_id="es_greetings", step_index=2)
    s.push_for_doubt()
    s.push_for_doubt()  # nested doubt
    assert len(s.stack) == 2
    s.pop_after_doubt()
    assert s.mode == Mode.DOUBT
    s.pop_after_doubt()
    assert s.mode == Mode.TEACHING
