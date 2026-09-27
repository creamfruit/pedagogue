import { audioContext } from "./synth.js";

const SAMPLE_NAMES = {
  21: "A0", 24: "C1", 27: "Ds1", 30: "Fs1", 33: "A1", 36: "C2", 39: "Ds2", 42: "Fs2", 45: "A2",
  48: "C3", 51: "Ds3", 54: "Fs3", 57: "A3", 60: "C4", 63: "Ds4", 66: "Fs4", 69: "A4", 72: "C5",
  75: "Ds5", 78: "Fs5", 81: "A5", 84: "C6", 87: "Ds6", 90: "Fs6", 93: "A6", 96: "C7", 99: "Ds7",
  102: "Fs7", 105: "A7", 108: "C8",
};
const SAMPLE_BASE = `${import.meta.env.BASE_URL || "/"}samples/piano/`;
const RELEASE_SECONDS = 0.35;
const DEFAULT_VELOCITY = 78;

const buffers = new Map();
const pending = new Map();
let master = null;

function nearestSample(midi) {
  const clamped = Math.min(108, Math.max(21, midi));
  return 21 + Math.round((clamped - 21) / 3) * 3;
}

function output(ctx) {
  if (master && master.context === ctx) return master;
  const compressor = ctx.createDynamicsCompressor();
  compressor.threshold.value = -14;
  compressor.knee.value = 12;
  compressor.ratio.value = 3;
  compressor.attack.value = 0.004;
  compressor.release.value = 0.2;
  const gain = ctx.createGain();
  gain.gain.value = 0.9;
  gain.connect(compressor).connect(ctx.destination);
  master = gain;
  return master;
}

function loadSample(ctx, sample) {
  if (buffers.has(sample)) return Promise.resolve(buffers.get(sample));
  if (pending.has(sample)) return pending.get(sample);
  const promise = fetch(`${SAMPLE_BASE}${SAMPLE_NAMES[sample]}.mp3`)
    .then((response) => {
      if (!response.ok) throw new Error(`piano sample ${SAMPLE_NAMES[sample]} missing`);
      return response.arrayBuffer();
    })
    .then((data) => new Promise((resolve, reject) => ctx.decodeAudioData(data, resolve, reject)))
    .then((buffer) => {
      buffers.set(sample, buffer);
      pending.delete(sample);
      return buffer;
    })
    .catch((error) => {
      pending.delete(sample);
      throw error;
    });
  pending.set(sample, promise);
  return promise;
}

export function preparePiano(midis) {
  const ctx = audioContext();
  if (!ctx) return Promise.reject(new Error("Audio is not available in this browser"));
  const samples = [...new Set(midis.map(nearestSample))];
  return Promise.all(samples.map((sample) => loadSample(ctx, sample)));
}

function strike(ctx, destination, midi, velocity, at, seconds) {
  const sample = nearestSample(midi);
  const buffer = buffers.get(sample);
  if (!buffer) return null;
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.playbackRate.value = Math.pow(2, (midi - sample) / 12);
  const gain = ctx.createGain();
  const level = Math.pow(Math.min(Math.max(velocity, 1), 127) / 127, 1.5) * 0.95;
  const releaseAt = at + Math.max(seconds, 0.06);
  gain.gain.setValueAtTime(level, at);
  gain.gain.setValueAtTime(level, releaseAt);
  gain.gain.exponentialRampToValueAtTime(0.0001, releaseAt + RELEASE_SECONDS);
  source.connect(gain).connect(destination);
  source.start(at);
  source.stop(releaseAt + RELEASE_SECONDS + 0.05);
  return source;
}

export function playEvents(events, { tempo = 90, onDone, onStart, onProgress, lead = 0.08 } = {}) {
  const ctx = audioContext();
  const secondsPerBeat = 60 / tempo;
  const end = events.reduce((latest, event) => Math.max(latest, event[0] + Math.max(event[5] ?? event[1], event[1])), 0);
  const durationMs = end * secondsPerBeat * 1000 + RELEASE_SECONDS * 1000;
  const sources = [];
  const timers = [];
  let stopped = false;
  let raf = null;

  const ready = ctx
    ? preparePiano(events.map((event) => event[2])).then(() => {
        if (stopped) return;
        const destination = output(ctx);
        const origin = ctx.currentTime + lead;
        events.forEach(([beat, length, midi, velocity, , sound]) => {
          const at = origin + beat * secondsPerBeat;
          const seconds = Math.max(sound ?? length, length) * secondsPerBeat;
          const source = strike(ctx, destination, midi, velocity || DEFAULT_VELOCITY, at, seconds);
          if (source) sources.push(source);
        });
        if (onStart) onStart();
        if (onProgress) {
          const tick = () => {
            if (stopped) return;
            const elapsed = (ctx.currentTime - origin) / secondsPerBeat;
            onProgress(Math.max(0, elapsed));
            if (elapsed < end) raf = requestAnimationFrame(tick);
          };
          raf = requestAnimationFrame(tick);
        }
        timers.push(setTimeout(() => {
          if (!stopped && onDone) onDone();
        }, durationMs + lead * 1000));
      })
    : Promise.reject(new Error("Audio is not available in this browser"));

  ready.catch(() => {
    if (!stopped && onDone) onDone();
  });

  return {
    durationMs,
    ready,
    stop: () => {
      stopped = true;
      timers.forEach(clearTimeout);
      if (raf) cancelAnimationFrame(raf);
      const now = ctx ? ctx.currentTime : 0;
      sources.forEach((source) => {
        try {
          source.stop(now + 0.05);
        } catch {
          return;
        }
      });
    },
  };
}
