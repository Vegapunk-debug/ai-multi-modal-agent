"use client";
import type { LessonMeta } from "../lib/session";

type Props = {
  lessons: LessonMeta[];
  activeLessonId: string | null;
  mode: string;
  personaName: string;
  difficulty?: string;
};

const MODE_LABELS: Record<string, string> = {
  idle: "Idle",
  teaching: "Lesson",
  quiz: "Quiz",
  conversation: "Conversation",
  doubt: "Resolving doubt",
  session_end: "Session ended",
};

export default function LessonCard({ lessons, activeLessonId, mode, personaName, difficulty }: Props) {
  const active = lessons.find((l) => l.id === activeLessonId);
  return (
    <div className="glass-strong rounded-2xl px-5 py-4 w-[300px]">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] uppercase tracking-[0.25em] text-muted font-mono">Mode</span>
        <span className="text-xs text-gold font-mono">{MODE_LABELS[mode] ?? mode}</span>
      </div>
      <div className="text-base font-medium text-ink mb-1">
        {active ? active.title : "No active lesson"}
      </div>
      <div className="text-xs text-muted mb-3">{personaName}</div>
      {difficulty && difficulty !== "maintain" && (
        <div
          className={
            "text-[10px] font-mono uppercase tracking-widest " +
            (difficulty === "advance" ? "text-teal" : "text-gold")
          }
        >
          {difficulty === "advance" ? "↑ advancing" : "↓ simplifying"}
        </div>
      )}
      <div className="mt-3 flex gap-1.5">
        {lessons.map((l) => (
          <div
            key={l.id}
            className={
              "h-1 flex-1 rounded-full transition-colors " +
              (l.id === activeLessonId ? "bg-gold" : "bg-white/8")
            }
            title={l.title}
          />
        ))}
      </div>
    </div>
  );
}
