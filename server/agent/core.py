"""Agent core: glues LLM + tools + FSM + grader + memory.

Public surface: `Agent.handle_user_turn(text) -> AsyncIterator[AgentEvent]`.
Pipeline calls this on each finalized STT turn. The returned events drive TTS
synthesis (`speak`), state updates, and traces.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from server.agent import doubt as doubt_mod
from server.agent import grader as grader_mod
from server.agent.fsm import LessonState, Mode, QuizState, SessionState
from server.agent.intent import Intent, classify as classify_intent
from server.agent.quiz import build_quiz
from server.config import SETTINGS
from server.curriculum.loader import Curriculum
from server.db.repo import Repo
from server.observability.tracer import TurnTrace, log
from server.services.llm import LLM, ToolCall, make_judge_llm
from server.tools.definitions import TOOLS


@dataclass
class AgentEvent:
    kind: str  # 'speak' | 'state' | 'tool' | 'trace' | 'error'
    text: str = ""
    persona: str = "teacher"
    payload: dict[str, Any] = field(default_factory=dict)


class Agent:
    def __init__(
        self,
        curriculum: Curriculum,
        llm: LLM,
        repo: Repo,
        user_id: str,
        session_id: str | None = None,
    ):
        self.curriculum = curriculum
        self.llm = llm
        # Judge LLM: slower-but-smarter (Gemini 2.5 Flash). Used for semantic
        # grading and doubt answers where reasoning quality > latency.
        self.judge = make_judge_llm()
        self.repo = repo
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.state = SessionState()
        self.history: list[dict[str, Any]] = []

    # ------------- prompt assembly -------------

    def _system_prompt(self) -> str:
        diff = self.state.adapt_difficulty()
        recent_mistakes = self.state.session_mistakes[-3:]
        intro_vocab = ", ".join(self.state.introduced_vocab[-15:])
        ctx = f"""
[Runtime State]
mode={self.state.mode.value}
active_persona={self.state.active_persona}
difficulty_hint={diff}
introduced_vocab_recent={intro_vocab or 'none'}
session_mistakes_recent={recent_mistakes or 'none'}
target_language={self.curriculum.language}

[Available Lessons]
{json.dumps([{'id': l.id, 'title': l.title, 'objective': l.objective} for l in self.curriculum.lessons], indent=2)}

[Current Lesson]
{self._current_lesson_block()}
"""
        return self.curriculum.system_prompt + "\n\n" + ctx

    def _current_lesson_block(self) -> str:
        if not self.state.lesson:
            return "none"
        lesson = self.curriculum.get_lesson(self.state.lesson.lesson_id)
        if not lesson:
            return "none"
        step = lesson.steps[self.state.lesson.step_index] if self.state.lesson.step_index < len(lesson.steps) else None
        return json.dumps(
            {
                "id": lesson.id,
                "title": lesson.title,
                "step_index": self.state.lesson.step_index,
                "current_step": step,
                "score": self.state.lesson.score,
            },
            ensure_ascii=False,
        )

    # ------------- main loop -------------

    async def handle_user_turn(self, user_text: str, trace: TurnTrace | None = None) -> AsyncIterator[AgentEvent]:
        trace = trace or TurnTrace(self.session_id)
        trace.event("user.text", text=user_text)

        # Doubt fast-path detection.
        if self.state.mode in (Mode.TEACHING, Mode.QUIZ, Mode.CONVERSATION) and doubt_mod.is_doubt(user_text):
            log.info("agent.doubt_detected", text=user_text)
            self.state.push_for_doubt()
            answer = await self._answer_doubt(user_text)
            yield AgentEvent(
                kind="speak",
                text=f"<en>{answer}</en>",
                persona="english_narrator",
                payload={"mode": "doubt"},
            )
            yield AgentEvent(kind="state", payload={"mode": self.state.mode.value, "stack_depth": len(self.state.stack)})
            # Auto-resume signal
            self.state.pop_after_doubt()
            yield AgentEvent(kind="state", payload={"mode": self.state.mode.value, "resumed": True})
            trace.event("doubt.resolved")
            trace.flush()
            return

        self.history.append({"role": "user", "content": user_text})
        # Cap history to last 12 turns to bound prompt size.
        if len(self.history) > 24:
            self.history = self.history[-24:]

        # ----- Deterministic intent router (bypasses LLM for clear commands) -----
        intent_match = classify_intent(user_text)
        if intent_match.intent != Intent.NONE:
            log.info("agent.intent", intent=intent_match.intent.value, lesson_id=intent_match.lesson_id)
            handled = False
            async for ev in self._handle_intent(intent_match, user_text, trace):
                handled = True
                yield ev
            if handled:
                trace.flush()
                return

        # Loop: stream → tools → maybe-stream-again until no more tool calls.
        # Caps at 3 rounds so a runaway tool chain can't burn cost.
        any_speech = False
        for round_idx in range(3):
            messages = [
                {"role": "system", "content": self._system_prompt()},
                *self.history,
            ]

            assistant_text = ""
            pending_tool_calls: list[ToolCall] = []

            with trace.span(f"llm.stream.round{round_idx}"):
                try:
                    async for delta in self.llm.stream(messages=messages, tools=TOOLS, max_tokens=150, temperature=0.4):
                        if delta.text:
                            assistant_text += delta.text
                        if delta.tool_calls:
                            pending_tool_calls.extend(delta.tool_calls)
                except Exception as exc:  # noqa: BLE001
                    log.error("agent.llm_failure", err=str(exc))
                    yield AgentEvent(
                        kind="speak",
                        text="<en>Sorry, I had a hiccup. Let's continue.</en>",
                        persona="english_narrator",
                    )
                    trace.event("llm.error", err=str(exc))
                    trace.flush()
                    return

            if assistant_text.strip():
                any_speech = True
                yield AgentEvent(
                    kind="speak", text=assistant_text, persona=self.state.active_persona
                )
                self.history.append({"role": "assistant", "content": assistant_text})

            # No tools? Done.
            if not pending_tool_calls:
                break

            # Execute tool calls and feed results back.
            for tc in pending_tool_calls:
                with trace.span(f"tool.{tc.name}"):
                    result = await self._exec_tool(tc)
                trace.event("tool.result", tool_name=tc.name, result=result)

                self.history.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                            }
                        ],
                    }
                )
                self.history.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)}
                )

                # Persona swap emits a state event for the UI.
                if tc.name == "transition_to":
                    yield AgentEvent(
                        kind="state",
                        payload={"persona": self.state.active_persona, "reason": tc.arguments.get("reason")},
                    )
                # Tools with canned spoken payloads are spoken immediately; this avoids
                # an extra LLM round for the predictable lesson-step / quiz-question text.
                spoken = result.get("spoken") or result.get("spoken_feedback") if isinstance(result, dict) else None
                if spoken:
                    any_speech = True
                    yield AgentEvent(
                        kind="speak", text=spoken, persona=self.state.active_persona
                    )
                    self.history.append({"role": "assistant", "content": spoken})

            # If a tool that doesn't carry canned speech was called (e.g. lookup_vocab,
            # save_progress), loop back so the LLM can verbalize what to do next.
            silent_tool_only = all(
                tc.name in {"lookup_vocab", "save_progress", "resume_after_doubt", "handle_doubt"}
                for tc in pending_tool_calls
            )
            if not silent_tool_only:
                # Tool already had canned speech; no need to round again.
                break

        # If the model produced zero speech and zero useful tool side-effects, do one
        # last retry without tools to force a plain text reply. Bypasses the failure
        # mode where Llama returns an empty completion.
        if not any_speech:
            trace.event("agent.empty_completion_retry")
            messages = [
                {"role": "system", "content": self._system_prompt() + "\n\nIMPORTANT: reply with ONE short spoken sentence. Do not call tools."},
                *self.history,
                {"role": "user", "content": user_text},
            ]
            try:
                retry_text = await self.llm.complete(
                    messages=messages, max_tokens=80, temperature=0.5
                )
                if retry_text and retry_text.strip():
                    yield AgentEvent(
                        kind="speak",
                        text=retry_text.strip(),
                        persona=self.state.active_persona,
                    )
                    any_speech = True
                    self.history.append({"role": "assistant", "content": retry_text.strip()})
            except Exception as exc:  # noqa: BLE001
                log.warning("agent.retry_failed", err=str(exc))

        if not any_speech:
            yield AgentEvent(
                kind="speak",
                text="<en>Sorry, I didn't quite get that. Could you say it again?</en>",
                persona="english_narrator",
            )

        trace.flush()

    # ------------- intent router -------------

    async def _handle_intent(self, match, user_text: str, trace: TurnTrace):
        """Execute a deterministic action for a recognized intent.
        Yields AgentEvents. Doesn't consult the LLM at all."""
        intent = match.intent

        if intent == Intent.TEACH:
            lesson_id = match.lesson_id or self._guess_first_lesson()
            result = await self._tool_start_lesson(lesson_id=lesson_id)
            if "error" in result:
                yield AgentEvent(
                    kind="speak",
                    text=f"<en>I don't have a lesson on that. Try 'teach me greetings'.</en>",
                    persona="english_narrator",
                )
            else:
                yield AgentEvent(
                    kind="speak", text=result["spoken"], persona=self.state.active_persona
                )
            return

        if intent == Intent.QUIZ:
            lesson_id = match.lesson_id
            result = await self._tool_start_quiz(lesson_id=lesson_id, n_questions=5)
            if "error" not in result:
                yield AgentEvent(
                    kind="state",
                    payload={"persona": "examiner", "mode": "quiz"},
                )
                yield AgentEvent(
                    kind="speak", text=result["spoken"], persona="examiner"
                )
            return

        if intent == Intent.CONVO:
            self.state.mode = Mode.CONVERSATION
            self.state.active_persona = "companion"
            yield AgentEvent(kind="state", payload={"persona": "companion", "mode": "conversation"})
            yield AgentEvent(
                kind="speak",
                text="<en>Sure, let's roleplay. You're at a café in Madrid. Order something to drink.</en>",
                persona="companion",
            )
            return

        if intent == Intent.DOUBT:
            self.state.push_for_doubt()
            answer = await self._answer_doubt(user_text)
            yield AgentEvent(
                kind="speak",
                text=f"<en>{answer}</en>",
                persona="english_narrator",
            )
            self.state.pop_after_doubt()
            yield AgentEvent(kind="state", payload={"mode": self.state.mode.value, "resumed": True})
            return

        if intent == Intent.RESUME:
            if self.state.lesson:
                # Re-speak current step.
                lesson = self.curriculum.get_lesson(self.state.lesson.lesson_id)
                if lesson and self.state.lesson.step_index < len(lesson.steps):
                    spoken = self._step_spoken(lesson.steps[self.state.lesson.step_index])
                    yield AgentEvent(kind="speak", text=spoken, persona=self.state.active_persona)
                    return
            yield AgentEvent(
                kind="speak",
                text="<en>Nothing to resume yet. Want me to teach you greetings?</en>",
                persona="english_narrator",
            )
            return

        if intent == Intent.STOP:
            result = await self._tool_end_session()
            yield AgentEvent(kind="speak", text=result["spoken"], persona="english_narrator")
            return

        if intent == Intent.REPEAT:
            # Re-speak last assistant message
            for msg in reversed(self.history):
                if msg.get("role") == "assistant" and msg.get("content"):
                    yield AgentEvent(
                        kind="speak", text=msg["content"], persona=self.state.active_persona
                    )
                    return
            yield AgentEvent(
                kind="speak",
                text="<en>I don't have anything to repeat yet.</en>",
                persona="english_narrator",
            )
            return

        # Other intents (reset_*, confirm_*) — fall through to LLM for now.
        return

    def _guess_first_lesson(self) -> str:
        ids = self.curriculum.lesson_ids()
        return ids[0] if ids else "es_greetings"

    # ------------- doubt branch -------------

    async def _answer_doubt(self, question: str) -> str:
        # Use the judge LLM (Gemini) for richer pedagogical explanations.
        messages = [
            {"role": "system", "content": doubt_mod.DOUBT_SYSTEM},
            *self.history[-6:],
            {"role": "user", "content": question},
        ]
        try:
            return await self.judge.complete(messages=messages, max_tokens=120, temperature=0.4)
        except Exception as exc:  # noqa: BLE001
            log.warning("doubt.judge_failed", err=str(exc))
            try:
                return await self.llm.complete(messages=messages, max_tokens=120, temperature=0.4)
            except Exception as exc2:  # noqa: BLE001
                log.warning("doubt.fallback", err=str(exc2))
                return "Good question — let me get back to that. Want to continue for now?"

    # ------------- tool dispatch -------------

    async def _exec_tool(self, tc: ToolCall) -> dict[str, Any]:
        try:
            handler = getattr(self, f"_tool_{tc.name}")
        except AttributeError:
            return {"error": f"unknown tool {tc.name}"}
        try:
            return await handler(**tc.arguments)
        except TypeError as exc:
            return {"error": f"bad args: {exc}"}
        except Exception as exc:  # noqa: BLE001
            log.error("tool.exec_error", name=tc.name, err=str(exc))
            return {"error": str(exc)}

    def _step_spoken(self, step: dict[str, Any]) -> str:
        """Render a step's spoken text. Practice/check steps append a turn-taking cue."""
        if step.get("say"):
            return step["say"]
        prompt = step.get("prompt") or "Next."
        if step.get("type") in {"practice", "check"}:
            # Explicit "your turn" cue so learner knows when to respond.
            return f"<en>{prompt}</en>"
        return prompt

    async def _tool_start_lesson(self, lesson_id: str) -> dict[str, Any]:
        lesson = self.curriculum.get_lesson(lesson_id)
        if not lesson:
            return {"error": f"unknown lesson {lesson_id}", "available": self.curriculum.lesson_ids()}
        self.state.lesson = LessonState(lesson_id=lesson_id)
        self.state.mode = Mode.TEACHING
        await self.repo.record_lesson(self.user_id, lesson_id, self.curriculum.language, "started")
        first = lesson.steps[0]
        spoken = self._step_spoken(first)
        return {
            "ok": True,
            "lesson": {"id": lesson.id, "title": lesson.title, "objective": lesson.objective},
            "first_step": first,
            "spoken": spoken,
        }

    async def _tool_advance_step(self) -> dict[str, Any]:
        if not self.state.lesson:
            return {"error": "no active lesson"}
        lesson = self.curriculum.get_lesson(self.state.lesson.lesson_id)
        if not lesson:
            return {"error": "lesson missing"}
        self.state.lesson.step_index += 1
        idx = self.state.lesson.step_index
        if idx >= len(lesson.steps):
            await self.repo.record_lesson(
                self.user_id, lesson.id, self.curriculum.language, "completed",
                score=self.state.lesson.score,
            )
            self.state.mode = Mode.IDLE
            spoken = f"<en>Nice work — you finished</en> <{self.curriculum.voice.language_code}>{lesson.title}</{self.curriculum.voice.language_code}>. <en>Want a quick quiz?</en>"
            return {"completed": True, "spoken": spoken, "score": self.state.lesson.score}
        step = lesson.steps[idx]
        spoken = self._step_spoken(step)
        return {"step_index": idx, "step": step, "spoken": spoken}

    async def _tool_start_quiz(
        self, topic: str | None = None, lesson_id: str | None = None, n_questions: int = 5
    ) -> dict[str, Any]:
        qs = build_quiz(self.curriculum, lesson_id=lesson_id, n_questions=n_questions)
        if not qs:
            return {"error": "no quiz questions available"}
        self.state.quiz = QuizState(
            topic=topic or lesson_id or "mixed",
            questions=[q.to_dict() for q in qs],
            total=len(qs),
        )
        self.state.mode = Mode.QUIZ
        self.state.active_persona = "examiner"
        first = qs[0]
        spoken = f"<en>Quiz time. Question one.</en> {first.prompt}"
        return {"ok": True, "n_questions": len(qs), "first_question": first.to_dict(), "spoken": spoken}

    async def _tool_grade_answer(
        self, expected: str, learner_response: str, mode: str
    ) -> dict[str, Any]:
        # Code-level guard: refuse to grade random utterances. Only grade when the
        # current lesson step is a practice/check, OR when an active quiz expects
        # an answer. Without this guard the LLM can call grade_answer on any user
        # input and emit confusing "your answer is wrong" feedback.
        in_quiz = self.state.quiz is not None and self.state.mode == Mode.QUIZ
        in_practice = False
        if self.state.lesson:
            lesson = self.curriculum.get_lesson(self.state.lesson.lesson_id)
            if lesson and self.state.lesson.step_index < len(lesson.steps):
                step_type = lesson.steps[self.state.lesson.step_index].get("type")
                in_practice = step_type in {"practice", "check", "roleplay"}
        if not (in_quiz or in_practice):
            return {
                "skipped": True,
                "reason": "not in practice/check/quiz state — grade refused",
                "spoken": "",
            }
        grade = await grader_mod.grade(
            expected=expected,
            response=learner_response,
            mode=mode,
            language=self.curriculum.language,
            llm=self.judge,
        )
        if grade.correct:
            self.state.add_correct()
            if self.state.quiz:
                self.state.quiz.score += 1
                self.state.quiz.current += 1
            await self.repo.upsert_vocab(self.user_id, self.curriculum.language, expected, correct=True)
        else:
            self.state.add_mistake(
                {"expected": expected, "got": learner_response, "error_type": grade.error_type}
            )
            await self.repo.log_mistake(
                self.user_id, self.session_id, self.curriculum.language,
                self.state.lesson.lesson_id if self.state.lesson else None,
                expected, learner_response, grade.error_type,
            )
            await self.repo.upsert_vocab(self.user_id, self.curriculum.language, expected, correct=False)

        # Build spoken feedback wrapped in EN narrator tags.
        spoken_feedback = f"<en>{grade.feedback}</en>"
        return {
            **grade.to_dict(),
            "spoken_feedback": spoken_feedback,
            "difficulty_hint": self.state.adapt_difficulty(),
        }

    async def _tool_lookup_vocab(self, word: str) -> dict[str, Any]:
        for lesson in self.curriculum.lessons:
            for v in lesson.vocab:
                if v.get("target", "").lower() == word.lower() or v.get("english", "").lower() == word.lower() or v.get("roman", "").lower() == word.lower():
                    return {"found": True, "entry": v, "from_lesson": lesson.id}
        return {"found": False, "word": word}

    async def _tool_save_progress(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event == "vocab_seen":
            word = payload.get("word", "")
            if word:
                self.state.introduced_vocab.append(word)
        return {"ok": True}

    async def _tool_transition_to(self, persona: str, reason: str | None = None) -> dict[str, Any]:
        if persona not in {"teacher", "examiner", "companion"}:
            return {"error": f"unknown persona {persona}"}
        self.state.active_persona = persona
        return {"ok": True, "persona": persona, "reason": reason or ""}

    async def _tool_handle_doubt(self, question: str) -> dict[str, Any]:
        if self.state.mode != Mode.DOUBT:
            self.state.push_for_doubt()
        answer = await self._answer_doubt(question)
        return {"answer_en": answer, "spoken": f"<en>{answer}</en>"}

    async def _tool_resume_after_doubt(self) -> dict[str, Any]:
        self.state.pop_after_doubt()
        return {"ok": True, "mode": self.state.mode.value}

    async def _tool_end_session(self) -> dict[str, Any]:
        summary = await self._build_summary()
        await self.repo.end_session(self.session_id, summary)
        self.state.mode = Mode.SESSION_END
        spoken = f"<en>{summary}</en>"
        return {"summary": summary, "spoken": spoken}

    async def _build_summary(self) -> str:
        mistakes = self.state.session_mistakes
        msg = f"Great session. You introduced {len(self.state.introduced_vocab)} new words"
        if mistakes:
            kinds = sorted({m.get('error_type', 'other') for m in mistakes})
            msg += f" and we caught a few {', '.join(kinds)} slips — we'll review those next time."
        else:
            msg += " and nailed every check. See you soon."
        return msg
