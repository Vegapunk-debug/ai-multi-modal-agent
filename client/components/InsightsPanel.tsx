"use client";
import { useState } from "react";

type Metrics = {
  turn_ms: number[];
  ttfb_ms: number[];
};

type Props = {
  metrics: Metrics;
  weakAreas?: { error_type: string; count: number }[];
};

export default function InsightsPanel({ metrics, weakAreas }: Props) {
  const [open, setOpen] = useState(false);
  const p = (arr: number[], q: number) => {
    if (!arr.length) return "—";
    const s = [...arr].sort((a, b) => a - b);
    const idx = Math.min(s.length - 1, Math.floor((s.length - 1) * q));
    return `${Math.round(s[idx])}ms`;
  };

  return (
    <div className="absolute top-6 right-6 z-20">
      <button
        onClick={() => setOpen((v) => !v)}
        className="glass rounded-full px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] font-mono text-muted hover:text-ink transition"
      >
        {open ? "Hide" : "Insights"}
      </button>
      {open && (
        <div className="glass-strong rounded-2xl p-5 mt-3 w-[280px] fade-in">
          <div className="text-[10px] uppercase tracking-[0.25em] text-muted font-mono mb-3">
            Latency
          </div>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Stat label="P50 turn" value={p(metrics.turn_ms, 0.5)} />
            <Stat label="P95 turn" value={p(metrics.turn_ms, 0.95)} />
            <Stat label="P50 TTFB" value={p(metrics.ttfb_ms, 0.5)} />
          </div>
          {weakAreas && weakAreas.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-[0.25em] text-muted font-mono mb-2">
                Weak areas
              </div>
              <div className="flex flex-wrap gap-2">
                {weakAreas.map((w) => (
                  <div
                    key={w.error_type}
                    className="text-xs px-2 py-1 rounded bg-white/5 text-violet"
                  >
                    {w.error_type} × {w.count}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] text-muted font-mono uppercase tracking-wider">{label}</span>
      <span className="text-sm text-ink font-mono">{value}</span>
    </div>
  );
}
