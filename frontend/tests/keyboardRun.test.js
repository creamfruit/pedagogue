import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_NOTES, createRun } from "../src/lib/keyboardRun.js";

const SCALE = [60, 62, 64, 65];
const notes = SCALE.map((midi, index) => [index, midi, 1]);

let now = 0;
const clock = () => now;

function advance(ms) {
  now += ms;
  vi.advanceTimersByTime(ms);
}

function fakeController() {
  const handlers = new Set();
  return {
    onNote(handler) {
      handlers.add(handler);
      return () => handlers.delete(handler);
    },
    press(midi, time) {
      handlers.forEach((handler) => handler({ type: "on", midi, velocity: 80, time }));
    },
    release(midi, time) {
      handlers.forEach((handler) => handler({ type: "off", midi, velocity: 0, time }));
    },
    get listening() {
      return handlers.size;
    },
  };
}

function fakeTrack(first = 100) {
  const track = { started: 0, stopped: 0, start: () => (track.started++, first === null ? null : now + first), stop: () => track.stopped++ };
  return track;
}

beforeEach(() => {
  now = 0;
  vi.useFakeTimers();
});

afterEach(() => vi.useRealTimers());

function setup(options = {}) {
  const controller = fakeController();
  const track = options.track || fakeTrack();
  const updates = [];
  const finished = [];
  const run = createRun({
    controller,
    clock,
    makeTrack: () => track,
    onUpdate: (state) => updates.push(state),
    onFinish: (result) => finished.push(result),
    tempoBpm: 120,
    countInBeats: 2,
    notes,
    mode: "scored",
    ...options,
  });
  return { run, controller, track, updates, finished };
}

describe("a timed run", () => {
  it("counts in, then scores notes played against the first beat after the count-in", () => {
    const { run, controller, track, updates, finished } = setup();
    expect(run.start()).toBe(true);
    expect(run.phase).toBe("countin");
    expect(track.started).toBe(1);
    expect(updates.filter((state) => state.countIn).map((state) => state.countIn)).toEqual([]);
    advance(100);
    expect(updates.map((state) => state.countIn).filter(Boolean)).toEqual([2]);
    advance(500);
    expect(updates.map((state) => state.countIn).filter(Boolean)).toEqual([2, 1]);
    advance(500);
    expect(run.phase).toBe("playing");
    const origin = 1100;
    SCALE.forEach((midi, index) => controller.press(midi, origin + index * 500 + 10));
    const states = updates.filter((state) => state.last);
    expect(states.map((state) => state.last.result)).toEqual(["correct", "correct", "correct", "correct"]);
    advance(4000);
    expect(finished).toHaveLength(1);
    const result = finished[0];
    expect(result.mode).toBe("scored");
    expect(result.tempoBpm).toBe(120);
    expect(result.countInBeats).toBe(2);
    expect(result.notes.map((note) => note.midi)).toEqual(SCALE);
    expect(result.notes.map((note) => note.t)).toEqual([10, 510, 1010, 1510]);
    expect(result.local.accuracy).toBe(1);
    expect(result.durationSec).toBeGreaterThan(3);
    expect(track.stopped).toBe(1);
    expect(controller.listening).toBe(0);
  });

  it("flags a wrong note as it is played and counts it against the bar", () => {
    const { run, controller, finished } = setup();
    run.start();
    advance(1100);
    controller.press(60, 1100);
    controller.press(61, 1620);
    run.stop();
    const result = finished[0];
    expect(result.local.wrong).toBe(1);
    expect(result.local.correct).toBe(1);
    expect(result.local.missing).toBe(3);
    expect(result.notes).toHaveLength(2);
  });

  it("ignores keys pressed well before the count-in ends", () => {
    const { run, controller, finished } = setup();
    run.start();
    advance(200);
    controller.press(72, 300);
    advance(900);
    controller.press(60, 1090);
    run.stop();
    expect(finished[0].notes.map((note) => note.midi)).toEqual([60]);
  });

  it("accepts a note a touch before the first beat", () => {
    const { run, controller, finished } = setup();
    run.start();
    advance(1000);
    controller.press(60, 1000);
    run.stop();
    expect(finished[0].notes[0].t).toBe(-100);
    expect(finished[0].local.correct).toBe(1);
  });

  it("falls back to a silent count when the browser cannot play audio", () => {
    const { run, updates } = setup({ track: fakeTrack(null) });
    run.start();
    expect(run.silent).toBe(true);
    expect(updates[0].silent).toBe(true);
    advance(150 + 1000 + 10);
    expect(run.phase).toBe("playing");
  });

  it("finishes once, however it is stopped", () => {
    const { run, finished } = setup();
    run.start();
    advance(1200);
    run.stop();
    run.stop();
    advance(10000);
    expect(finished).toHaveLength(1);
  });

  it("can be cancelled without reporting a result", () => {
    const { run, controller, track, finished } = setup();
    run.start();
    run.cancel();
    advance(10000);
    expect(finished).toHaveLength(0);
    expect(track.stopped).toBe(1);
    expect(controller.listening).toBe(0);
  });

  it("does nothing when stopped before it starts, and cannot start twice", () => {
    const { run, track, finished } = setup();
    run.stop();
    expect(finished).toHaveLength(0);
    expect(run.start()).toBe(true);
    expect(run.start()).toBe(false);
    expect(track.started).toBe(1);
  });

  it("stops by itself when there are too many notes", () => {
    const { run, controller, finished } = setup({ mode: "free", maxSeconds: 60 });
    run.start();
    advance(1100);
    for (let index = 0; index < MAX_NOTES; index += 1) controller.press(60 + (index % 12), 1100 + index);
    expect(finished).toHaveLength(1);
    expect(finished[0].notes).toHaveLength(MAX_NOTES);
  });
});

describe("wait for me", () => {
  it("has no metronome or count-in and moves on with the player", () => {
    const { run, controller, track, updates, finished } = setup({ mode: "wait" });
    run.start();
    expect(track.started).toBe(0);
    expect(run.phase).toBe("playing");
    expect(updates[0].expected).toEqual([60]);
    controller.press(61, 400);
    controller.press(60, 900);
    expect(updates.at(-1).expected).toEqual([62]);
    controller.press(62, 3000);
    controller.press(64, 9000);
    expect(finished).toHaveLength(0);
    controller.press(65, 20000);
    advance(300);
    expect(finished).toHaveLength(1);
    const result = finished[0];
    expect(result.mode).toBe("wait");
    expect(result.tempoBpm).toBeNull();
    expect(result.countInBeats).toBe(0);
    expect(result.notes.map((note) => note.midi)).toEqual([61, 60, 62, 64, 65]);
    expect(result.local).toMatchObject({ correct: 4, wrong: 1, missing: 0 });
  });

  it("can be ended early and reports what was left", () => {
    const { run, controller, finished } = setup({ mode: "wait" });
    run.start();
    controller.press(60, 100);
    run.stop();
    expect(finished[0].local).toMatchObject({ correct: 1, missing: 3 });
  });
});

describe("free play", () => {
  it("has no reference, keeps the metronome going and runs until stopped", () => {
    const { run, controller, finished } = setup({ mode: "free", notes: [], countInBeats: 4 });
    run.start();
    advance(100 + 2000);
    [0, 300, 600, 900].forEach((offset, index) => controller.press(60 + index, 2100 + offset));
    advance(5000);
    expect(finished).toHaveLength(0);
    run.stop();
    const result = finished[0];
    expect(result.mode).toBe("free");
    expect(result.local).toBeNull();
    expect(result.notes.map((note) => note.t)).toEqual([0, 300, 600, 900]);
    expect(result.tempoBpm).toBe(120);
    expect(result.countInBeats).toBe(4);
  });

  it("gives up after the longest allowed take", () => {
    const { run, finished } = setup({ mode: "free", notes: [], maxSeconds: 30 });
    run.start();
    advance(1100 + 30000 + 10);
    expect(finished).toHaveLength(1);
    expect(finished[0].durationSec).toBeLessThanOrEqual(30);
  });
});
