"""OpenAI/Groq-style tool schemas exposed to the LLM."""
from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "start_lesson",
            "description": "Begin a lesson by id. Resets lesson state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "string",
                        "description": "Curriculum lesson id, e.g. 'es_greetings'.",
                    }
                },
                "required": ["lesson_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "advance_step",
            "description": "Move to the next step in the current lesson. Returns the next step payload.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_quiz",
            "description": "Start a quiz, optionally scoped to a topic or recent lesson.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "lesson_id": {"type": "string"},
                    "n_questions": {"type": "integer", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grade_answer",
            "description": "Semantically grade a learner response against expected answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expected": {"type": "string"},
                    "learner_response": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": [
                            "translation_en_to_target",
                            "translation_target_to_en",
                            "spoken_target",
                            "free_form",
                            "listening_comprehension",
                        ],
                    },
                },
                "required": ["expected", "learner_response", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_vocab",
            "description": "Look up a vocabulary word (target lang or English) and return meaning + grammar.",
            "parameters": {
                "type": "object",
                "properties": {"word": {"type": "string"}},
                "required": ["word"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_progress",
            "description": "Persist an event (lesson_complete, mistake, vocab_seen) to long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "enum": ["lesson_complete", "mistake", "vocab_seen"],
                    },
                    "payload": {"type": "object"},
                },
                "required": ["event", "payload"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transition_to",
            "description": "Hand off to a different persona (teacher | examiner | companion).",
            "parameters": {
                "type": "object",
                "properties": {
                    "persona": {"type": "string", "enum": ["teacher", "examiner", "companion"]},
                    "reason": {"type": "string"},
                },
                "required": ["persona"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handle_doubt",
            "description": "Save current state and answer a doubt in English. Call resume_after_doubt when done.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume_after_doubt",
            "description": "Pop the saved state and resume the lesson/quiz from where it left off.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_session",
            "description": "End the session gracefully and produce a spoken summary.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
