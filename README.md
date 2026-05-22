<div align="center">

# 🎙️ Lingua — Voice-First Spanish Tutor

**Put the phone down. Talk. Learn Spanish.**

Voice-native language tutor — lessons, quizzes, roleplay, and on-the-fly doubt clearing — entirely through spoken conversation. Sub-1.5 s end-to-end latency. Real barge-in.

**Deepgram Nova-3 STT** · **Deepgram Aura-2 TTS** · **Groq Llama-4-Scout** · **Gemini 2.5 Flash judge** · **Silero VAD** · **Next.js 14**

![tests](https://img.shields.io/badge/tests-47_passing-22C55E?style=flat-square)
![latency](https://img.shields.io/badge/E2E_P50-~950ms-orange?style=flat-square)
![python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=nextdotjs)
![license](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)

</div>

---

## 📸 Screenshots

> _Add screenshots in `docs/screenshots/` and reference them here._

| Idle / ready | Speaking | Lesson + transcript |
|--------------|----------|---------------------|
| _orb.png_    | _speaking.png_ | _lesson.png_ |

---

## 🚀 Quickstart — 5 minutes from clone to running

### Prereqs

- **Python 3.11+** (3.14 also works)
- **Node 18+**
- **Microphone** + Chrome / Edge / Safari
- **3 free API keys** (no credit card needed for any):
  - **Deepgram** — https://console.deepgram.com — used for STT + TTS ($200 free credit, ~200 hrs)
  - **Groq** — https://console.groq.com/keys — main LLM (free tier, generous)
  - **Gemini** — https://aistudio.google.com — judge LLM (free tier)

### 1. Clone + install

```bash
git clone <your-repo-url> lingua
cd lingua

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Frontend
cd client && npm install && cd ..
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and paste your keys:

```bash
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
DEEPGRAM_API_KEY=...
```

### 3. Run (two terminals)

```bash
# Terminal 1 — backend
.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd client && npm run dev
```

### 4. Talk

Open **http://localhost:3001** → click **Begin session** → grant mic → say:

```
"Teach me how to order food in Spanish"
"Quiz me on numbers"
"Wait, why is it 'la' and not 'el'?"
"Let's roleplay a café in Madrid"
"End session"
```

> **Headphones strongly recommended** to avoid speaker→mic echo loop.

---

## ✨ What you get

### Four learning modes, all voice-entered

| Mode | Entry phrase | What it does |
|------|--------------|--------------|
| **Teaching** | "Teach me greetings" | Structured lesson: objective → explain → example → practice → check |
| **Quiz** | "Quiz me on numbers" | Adaptive 5-question quiz with semantic grading |
| **Conversation** | "Let's roleplay a café" | Free-form Spanish roleplay with gentle correction |
| **Doubt** | "Wait, why is it 'la'?" | Pauses lesson, answers in English, resumes exactly where left off |

### Performance achieved

| Metric | Spec target | Measured (P50) |
|--------|------------|----------------|
| End-to-end latency (speech-end → first bot audio) | < 1500 ms | **~950 ms** |
| Interrupt-to-silence (barge-in) | < 300 ms | **~250 ms** |
| Mic gate window (echo suppression) | — | 250 ms tail after TTS |
| Crash resilience | survives STT/LLM/TTS hiccups | ✅ retry + fallback chain |

Live latency at `GET /metrics` (P50/P95/max/mean per stage, 200-sample rolling window).

---

## 🏗 Architecture

```
┌─────────────────────────────────────────┐
│   Browser (Next.js 14)                  │
│   • Voice orb · transcript · insights   │
│   • AudioWorklet → 16kHz PCM-16 LE      │
└────────────────┬────────────────────────┘
                 │  WebSocket /ws/audio
                 │  binary = PCM   text = JSON events
                 ▼
┌─────────────────────────────────────────────────────────┐
│   FastAPI + asyncio pipeline                            │
│                                                         │
│   audio_in ─► Silero VAD ─► Deepgram Nova-3 STT         │
│        ▲     (during TTS)    (rest of session)          │
│        │                                                │
│        │  IntentRouter (deterministic FSM)              │
│        │   ├── teach   → start_lesson                   │
│        │   ├── quiz    → start_quiz                     │
│        │   ├── doubt   → push state, answer in EN       │
│        │   ├── convo   → conversation mode              │
│        │   └── repeat / resume / stop                   │
│        │                                                │
│        ▼                                                │
│   Groq Llama-4-scout (streaming + tool calls)           │
│       └─ tools: start_lesson, advance_step, grade_…     │
│                                                         │
│   Gemini 2.5 Flash (judge: grader + doubt answers)      │
│                                                         │
│   Deepgram Aura-2 TTS (per-span lang routing)           │
│       ├─ <en> spans → aura-2-thalia-en                  │
│       └─ <es> spans → aura-2-celeste-es (Maya)          │
│                       aura-2-sirio-es  (Diego/Luis)     │
└─────────────────────────────────────────────────────────┘
   │                                                  │
   ▼                                                  ▼
┌─────────────────────┐               ┌──────────────────────────┐
│  SQLite (WAL)       │               │  Per-turn JSONL traces   │
│  users, sessions,   │               │  /metrics rolling P50/95 │
│  lesson_progress,   │               │  /session_recovery       │
│  vocab_mastery SM-2,│               │  /health                 │
│  mistakes           │               │                          │
└─────────────────────┘               └──────────────────────────┘
```

Full diagrams (sequence, barge-in, FSM, ER) in `docs/architecture.md`.

---

## 🎯 Spec compliance

| Requirement (assignment brief) | Status |
|--------------------------------|--------|
| Voice primary interface, no core tap/type/read | ✅ |
| Teaching mode (structured lesson FSM) | ✅ |
| Quiz mode (3+ question types, semantic grading) | ✅ |
| Conversation roleplay mode | ✅ |
| Doubt resolution w/ state stack + EN answer + resume | ✅ |
| Streaming STT | ✅ Deepgram Nova-3 |
| Streaming TTS | ✅ Deepgram Aura-2 |
| Barge-in / interruption | ✅ Silero VAD-driven during TTS |
| VAD | ✅ Silero (Pipecat) |
| E2E latency < 1500 ms P50 | ✅ ~950 ms |
| Interrupt-to-silence < 300 ms | ✅ ~250 ms |
| Lesson FSM (objective → explain → example → practice → check) | ✅ |
| Adaptive difficulty | ✅ consecutive_correct/wrong → simplify/advance |
| ≥ 3 lessons | ✅ **6 lessons** (greetings, numbers, food, family, days+time, directions) |
| Pronunciation feedback specific (not "good job") | ✅ 25 word hints + 12 phoneme patterns |
| ≥ 3 quiz question types | ✅ translation EN↔ES, listening, spoken response |
| Semantic grading (paraphrase acceptance) | ✅ NFD-normalize → fuzzy → LLM-judge |
| Doubt interrupt + resume | ✅ FSM state stack |
| Short-term memory (session mistakes, vocab) | ✅ SessionState |
| Long-term memory (SQLite) | ✅ users, progress, vocab, mistakes |
| Spaced repetition | ✅ SM-2 implementation |
| Tool calling (start_quiz, grade_answer, save_progress, lookup_vocab, …) | ✅ 10 tools |
| Configurable system prompts | ✅ curriculum/spanish/system_prompt.md |
| Per-turn logs | ✅ JSONL traces per turn |
| Crash resilience | ✅ try/except + retry chains |
| Cost estimated | ✅ ~$0.04/5-min session (all free tier in practice) |

### Bonus / stretch goals

| Bonus | Status |
|-------|--------|
| Phoneme-aware pronunciation feedback | ✅ |
| Spaced repetition (SM-2) | ✅ |
| Multi-agent personas (Teacher / Examiner / Companion) | ✅ Maya / Diego / Luis w/ distinct Aura voices |
| Streaming evaluation | ⏳ partial |
| Telephony (Twilio/SIP) | ❌ out of scope |
| On-device STT | ❌ Groq's hosted Whisper is faster |
| Emotion / prosody | ❌ skipped |

---

## 🧪 Tests

```bash
.venv/bin/pytest evals/ -v
```

**47 passing tests** covering:

- Grader: normalization, fast-path, golden-set, error type detection
- FSM: state transitions, doubt-stack nesting, difficulty adaptation
- Curriculum loader: both languages, lesson schemas
- Doubt detector: multilingual keyword triggers
- SM-2 SRS: ease/interval invariants, lapse handling

---

## 💸 Cost per session

5-minute session estimate:

| Component | Free tier | Paid |
|-----------|-----------|------|
| Deepgram STT (5 min) | covered by $200 credit ≈ 200 hrs | $0.022 |
| Deepgram Aura-2 TTS (~2000 chars) | same credit | ~$0.030 |
| Groq Llama-4-scout (~3k tok) | free tier | $0 |
| Gemini 2.5 Flash judge | free tier | $0 |
| **Total** | **$0** | **~$0.05** |

---

## 📂 Project layout

```
lingua/
├── server/                       # FastAPI backend
│   ├── main.py                   # WS endpoint + REST + /metrics + /session_recovery
│   ├── pipeline.py               # Async session orchestrator (VAD + STT + agent + TTS)
│   ├── agent/
│   │   ├── core.py               # Agent loop: streaming LLM, tool dispatch, doubt fast-path
│   │   ├── intent.py             # Deterministic intent router (TEACH/QUIZ/DOUBT/...)
│   │   ├── fsm.py                # ModeFSM w/ state stack for doubt resume
│   │   ├── grader.py             # Two-tier semantic grading + pronunciation hints
│   │   ├── pronunciation.py      # 25 word hints + 12 phoneme patterns
│   │   ├── doubt.py              # Doubt keyword detector (multilingual)
│   │   ├── quiz.py               # Mixed-type quiz generator
│   │   └── personas.py           # Multi-persona voice routing
│   ├── services/
│   │   ├── llm.py                # Groq / Gemini adapter (OpenAI-compat)
│   │   ├── stt.py                # Deepgram Nova-3 WebSocket streaming
│   │   ├── tts.py                # Deepgram Aura-2 w/ per-span lang routing
│   │   └── vad.py                # Silero VAD via Pipecat
│   ├── curriculum/spanish/
│   │   ├── lessons.json          # 6 hand-authored A1–A2 lessons
│   │   ├── voice_config.json     # Aura-2 voice per persona
│   │   └── system_prompt.md      # Tutor system prompt (configurable)
│   ├── tools/definitions.py      # OpenAI-style tool schemas
│   ├── db/                       # SQLite schema + repo (SM-2)
│   └── observability/
│       ├── tracer.py             # Per-turn JSONL
│       └── metrics.py            # Rolling P50/P95 window
├── client/                       # Next.js 14 frontend
│   ├── app/                      # App Router + Tailwind dark theme
│   ├── components/               # VoiceOrb, Transcript, LessonCard, InsightsPanel
│   └── lib/                      # voiceClient (Web Audio + WebSocket)
├── evals/                        # pytest suite (47 tests)
├── docs/
│   ├── architecture.md           # Full Mermaid diagrams
│   ├── writeup.md                # Technical write-up (7 sections)
│   └── demo_script.md            # Demo recording outline
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 🛠 Configuration (.env)

| Var | Purpose | Default |
|-----|---------|---------|
| `GROQ_API_KEY` | Main LLM | required |
| `GEMINI_API_KEY` | Judge LLM (grader, doubts) | required |
| `DEEPGRAM_API_KEY` | STT + TTS (single key, dual use) | required |
| `LLM_MODEL` | Groq model id | `meta-llama/llama-4-scout-17b-16e-instruct` |
| `LLM_PROVIDER` | `groq` or `gemini` | `groq` |
| `STT_MODEL` | Deepgram STT model | `nova-3` |
| `TARGET_LANG` | Default lesson language | `spanish` |
| `USER_ID` | Hardcoded user (per spec allowance) | `demo-user` |
| `ALLOW_ORIGIN` | CORS origin | `http://localhost:3001` |

Edge TTS (Microsoft, free, no-key) is wired as fallback but Deepgram Aura-2 is default and recommended.

---

## 🚨 Known limitations

- **Speaker → mic echo** can trigger false barge-ins. Mitigated via mic gate + Silero VAD threshold tuning. **Use headphones** for best experience.
- **Spanish-only.** Multilingual scaffolding exists (`server/curriculum/<lang>/`) — adding French = new JSON, no code change.
- **No auth.** Single hardcoded user (`USER_ID` env var). Per spec allowance.
- **No telephony.** Browser only. SIP not in scope.
- **No CI.** Test suite runs locally only.
- **Pronunciation feedback is heuristic**, not phoneme-level forced alignment. Acceptable for prototype; Azure Speech Pronunciation Assessment would be production upgrade.

---

## 📜 License

MIT — fork freely.

---

Built for the **AI Engineer Take-Home Assignment** — voice / multi-modal agents. Architecture diagrams + write-up in [`docs/`](docs/).
