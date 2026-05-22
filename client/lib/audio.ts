// Mic capture + PCM16 16k resampling for Deepgram, and MP3 audio playback queue.

export type MicConfig = {
  sampleRate: number;
  onPCM: (pcm16: ArrayBuffer) => void;
  onLevel?: (rms: number) => void;
  onVAD?: (speaking: boolean) => void;
};

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private worklet: AudioWorkletNode | null = null;
  private cfg: MicConfig;
  private vadActive = false;
  private vadStreak = 0;
  private silentStreak = 0;

  constructor(cfg: MicConfig) {
    this.cfg = cfg;
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 48000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.ctx = new AudioContext({ sampleRate: 48000 });

    const workletCode = `
      class Pcm16Worklet extends AudioWorkletProcessor {
        constructor() {
          super();
          this.targetRate = ${this.cfg.sampleRate};
          this.acc = 0;
        }
        process(inputs) {
          const input = inputs[0];
          if (!input || !input[0]) return true;
          const ch0 = input[0];
          const ratio = sampleRate / this.targetRate;
          const out = new Int16Array(Math.floor(ch0.length / ratio));
          let level = 0;
          for (let i = 0; i < out.length; i++) {
            const idx = Math.floor(i * ratio);
            let s = ch0[idx];
            if (s > 1) s = 1; if (s < -1) s = -1;
            level += s * s;
            out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          const rms = Math.sqrt(level / Math.max(1, out.length));
          this.port.postMessage({ pcm: out.buffer, rms }, [out.buffer]);
          return true;
        }
      }
      registerProcessor("pcm16-worklet", Pcm16Worklet);
    `;
    const blob = new Blob([workletCode], { type: "application/javascript" });
    await this.ctx.audioWorklet.addModule(URL.createObjectURL(blob));
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(this.ctx, "pcm16-worklet");
    this.worklet.port.onmessage = (ev) => {
      const { pcm, rms } = ev.data;
      this.cfg.onPCM(pcm);
      if (this.cfg.onLevel) this.cfg.onLevel(rms);
      this.detectVAD(rms);
    };
    src.connect(this.worklet);
    // Connect to a dummy node so the worklet ticks (silent).
    const silent = this.ctx.createGain();
    silent.gain.value = 0;
    this.worklet.connect(silent).connect(this.ctx.destination);
  }

  private detectVAD(rms: number) {
    // Tuned to ignore typing/breath/HVAC noise. Real speech rarely sits below 0.07 RMS
    // after the AGC enabled in getUserMedia. Long streak avoids brief clicks.
    const T = 0.07;
    if (rms > T) {
      this.vadStreak++;
      this.silentStreak = 0;
      if (!this.vadActive && this.vadStreak > 8) {
        this.vadActive = true;
        this.cfg.onVAD?.(true);
      }
    } else {
      this.silentStreak++;
      this.vadStreak = 0;
      if (this.vadActive && this.silentStreak > 40) {
        this.vadActive = false;
        this.cfg.onVAD?.(false);
      }
    }
  }

  stop() {
    this.worklet?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.ctx = null;
    this.stream = null;
    this.worklet = null;
  }
}

// --- Playback queue using MediaSource for streaming MP3 ---

export class AudioPlayer {
  private audioEl: HTMLAudioElement;
  private mediaSource: MediaSource;
  private sourceBuffer: SourceBuffer | null = null;
  private queue: ArrayBuffer[] = [];
  private ready = false;
  private currentRMS = 0;
  private analyser: AnalyserNode | null = null;
  private ctx: AudioContext | null = null;

  onAmplitude?: (a: number) => void;

  constructor() {
    this.audioEl = new Audio();
    this.audioEl.autoplay = true;
    this.mediaSource = new MediaSource();
    this.audioEl.src = URL.createObjectURL(this.mediaSource);
    this.mediaSource.addEventListener("sourceopen", () => this.onSourceOpen());
  }

  private onSourceOpen() {
    try {
      this.sourceBuffer = this.mediaSource.addSourceBuffer("audio/mpeg");
    } catch (err) {
      console.error("Failed to add SourceBuffer", err);
      return;
    }
    this.sourceBuffer.addEventListener("updateend", () => this.flush());
    this.ready = true;
    this.flush();
    this.attachAnalyser();
  }

  private attachAnalyser() {
    try {
      this.ctx = new AudioContext();
      const src = this.ctx.createMediaElementSource(this.audioEl);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      src.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
      const buf = new Uint8Array(this.analyser.frequencyBinCount);
      const tick = () => {
        if (!this.analyser) return;
        this.analyser.getByteFrequencyData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length) / 255;
        this.currentRMS = rms;
        this.onAmplitude?.(rms);
        requestAnimationFrame(tick);
      };
      tick();
    } catch (e) {
      console.warn("analyser attach failed", e);
    }
  }

  private flush() {
    if (!this.ready || !this.sourceBuffer || this.sourceBuffer.updating) return;
    const chunk = this.queue.shift();
    if (chunk) {
      try {
        this.sourceBuffer.appendBuffer(chunk);
      } catch (e) {
        console.warn("appendBuffer failed", e);
      }
    }
  }

  feed(chunk: ArrayBuffer) {
    this.queue.push(chunk);
    this.flush();
  }

  stop() {
    this.queue = [];
    try {
      this.audioEl.pause();
    } catch {}
    try {
      if (this.sourceBuffer && !this.sourceBuffer.updating) {
        this.sourceBuffer.abort();
      }
    } catch {}
  }
}
