"use client";
import { useEffect, useRef } from "react";

type Props = {
  amplitude: number;       // 0..1 from TTS playback
  micLevel: number;        // 0..1 mic RMS
  personaColor: string;    // hex
  speaking: boolean;
  userSpeaking: boolean;
};

// ChatGPT-voice-style sphere + Siri-style equalizer bars.
// Compact (220px). Driven by amplitude (agent) and micLevel (user).
export default function Orb({
  amplitude,
  micLevel,
  personaColor,
  speaking,
  userSpeaking,
}: Props) {
  const energy = Math.min(1, amplitude + micLevel);
  const active = speaking || userSpeaking;

  return (
    <div className="flex flex-col items-center gap-8">
      {/* Sphere */}
      <div className="relative w-[220px] h-[220px] flex items-center justify-center">
        {/* Outer pulse ring (listening cue) */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            border: `1px solid ${personaColor}33`,
            transform: `scale(${1 + energy * 0.35})`,
            opacity: active ? 0.8 : 0.3,
            transition: "transform 140ms ease-out, opacity 300ms ease-out",
          }}
        />
        <div
          className="absolute inset-2 rounded-full"
          style={{
            border: `1px solid ${personaColor}22`,
            transform: `scale(${1 + energy * 0.2})`,
            opacity: active ? 0.5 : 0.15,
            transition: "transform 200ms ease-out, opacity 400ms ease-out",
          }}
        />

        {/* The sphere itself — conic + radial gradient, ChatGPT-voice feel */}
        <div
          className="relative w-[180px] h-[180px] rounded-full overflow-hidden animate-breathe"
          style={{
            background: `
              radial-gradient(circle at 35% 30%, ${personaColor}ee 0%, ${personaColor}66 35%, ${personaColor}11 75%, transparent 100%),
              conic-gradient(from ${energy * 360}deg at 50% 50%, ${personaColor}88, #ffffff10, ${personaColor}66, ${personaColor}aa, ${personaColor}88)
            `,
            boxShadow: `
              0 0 80px ${personaColor}55,
              0 0 40px ${personaColor}88,
              inset 0 0 60px ${personaColor}33,
              inset 0 0 20px ${personaColor}88
            `,
            transform: `scale(${1 + energy * 0.12})`,
            transition: "transform 100ms ease-out, box-shadow 200ms ease-out",
          }}
        >
          {/* Inner spin — flowing highlight */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `conic-gradient(from 0deg, transparent, ${personaColor}55 40%, transparent 60%, ${personaColor}33 80%, transparent)`,
              animation: `spin ${10 - energy * 6}s linear infinite`,
              opacity: 0.7 + energy * 0.3,
            }}
          />
          {/* Soft inner core highlight */}
          <div
            className="absolute inset-[20%] rounded-full"
            style={{
              background: `radial-gradient(circle at 40% 35%, #ffffff${active ? "55" : "22"}, transparent 60%)`,
              filter: "blur(8px)",
            }}
          />
          {/* Liquid distortion — animated displacement via SVG filter */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `radial-gradient(ellipse at ${50 + Math.sin(Date.now() / 600) * 15}% ${50 + Math.cos(Date.now() / 700) * 15}%, ${personaColor}66, transparent 50%)`,
              mixBlendMode: "screen",
              opacity: 0.6 + energy * 0.4,
            }}
          />
        </div>

        {/* Outer glow halo */}
        <div
          className="absolute inset-[-30%] rounded-full pointer-events-none -z-10"
          style={{
            background: `radial-gradient(circle, ${personaColor}55 0%, transparent 55%)`,
            filter: "blur(40px)",
            opacity: 0.4 + energy * 0.6,
          }}
        />
      </div>

      {/* Siri-style equalizer bars */}
      <EqualizerBars
        amplitude={amplitude}
        micLevel={micLevel}
        personaColor={personaColor}
        active={active}
      />
    </div>
  );
}

function EqualizerBars({
  amplitude,
  micLevel,
  personaColor,
  active,
}: {
  amplitude: number;
  micLevel: number;
  personaColor: string;
  active: boolean;
}) {
  const heightsRef = useRef<number[]>(new Array(9).fill(0.2));
  const containerRef = useRef<HTMLDivElement>(null);
  const targetRef = useRef({ amplitude: 0, mic: 0 });

  useEffect(() => {
    targetRef.current.amplitude = amplitude;
    targetRef.current.mic = micLevel;
  }, [amplitude, micLevel]);

  useEffect(() => {
    let raf = 0;
    let phase = 0;
    const animate = () => {
      phase += 0.08;
      const energy = Math.min(1, targetRef.current.amplitude + targetRef.current.mic);
      const idle = 0.15 + Math.sin(phase * 0.5) * 0.05;

      const newHeights = heightsRef.current.map((h, i) => {
        const center = 4; // bar index
        const distFromCenter = Math.abs(i - center) / center;
        // Bars near center react stronger; sine waves create natural shimmer
        const wave1 = Math.sin(phase + i * 0.7) * 0.5 + 0.5;
        const wave2 = Math.sin(phase * 1.3 + i * 1.1) * 0.5 + 0.5;
        const reactive = energy * (1 - distFromCenter * 0.5) * (0.55 + wave1 * 0.45);
        const noise = (Math.random() - 0.5) * energy * 0.25;
        const target = idle + reactive + wave2 * energy * 0.4 + noise;
        return h + (Math.min(1, Math.max(0.12, target)) - h) * 0.35;
      });
      heightsRef.current = newHeights;

      // Apply to DOM imperatively to avoid React render storm
      if (containerRef.current) {
        const bars = containerRef.current.children;
        for (let i = 0; i < bars.length; i++) {
          (bars[i] as HTMLElement).style.transform = `scaleY(${newHeights[i]})`;
          (bars[i] as HTMLElement).style.opacity = active ? "1" : "0.5";
        }
      }

      raf = requestAnimationFrame(animate);
    };
    animate();
    return () => cancelAnimationFrame(raf);
  }, [active]);

  return (
    <div
      ref={containerRef}
      className="flex items-center gap-1.5 h-12"
      style={{ minHeight: "48px" }}
    >
      {Array.from({ length: 9 }).map((_, i) => (
        <div
          key={i}
          className="rounded-full transition-opacity duration-300"
          style={{
            width: "4px",
            height: "100%",
            background: `linear-gradient(180deg, ${personaColor}, ${personaColor}55)`,
            transformOrigin: "center",
            transform: "scaleY(0.2)",
            boxShadow: `0 0 8px ${personaColor}66`,
          }}
        />
      ))}
    </div>
  );
}
