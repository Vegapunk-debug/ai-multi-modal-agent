"use client";
import { useEffect, useRef } from "react";
import clsx from "clsx";
import type { TranscriptLine } from "../lib/session";

type Props = {
  lines: TranscriptLine[];
  interim?: string;
};

export default function Transcript({ lines, interim }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines, interim]);

  return (
    <div
      ref={containerRef}
      className="glass rounded-2xl px-6 py-4 max-h-40 overflow-y-auto"
      style={{ minHeight: "120px" }}
    >
      <div className="text-xs uppercase tracking-[0.2em] text-muted mb-2 font-mono">Transcript</div>
      <div className="flex flex-col gap-2">
        {lines.slice(-8).map((line) => (
          <div
            key={line.id}
            className={clsx(
              "transcript-line flex gap-3 items-start",
              line.speaker === "user" ? "text-ink" : "text-teal/90",
            )}
          >
            <span
              className={clsx(
                "text-[10px] font-mono uppercase tracking-wider pt-1 w-12 shrink-0",
                line.speaker === "user" ? "text-muted" : "text-gold/70",
              )}
            >
              {line.speaker === "user" ? "You" : "Tutor"}
            </span>
            <span className="text-base leading-snug">
              {stripTags(line.text)}
              {line.language && (
                <span className="ml-2 text-[10px] font-mono text-muted">[{line.language}]</span>
              )}
            </span>
          </div>
        ))}
        {interim && (
          <div className="flex gap-3 items-start opacity-60">
            <span className="text-[10px] font-mono uppercase tracking-wider pt-1 w-12 shrink-0 text-muted">
              You
            </span>
            <span className="text-base leading-snug italic">{interim}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function stripTags(s: string): string {
  return s.replace(/<\/?(es|hi|en)>/g, "");
}
