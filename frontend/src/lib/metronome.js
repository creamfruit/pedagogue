import { audioContext, click } from "./synth.js";

const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD_S = 0.12;

export const MIN_BPM = 30;
export const MAX_BPM = 240;

export function clampBpm(value) {
  const number = Math.round(Number(value));
  if (!Number.isFinite(number)) return 80;
  return Math.min(MAX_BPM, Math.max(MIN_BPM, number));
}

export function bpmFromTaps(taps) {
  if (taps.length < 2) return null;
  const intervals = [];
  for (let i = 1; i < taps.length; i += 1) intervals.push(taps[i] - taps[i - 1]);
  const recent = intervals.slice(-4);
  const average = recent.reduce((sum, value) => sum + value, 0) / recent.length;
  return average > 0 ? clampBpm(60000 / average) : null;
}

export function createMetronome({ onBeat } = {}) {
  let bpm = 80;
  let beatsPerBar = 4;
  let accent = true;
  let volume = 0.7;
  let running = false;
  let ctx = null;
  let timer = null;
  let frame = null;
  let nextTime = 0;
  let beat = 0;
  const queue = [];

  function schedule() {
    while (nextTime < ctx.currentTime + SCHEDULE_AHEAD_S) {
      const isDownbeat = beat % beatsPerBar === 0;
      click(ctx, nextTime, { accent: accent && isDownbeat, volume });
      queue.push({ time: nextTime, index: beat % beatsPerBar });
      nextTime += 60 / bpm;
      beat += 1;
    }
  }

  function paint() {
    if (!running) return;
    while (queue.length && queue[0].time <= ctx.currentTime) {
      const due = queue.shift();
      if (onBeat) onBeat(due.index, beatsPerBar);
    }
    frame = requestAnimationFrame(paint);
  }

  return {
    get running() {
      return running;
    },
    get bpm() {
      return bpm;
    },
    setBpm(value) {
      bpm = clampBpm(value);
    },
    setBeatsPerBar(value) {
      beatsPerBar = Math.max(1, Math.min(12, Math.round(Number(value)) || 4));
    },
    setAccent(value) {
      accent = Boolean(value);
    },
    setVolume(value) {
      volume = Math.max(0, Math.min(1, Number(value)));
    },
    start() {
      if (running) return true;
      ctx = audioContext();
      if (!ctx) return false;
      running = true;
      beat = 0;
      queue.length = 0;
      nextTime = ctx.currentTime + 0.06;
      schedule();
      timer = setInterval(schedule, LOOKAHEAD_MS);
      frame = requestAnimationFrame(paint);
      return true;
    },
    stop() {
      running = false;
      clearInterval(timer);
      cancelAnimationFrame(frame);
      queue.length = 0;
      if (onBeat) onBeat(-1, beatsPerBar);
    },
  };
}
