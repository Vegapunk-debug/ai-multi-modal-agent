// WebSocket session manager. Bridges MicCapture <-> backend <-> AudioPlayer.

import { MicCapture, AudioPlayer } from "./audio";

export type Persona = { name: string; voice_id: string };
export type LessonMeta = { id: string; title: string };

export type TranscriptLine = {
  id: string;
  speaker: "user" | "assistant";
  text: string;
  language?: string;
  isFinal: boolean;
  ts: number;
};

export type SessionEvents = {
  onTranscript?: (line: TranscriptLine) => void;
  onPersona?: (key: string, name: string) => void;
  onState?: (state: Record<string, unknown>) => void;
  onAmplitude?: (a: number) => void;
  onMicLevel?: (rms: number) => void;
  onMetrics?: (m: { turn_ms?: number; tts_ttfb_ms?: number }) => void;
  onLessons?: (lessons: LessonMeta[]) => void;
  onError?: (msg: string) => void;
  onConnected?: () => void;
  onSpeakingChange?: (speaking: boolean) => void;
};

export class TutorSession {
  private ws: WebSocket | null = null;
  private mic: MicCapture | null = null;
  private player: AudioPlayer = new AudioPlayer();
  private cb: SessionEvents;
  private connected = false;
  private speaking = false;
  private currentLine: TranscriptLine | null = null;
  private wsUrl: string;
  private lastTtsStart = 0;

  constructor(opts: SessionEvents & { wsUrl?: string }) {
    this.cb = opts;
    this.wsUrl = opts.wsUrl || (process.env.NEXT_PUBLIC_WS_URL as string) || "ws://localhost:8000/ws/audio";
    this.player.onAmplitude = (a) => this.cb.onAmplitude?.(a);
  }

  async connect(userId: string, lang: string) {
    const url = `${this.wsUrl}?user_id=${encodeURIComponent(userId)}&lang=${encodeURIComponent(lang)}`;
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";
    this.ws.onopen = () => {
      this.connected = true;
      this.cb.onConnected?.();
    };
    this.ws.onmessage = (ev) => this.handleMessage(ev);
    this.ws.onerror = (ev) => this.cb.onError?.("WebSocket error");
    this.ws.onclose = () => {
      this.connected = false;
    };

    this.mic = new MicCapture({
      sampleRate: 16000,
      onPCM: (buf) => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(buf);
        }
      },
      onLevel: (rms) => this.cb.onMicLevel?.(rms),
      onVAD: (speaking) => {
        if (speaking && this.speaking) {
          // Barge-in suppressed for the first 300ms of TTS only — long enough
          // that ambient noise on TTS start doesn't kill it, short enough that
          // user can interrupt almost immediately.
          const tts_age = Date.now() - this.lastTtsStart;
          if (tts_age > 300) {
            this.sendControl({ type: "user_speech_start" });
          }
        }
        this.cb.onSpeakingChange?.(speaking);
      },
    });
    await this.mic.start();
  }

  switchLang(lang: string) {
    this.sendControl({ type: "switch_lang", lang });
  }

  sendText(text: string) {
    this.sendControl({ type: "user_text", text });
  }

  private sendControl(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private handleMessage(ev: MessageEvent) {
    if (typeof ev.data === "string") {
      try {
        const msg = JSON.parse(ev.data);
        this.handleJson(msg);
      } catch {}
    } else if (ev.data instanceof ArrayBuffer) {
      this.player.feed(ev.data);
    }
  }

  private handleJson(msg: Record<string, any>) {
    switch (msg.type) {
      case "session_started":
        if (msg.lessons) this.cb.onLessons?.(msg.lessons);
        break;
      case "transcript": {
        const line: TranscriptLine = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          speaker: "user",
          text: (msg.text || "").trim(),
          language: msg.language,
          isFinal: !!msg.is_final,
          ts: Date.now(),
        };
        this.cb.onTranscript?.(line);
        break;
      }
      case "tts_start": {
        this.speaking = true;
        this.lastTtsStart = Date.now();
        this.cb.onPersona?.(msg.persona, msg.persona_name);
        const line: TranscriptLine = {
          id: `${Date.now()}-a`,
          speaker: "assistant",
          text: msg.text || "",
          isFinal: true,
          ts: Date.now(),
        };
        this.cb.onTranscript?.(line);
        break;
      }
      case "tts_end":
        this.speaking = false;
        break;
      case "tts_cancelled":
        this.speaking = false;
        this.player.stop();
        break;
      case "state":
        this.cb.onState?.(msg);
        break;
      case "metrics":
        this.cb.onMetrics?.({ turn_ms: msg.turn_ms });
        break;
      case "tts_ttfb_ms":
        this.cb.onMetrics?.({ tts_ttfb_ms: msg.ms });
        break;
      case "error":
        this.cb.onError?.(msg.msg || msg.err || "unknown");
        break;
    }
  }

  disconnect() {
    this.mic?.stop();
    this.player.stop();
    this.ws?.close();
  }
}
