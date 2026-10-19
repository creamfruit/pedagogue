import { createLiveMatcher, createWaitMatcher, groupReference, localSummary } from "./keyboardMatch.js";
import { audioContext, click } from "./synth.js";

export const MAX_NOTES = 3000;
export const LEAD_IN_BEATS = 0.6;
const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD_S = 0.12;
const START_LEAD_S = 0.12;

export function createClickTrack({ beatMs, beatsPerBar, volume = 0.8, clock = () => performance.now() }) {
  let ctx = null;
  let timer = null;
  let nextTime = 0;
  let beat = 0;

  function schedule() {
    while (nextTime < ctx.currentTime + SCHEDULE_AHEAD_S) {
      click(ctx, nextTime, { accent: beat % beatsPerBar === 0, volume });
      nextTime += beatMs / 1000;
      beat += 1;
    }
  }

  return {
    start() {
      ctx = audioContext();
      if (!ctx) return null;
      const now = clock();
      nextTime = ctx.currentTime + START_LEAD_S;
      const latency = (ctx.outputLatency || ctx.baseLatency || 0) * 1000;
      schedule();
      timer = setInterval(schedule, LOOKAHEAD_MS);
      return now + START_LEAD_S * 1000 + latency;
    },
    stop() {
      clearInterval(timer);
      timer = null;
    },
  };
}

export function createRun({
  controller,
  mode,
  notes = [],
  tempoBpm = 80,
  beatsPerBar = 4,
  countInBeats = 4,
  latencyMs = 0,
  maxSeconds = 600,
  clock = () => performance.now(),
  makeTrack = (config) => createClickTrack(config),
  onUpdate = () => {},
  onFinish = () => {},
}) {
  const events = mode === "free" ? [] : groupReference(notes);
  const beatMs = 60000 / tempoBpm;
  const wait = mode === "wait" && events.length ? createWaitMatcher(events) : null;
  const live = mode === "scored" && events.length ? createLiveMatcher(events, tempoBpm) : null;
  const played = [];
  const timers = [];
  let phase = "idle";
  let track = null;
  let off = null;
  let startedAt = 0;
  let origin = 0;
  let silent = false;
  let finished = false;

  function snapshot(extra = {}) {
    return {
      phase,
      mode,
      silent,
      bars: wait ? wait.bars() : live ? live.bars() : [],
      expected: wait ? wait.expected : [],
      bar: wait ? wait.bar : null,
      played: played.length,
      ...extra,
    };
  }

  function emit(extra) {
    onUpdate(snapshot(extra));
  }

  function after(ms, fn) {
    timers.push(setTimeout(fn, Math.max(ms, 0)));
  }

  function release() {
    timers.forEach(clearTimeout);
    timers.length = 0;
    if (track) track.stop();
    track = null;
    if (off) off();
    off = null;
  }

  function finish() {
    if (finished || phase === "idle") return;
    finished = true;
    const seconds = Math.min(Math.max((clock() - startedAt) / 1000, 0), maxSeconds);
    release();
    phase = "done";
    const tally = wait ? new Map(wait.bars().map((item) => [item.bar, { ...item }])) : live ? new Map(live.bars().map((item) => [item.bar, { ...item }])) : null;
    const result = {
      mode,
      notes: played.slice(),
      tempoBpm: mode === "wait" ? null : tempoBpm,
      beatsPerBar,
      countInBeats: mode === "wait" ? 0 : countInBeats,
      latencyMs,
      durationSec: Math.round(seconds * 10) / 10,
      local: tally ? localSummary(tally) : null,
    };
    onUpdate(snapshot());
    onFinish(result);
  }

  function heard(note) {
    if (phase === "done" || note.type !== "on") return;
    const relative = note.time - origin;
    if (mode !== "wait" && relative < -LEAD_IN_BEATS * beatMs) return;
    played.push({ t: Math.round(relative * 10) / 10, midi: note.midi });
    let extra = {};
    if (wait) extra = { last: wait.press(note.midi) };
    else if (live) extra = { last: live.play(note.midi, relative - latencyMs) };
    emit(extra);
    if (wait && wait.done) after(250, finish);
    else if (played.length >= MAX_NOTES) finish();
  }

  function begin() {
    if (phase !== "idle") return false;
    startedAt = clock();
    off = controller.onNote(heard);
    if (mode === "wait") {
      origin = startedAt;
      phase = "playing";
      after(maxSeconds * 1000, finish);
      emit();
      return true;
    }
    track = makeTrack({ beatMs, beatsPerBar });
    const first = track.start();
    silent = first === null;
    const firstBeat = silent ? clock() + 150 : first;
    origin = firstBeat + countInBeats * beatMs;
    phase = countInBeats > 0 ? "countin" : "playing";
    for (let beat = 0; beat < countInBeats; beat += 1) after(firstBeat + beat * beatMs - clock(), () => emit({ countIn: countInBeats - beat }));
    after(origin - clock(), () => {
      if (phase === "countin") phase = "playing";
      emit();
    });
    const lastOnset = events.length ? events[events.length - 1].onset : 0;
    const runMs = mode === "free" ? maxSeconds * 1000 : (lastOnset + 3) * beatMs;
    after(origin - clock() + runMs, finish);
    emit();
    return true;
  }

  return {
    start: begin,
    stop: finish,
    cancel() {
      finished = true;
      release();
      phase = "idle";
    },
    get phase() {
      return phase;
    },
    get silent() {
      return silent;
    },
  };
}
