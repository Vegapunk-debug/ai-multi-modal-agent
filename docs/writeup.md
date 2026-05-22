# Technical Write-Up — Lingua Voice Tutor

**Submission:** AI Engineer Take-Home — Voice-first multi-modal language learning agent.
**Languages shipped:** Spanish (default) + Hindi. Both taught in English.
**Stack:** FastAPI + asyncio pipeline · Groq Llama 3.3 70B · Deepgram Nova-3 · Microsoft Edge TTS · Silero VAD · Next.js + WebGL · SQLite.

---

## 1. Decisions & trade-offs

### Pipeline orchestration: Pipecat-style, not Pipecat

The brief asks for Pipecat or LiveKit. Pipecat's mental model (VAD → STT → agent → TTS with cancellable frames) is exactly right for this product. But to debug latency at the milli-second level and prove barge-in cancellation correctness, I needed every frame in-process and inspectable. So the pipeline is a small asyncio orchestrator (`server/pipeline.py`) that follows Pipecat's pattern: a session owns the STT WebSocket, the agent task, and a cancellable TTS task that any user-speech signal pre-empts. Same architecture, fewer layers between me and the wire. If we needed scale or telephony, swapping in LiveKit Agents (or Pipecat proper) is a 200-line lift — adapter at the WebSocket boundary.

### LLM: Groq Llama 3.3 70B

Two reasons. First, TTFT — Groq's inference TTFT is ~200 ms vs ~500 ms for Claude or GPT, which is half of my latency budget. Second, the brief permits any modern LLM and Groq is free. Tool calling is OpenAI-compatible. The provider adapter (`server/services/llm.py`) is OpenAI-shape so `LLM_PROVIDER=gemini` swaps in Gemini 2.0 Flash without touching agent code.

### STT: Deepgram Nova-3 `language=multi`

Deepgram is the only free-tier streaming STT I trust to handle EN ⇄ ES and EN ⇄ HI code-switching in a single stream. Crucially this matters because the doubt-resolution flow involves the learner switching from target language *back* into English mid-utterance. Whisper streaming (Groq's Whisper-large-v3-turbo) is faster but is effectively chunked, not true streaming — endpointing would suffer. Deepgram's $200 free credit covers ~200 hours, more than enough for the prototype + grading.

### TTS: Microsoft Edge TTS

Free, no key, neural voices for both target languages. Crucially it has *eight* Spanish voices and two Hindi voices that I can use to back the three-persona handoff feature. Cartesia would be faster (90 ms TTFB vs ~250 ms) but its free tier is too thin and its Hindi catalog is weak. Edge TTS is unofficial — the write-up flags this as a productionization risk; Piper TTS local is the fallback path (schema in `services/tts.py`).

### State management: FSM with stack, not LangGraph

The lesson loop has five states (idle, teaching, quiz, conversation, doubt) and needs a stack so a doubt can be popped to resume the prior state. LangGraph buys you nothing here over an `Enum` and a `list[snapshot]`. The FSM is in `server/agent/fsm.py`, ~70 lines, fully unit-tested.

### Grading: two-tier (fast + LLM-judge)

A fast path strips accents and punctuation, then runs `rapidfuzz.token_set_ratio`. Anything ≥ 0.9 is accepted; ≥ 0.7 is "close, try again." Below that, or any free-form mode, falls through to an LLM judge with a strict JSON schema. The judge returns `{correct, partial, feedback, error_type}` — the `error_type` powers the weak-areas heatmap. This keeps median grading at <30 ms while preserving the brief's "semantic grading, not exact string match" requirement.

### Doubt-resolution: regex pre-filter + state stack

Cheap multilingual regex (`wait`, `why`, `kyun`, `por qué`, `samajh nahi aaya`, ...) classifies most doubts in <1 ms. Confirmed doubts push the current FSM snapshot (mode, persona, lesson position, quiz position) onto a stack, the agent answers in English with a strict ≤3-sentence system prompt, then auto-pops the stack and resumes. Nested doubts work — tested in `evals/test_fsm.py::test_nested_doubt_stack`.

### Memory

- **Short-term** (session): introduced vocab, recent mistakes — held in `SessionState`, injected into the system prompt so the agent can reference what it just taught without re-fetching from DB.
- **Long-term** (SQLite): per-user `lesson_progress`, `mistakes`, `vocab_mastery` (with SM-2 fields), and `sessions`. The schema (`server/db/schema.sql`) is small enough to inspect at a glance.
- **SM-2 spaced repetition**: on every correct/incorrect grade we call `Repo.upsert_vocab` which updates the SM-2 interval, ease factor, and `due_at`. Next session, `get_due_vocab` surfaces what to review.

---

## 2. Latency

**Target:** P50 end-to-end < 1500 ms, barge-in < 300 ms.
**Measured (laptop, local server):**

| Stage | P50 | P95 |
|------|-----|-----|
| Deepgram STT endpoint (post-utterance) | 240 ms | 320 ms |
| Groq LLM TTFT (with tool decision) | 210 ms | 380 ms |
| Edge TTS TTFB | 250 ms | 410 ms |
| Pipeline overhead | 60 ms | 110 ms |
| **End-to-end (user-speech-end → first TTS chunk)** | **~770 ms** | **~1100 ms** |
| Barge-in (user-speech-start → audio silence) | 180 ms | 240 ms |

Numbers come from `traces/*.jsonl` (every stage timestamped). The InsightsPanel in the UI surfaces P50/P95 live. Some implementation choices that moved the needle:

- Deepgram `endpointing=300` rather than the default 700 ms; the 400 ms saving here is bigger than any model-side win.
- Client emits a `user_speech_start` control message the moment its in-browser VAD trips, *before* Deepgram even acknowledges. The server cancels the TTS task on this signal, not on the Deepgram interim — that's how barge-in stays under 250 ms.
- Tool-call streaming: the LLM provider streams tool-call arguments; we don't wait for `finish_reason` to start preparing TTS, since `start_lesson`'s spoken text is the canned first-step `say` text and can begin synthesizing immediately.

---

## 3. Cost per session

Five-minute session = ~10 turns @ 5 s each.

| Component | Per-session estimate |
|----------|---------------------|
| Deepgram STT | 5 min × $0.0043/min = **$0.022** (covered by $200 free credit for ~46,500 sessions) |
| Groq Llama 3.3 70B | ~3 k input + 1 k output tokens/turn × 10 = ~40 k tokens. Free tier covers it. Paid: ~$0.018 |
| Edge TTS | **$0** (free, no quota disclosed) |
| Compute (1 vCPU, 512 MB) | trivial |
| **Total free-tier** | **$0** |
| **Total at break-out scale (paid Groq, paid Deepgram)** | **~$0.04 / session** |

---

## 4. AI tooling used

This submission was built with **Claude Code (Opus 4.7)** as a coding assistant. I reviewed every file before commit. The agent helped with:

- Initial scaffolding and the pyproject/Makefile structure.
- The Three.js shader for the orb (vertex displacement + Fresnel glow + persona color uniform).
- SM-2 algorithm transcription (I verified the math against the reference SuperMemo paper).
- The Edge TTS span-router (split text on `<es>`/`<hi>`/`<en>` tags and route per span).

Areas I owned end-to-end: the agent core (turn loop, doubt fast-path, tool dispatch), the FSM and stack semantics, the curriculum content for both languages, the grading two-tier design, the eval harness, the latency targets and instrumentation, and the write-up.

---

## 5. What I'd build next (with another 24 h)

1. **Pronunciation scoring** via Azure Speech Pronunciation Assessment for Spanish — phoneme-level scores, not just LLM judgement. Hindi has no comparable free service; would need Montreal Forced Aligner locally.
2. **Streaming evaluation** — start grading on STT partials, confirm at final. Trims ~200 ms off the response-feedback gap.
3. **Telephony**: Twilio + LiveKit SIP so the learner can literally call the tutor. The pipeline is provider-agnostic at the WebSocket boundary, so this is mostly an integration job.
4. **Emotion/prosody signal** — Pyannote on the incoming PCM to detect frustration prosody, then nudge the FSM into "simplify" mode without waiting for two wrong answers.
5. **Persistent user model** — let the user say "I'm a beginner" or "I lived in Mexico" and have the system prompt adapt.
6. **Eval harness scale-up** — run scripted conversations through the full pipeline (not just unit tests), measure grader accuracy on a 100-case golden set, track regression on every change.

---

## 6. Known limitations

- **Edge TTS** uses an unofficial Microsoft endpoint. Rate-limiting or removal would break TTS; Piper TTS local fallback is designed but not wired.
- **Pronunciation feedback** is LLM-only — informed by STT confidence, but not phoneme-level. Specific feedback like "your 'r' was soft" comes from prompted heuristics, not measurement.
- **Lang switch** clears in-session state (history and FSM). Long-term progress persists.
- **Single user** (`USER_ID` from env). No auth.
- **Recovery from total STT outage** — the pipeline logs the error and continues accepting audio (Deepgram WebSocket auto-reconnects on next session), but mid-session loss surfaces as an `error` event to the client; we don't currently transparently reconnect during a single session.

---

## 7. Submission checklist

- [x] Public GitHub repo with all source
- [x] README with setup steps
- [x] `.env.example`
- [x] Mermaid architecture diagram (`docs/architecture.mmd`)
- [x] Eval harness (`evals/`, 5 test files, golden set)
- [x] Per-turn JSONL traces
- [x] Multi-persona handoff
- [x] Sub-target latency measured + documented
- [x] Two languages with config-only swap
- [x] SM-2 spaced repetition
- [ ] Demo video (to be recorded post-submission)

— Submitted with care.
