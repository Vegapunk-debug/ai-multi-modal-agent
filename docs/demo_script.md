# Demo Video Script (4 min)

Record at 1080p, ~30s buffer beginning and end. Use OBS or QuickTime. Mic close, headphones on to avoid feedback.

## Scene 1 — Cold open (0:00–0:20)
- Black screen. Open browser to `localhost:3000`.
- Click **Begin session**, allow mic.
- Orb fades in, gold. Profesora Maya: "Hola, soy Maya. ¿Lista para aprender?"
- Voice-over (text overlay): **"Lingua — a voice-first tutor"**.

## Scene 2 — Teaching loop (0:20–1:10)
- Say: **"Teach me how to order food in Spanish."**
- Watch the orb pulse. Lesson card updates to "Pedir comida".
- Maya: explains "Quisiera", says "Quisiera un café, por favor."
- You repeat. Maya gives specific feedback.
- Show insights panel: P50 turn latency ~770 ms.

## Scene 3 — Doubt interrupt (1:10–1:50)
- Mid-explanation, interrupt: **"Wait, why is it 'la cuenta' and not 'el cuenta'?"**
- TTS cancels mid-sentence (barge-in). Orb shifts to neutral grey (English narrator).
- Tutor answers in English (≤3 sentences).
- Mode chip flips back to "Lesson", orb returns to gold. Tutor resumes exactly where she left off.

## Scene 4 — Quiz handoff (1:50–2:30)
- Say: **"Quiz me on what we covered."**
- Maya: "Diego will take it from here."
- Voice changes — orb shifts to teal (Examinador Diego).
- Diego asks three questions: translate-EN-to-ES, listening, spoken response.
- Show acceptance of paraphrase: "I would like a coffee" vs "I'd like coffee please".

## Scene 5 — Code-switch (2:30–2:50)
- Mid-roleplay sentence, mix Spanish and English: **"Quisiera... what's the word for water again?"**
- Watch transcript: Deepgram correctly tags `[es]` and `[en]` spans.
- Tutor handles it cleanly.

## Scene 6 — Hindi switch (2:50–3:30)
- Click Hindi pill / say: **"Switch to Hindi."**
- Brief reload, lesson list changes.
- Guru Priya: "Namaste! Hindi mein swagat hai."
- One-question taste: "Say 'thank you' in Hindi."

## Scene 7 — Error recovery (3:30–4:00)
- Open another terminal: `kill -9 $(pgrep -f "deepgram")` — or simulate via dev override.
- Continue speaking. Pipeline logs error, client receives error toast, reconnects on next session.
- Show traces file: `tail traces/<session>.jsonl | jq .`
- End: **"~770 ms P50 latency. Free-tier stack. Two languages. Architecture is config-driven."**
- Fade out.

## Pre-record checklist
- [ ] `.env` filled with valid Groq + Deepgram keys
- [ ] Both server and client running (`make server` + `make client`)
- [ ] Test all four utterances above resolve correctly
- [ ] Headphones on
- [ ] Browser zoom 110%, system audio level moderate
