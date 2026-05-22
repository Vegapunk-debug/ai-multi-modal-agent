"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Orb from "../components/Orb";
import Transcript from "../components/Transcript";
import LessonCard from "../components/LessonCard";
import InsightsPanel from "../components/InsightsPanel";
import { TutorSession, type TranscriptLine, type LessonMeta } from "../lib/session";

const PERSONA_COLORS: Record<string, string> = {
  teacher: "#e7c87a",         // warm gold
  examiner: "#6ee0c4",        // cool teal
  companion: "#a18cd1",       // violet
  english_narrator: "#9aa0bd",// neutral
  default: "#e7c87a",
};

export default function Home() {
  const [connected, setConnected] = useState(false);
  const [lang] = useState<"spanish">("spanish");
  const [persona, setPersona] = useState<{ key: string; name: string }>({
    key: "teacher",
    name: "Profesora Maya",
  });
  const [lessons, setLessons] = useState<LessonMeta[]>([]);
  const [activeLessonId, setActiveLessonId] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("idle");
  const [difficulty, setDifficulty] = useState<string>("maintain");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [interim, setInterim] = useState<string>("");
  const [ttsAmp, setTtsAmp] = useState(0);
  const [micLvl, setMicLvl] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [turnMetrics, setTurnMetrics] = useState<number[]>([]);
  const [ttfbMetrics, setTtfbMetrics] = useState<number[]>([]);
  const [statusText, setStatusText] = useState("Ready");

  const sessionRef = useRef<TutorSession | null>(null);

  const personaColor = PERSONA_COLORS[persona.key] || PERSONA_COLORS.default;

  const startSession = async () => {
    if (sessionRef.current) return;
    setStatusText("Connecting…");
    const session = new TutorSession({
      onConnected: () => {
        setConnected(true);
        setStatusText("Listening");
      },
      onTranscript: (line) => {
        if (line.speaker === "user") {
          if (line.isFinal) {
            setInterim("");
            setLines((ls) => [...ls, line]);
          } else {
            setInterim(line.text);
          }
        } else {
          setLines((ls) => [...ls, line]);
        }
      },
      onPersona: (key, name) => setPersona({ key, name }),
      onState: (s: any) => {
        if (typeof s.mode === "string") setMode(s.mode);
        if (typeof s.persona === "string") setPersona((p) => ({ ...p, key: s.persona }));
        if (s.lesson_id) setActiveLessonId(s.lesson_id);
        if (typeof s.difficulty_hint === "string") setDifficulty(s.difficulty_hint);
      },
      onAmplitude: (a) => setTtsAmp(a),
      onMicLevel: (rms) => setMicLvl(Math.min(1, rms * 12)),
      onSpeakingChange: (s) => setUserSpeaking(s),
      onMetrics: (m) => {
        if (m.turn_ms) setTurnMetrics((arr) => [...arr.slice(-50), m.turn_ms!]);
        if (m.tts_ttfb_ms) setTtfbMetrics((arr) => [...arr.slice(-50), m.tts_ttfb_ms!]);
      },
      onLessons: (ls) => setLessons(ls),
      onError: (e) => setStatusText("Error: " + e),
    });
    await session.connect("demo-user", lang);
    sessionRef.current = session;
  };

  const stopSession = () => {
    sessionRef.current?.disconnect();
    sessionRef.current = null;
    setConnected(false);
    setStatusText("Disconnected");
  };


  useEffect(() => {
    return () => {
      sessionRef.current?.disconnect();
    };
  }, []);

  const statusDot = useMemo(() => {
    if (!connected) return "bg-muted";
    if (speaking) return "bg-gold";
    if (userSpeaking) return "bg-teal";
    return "bg-violet/70";
  }, [connected, speaking, userSpeaking]);

  return (
    <main className="relative w-screen h-screen flex flex-col items-center justify-between p-8 select-none">
      {/* Top bar */}
      <header className="w-full max-w-6xl flex items-center justify-between fade-in">
        <div className="flex items-center gap-3">
          <div className="text-2xl font-semibold tracking-tight">
            Lingua<span className="text-gold">.</span>
          </div>
          <div className="text-xs text-muted font-mono uppercase tracking-[0.2em] ml-2">
            voice-first tutor
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className={`w-1.5 h-1.5 rounded-full ${statusDot} transition-colors`} />
          <span className="text-muted uppercase tracking-[0.2em]">{statusText}</span>
        </div>
      </header>

      <InsightsPanel
        metrics={{ turn_ms: turnMetrics, ttfb_ms: ttfbMetrics }}
      />

      {/* Center stage: orb */}
      <section className="flex-1 w-full flex items-center justify-center relative">
        <div className="relative flex flex-col items-center">
          <Orb
            amplitude={ttsAmp}
            micLevel={micLvl}
            personaColor={personaColor}
            speaking={speaking}
            userSpeaking={userSpeaking}
          />
          <div className="mt-6 text-center">
            <div className="text-sm tracking-wide font-medium" style={{ color: personaColor }}>
              {connected ? persona.name : "Ready to teach"}
            </div>
            <div className="text-xs text-muted mt-1 font-mono uppercase tracking-[0.2em]">
              {!connected
                ? "Press begin"
                : speaking
                  ? "Speaking…"
                  : userSpeaking
                    ? "Listening to you"
                    : "Your turn"}
            </div>
          </div>
        </div>

        {/* Right side: lesson card */}
        <div className="absolute right-12 top-1/2 -translate-y-1/2">
          <LessonCard
            lessons={lessons}
            activeLessonId={activeLessonId}
            mode={mode}
            personaName={persona.name}
            difficulty={difficulty}
          />
        </div>

        {/* Left side: language indicator */}
        <div className="absolute left-12 top-1/2 -translate-y-1/2">
          <div className="glass rounded-full px-4 py-2 text-sm text-gold flex items-center gap-2">
            <span className="text-[10px] font-mono opacity-60">ES</span>
            <span>Español</span>
          </div>
        </div>
      </section>

      {/* Bottom: transcript + control */}
      <footer className="w-full max-w-3xl flex flex-col gap-4">
        <Transcript lines={lines} interim={interim} />
        <div className="flex justify-center gap-3">
          {!connected ? (
            <button
              onClick={startSession}
              className="glass-strong px-8 py-3 rounded-full text-sm font-medium hover:text-gold transition"
            >
              Begin session
            </button>
          ) : (
            <>
              <SuggestionChip
                text="Teach me greetings"
                onClick={() => sessionRef.current?.sendText("Teach me greetings.")}
              />
              <SuggestionChip
                text="Quiz me"
                onClick={() => sessionRef.current?.sendText("Quiz me on what we covered.")}
              />
              <SuggestionChip
                text="Roleplay café"
                onClick={() => sessionRef.current?.sendText("Let's roleplay ordering at a café.")}
              />
              <button
                onClick={stopSession}
                className="text-xs text-muted hover:text-ink px-3 py-1.5"
              >
                End
              </button>
            </>
          )}
        </div>
      </footer>
    </main>
  );
}

function SuggestionChip({ text, onClick }: { text: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="glass rounded-full px-4 py-2 text-xs text-muted hover:text-ink transition"
    >
      {text}
    </button>
  );
}
