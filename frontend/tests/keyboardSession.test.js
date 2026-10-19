import { afterEach, describe, expect, it, vi } from "vitest";
import { keyboardSession } from "../src/views/keyboardSession.js";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const REFERENCE = {
  available: true,
  source: "musicxml",
  first_bar: 1,
  last_bar: 12,
  quarter_bpm: 100,
  beats_per_bar: 4,
  note_count: 90,
  target_tempo_bpm: 100,
  passages: [{ id: 7, label: "Octave passage", start_bar: 9, end_bar: 11 }],
};

const NOTES = { start_bar: 1, end_bar: 12, quarter_bpm: 100, beats_per_bar: 4, bars: [1, 2], notes: [[0, 60, 1], [1, 62, 1], [4, 64, 2]] };

function attemptResult(overrides = {}) {
  return {
    id: "a1",
    mode: "scored",
    tempo_bpm: 60,
    expected: 3,
    correct: 3,
    wrong: 0,
    missing: 0,
    played: 3,
    accuracy: 1,
    timing: 96,
    evenness: 90,
    overall: 97,
    clean: true,
    late: 0,
    early: 0,
    achieved_tempo_bpm: 59.4,
    bars: [{ bar: 1, expected: 2, correct: 2, wrong: 0, missing: 0, accuracy: 1 }, { bar: 2, expected: 1, correct: 1, wrong: 0, missing: 0, accuracy: 1 }],
    ladder: { recommended_tempo: 62, current_tempo: 60, clean_streak: 2, runs_needed: 2, target_tempo: 100, raised: true, reached_target: false },
    note_checking: true,
    ...overrides,
  };
}

function setup({ reference = REFERENCE, status = "ready", attempt = attemptResult(), failSave = false } = {}) {
  const api = {
    repertoire: vi.fn(async () => ({ items: [{ id: "e1", status: "learning", piece: { title: "Octave study" } }, { id: "e2", status: "learnt", piece: { title: "Old piece" } }] })),
    keyboardReference: vi.fn(async () => reference),
    keyboardLadder: vi.fn(async () => ({ recommended_tempo: 60, current_tempo: null, clean_streak: 0, runs_needed: 2, target_tempo: 100, raised: false, reached_target: false })),
    keyboardNotes: vi.fn(async () => NOTES),
    keyboardAttempt: vi.fn(async () => {
      if (failSave) throw Object.assign(new Error("offline"), { detail: "you appear to be offline" });
      return attempt;
    }),
  };
  const controller = { state: { status, selectedId: status === "ready" ? "k1" : "" }, onNote: () => () => {} };
  const runs = [];
  const createRun = (config) => {
    const run = { config, start: vi.fn(), stop: vi.fn(), cancel: vi.fn() };
    runs.push(run);
    return run;
  };
  const toasts = document.createElement("div");
  toasts.id = "toasts";
  document.body.append(toasts);
  const session = keyboardSession({ controller, api, createRun });
  document.body.append(session.node);
  return { api, session, runs, node: session.node };
}

async function choose(node, id = "e1") {
  const select = node.querySelector('select[aria-label="Piece to practise"]');
  await flush();
  select.value = id;
  select.dispatchEvent(new Event("change"));
  await flush();
  await flush();
}

const startButton = (node) => [...node.querySelectorAll("button")].find((button) => button.textContent === "Start");

afterEach(() => {
  document.body.replaceChildren();
  localStorage.clear();
});

describe("choosing a piece", () => {
  it("lists the pieces being learned first", async () => {
    const { node } = setup();
    await flush();
    const options = [...node.querySelector('select[aria-label="Piece to practise"]').options].map((option) => option.textContent);
    expect(options).toEqual(["Choose a piece…", "Octave study", "Old piece"]);
  });

  it("offers passages, the whole piece and custom bars once note data is found", async () => {
    const { node, api } = setup();
    await choose(node);
    expect(api.keyboardReference).toHaveBeenCalledWith("e1");
    const passages = [...node.querySelector('select[aria-label="Passage"]').options].map((option) => option.textContent);
    expect(passages).toEqual(["The whole piece (bars 1–12)", "Octave passage (bars 9–11)", "Choose bars…"]);
    expect(startButton(node).disabled).toBe(false);
  });

  it("starts the ladder below the target tempo for a new passage", async () => {
    const { node } = setup();
    await choose(node);
    expect(node.querySelector('input[aria-label="Tempo in beats per minute"]').value).toBe("60");
    expect(node.textContent).toContain("Start at ♩ = 60");
  });

  it("says plainly when there is no reference and will not start", async () => {
    const message = "Note checking isn't available for this piece because it has no MusicXML or MIDI reference.";
    const { node, runs, api } = setup({ reference: { available: false, message, passages: [], target_tempo_bpm: 100, beats_per_bar: 4 } });
    await choose(node);
    expect(node.textContent).toContain(message);
    expect(startButton(node).disabled).toBe(true);
    startButton(node).click();
    await flush();
    expect(runs).toHaveLength(0);
    expect(api.keyboardNotes).not.toHaveBeenCalled();
  });
});

describe("starting a run", () => {
  it("needs a connected keyboard", async () => {
    const { node, runs, api } = setup({ status: "idle" });
    await choose(node);
    startButton(node).click();
    await flush();
    expect(runs).toHaveLength(0);
    expect(api.keyboardNotes).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("Connect a MIDI keyboard first");
  });

  it("loads the chosen bars and starts a timed run with the tempo and count-in", async () => {
    const { node, runs, api } = setup();
    await choose(node);
    const passage = node.querySelector('select[aria-label="Passage"]');
    passage.value = "7";
    passage.dispatchEvent(new Event("change"));
    await flush();
    expect(api.keyboardLadder).toHaveBeenLastCalledWith("e1", { mode: "scored", start_bar: 9, end_bar: 11 });
    startButton(node).click();
    await flush();
    expect(api.keyboardNotes).toHaveBeenCalledWith("e1", { start_bar: 9, end_bar: 11 });
    expect(runs).toHaveLength(1);
    expect(runs[0].config).toMatchObject({ mode: "scored", tempoBpm: 60, beatsPerBar: 4, countInBeats: 4, latencyMs: 0 });
    expect(runs[0].config.notes).toEqual(NOTES.notes);
    expect(runs[0].start).toHaveBeenCalled();
    expect(node.querySelector('select[aria-label="Piece to practise"]').disabled).toBe(true);
  });

  it("wait mode has no tempo and no count-in", async () => {
    const { node, runs, api } = setup();
    await choose(node);
    const mode = node.querySelector('select[aria-label="How to play"]');
    mode.value = "wait";
    mode.dispatchEvent(new Event("change"));
    await flush();
    expect(node.querySelector('input[aria-label="Tempo in beats per minute"]').closest(".row").hidden).toBe(true);
    startButton(node).click();
    await flush();
    expect(runs[0].config.mode).toBe("wait");
    expect(api.keyboardLadder).toHaveBeenCalledTimes(1);
  });

  it("takes the keyboard delay off every note and remembers it", async () => {
    const { node, runs } = setup();
    await choose(node);
    [...node.querySelectorAll("button")].find((button) => button.textContent === "Count-in and keyboard delay").click();
    const delay = node.querySelector('input[aria-label="Keyboard delay in milliseconds"]');
    delay.value = "35";
    startButton(node).click();
    await flush();
    expect(runs[0].config.latencyMs).toBe(35);
    expect(localStorage.getItem("pp.midi-latency")).toBe("35");
  });
});

describe("finishing a run", () => {
  const finished = (extra = {}) => ({
    mode: "scored",
    notes: [{ t: 0, midi: 60 }, { t: 600, midi: 62 }, { t: 2400, midi: 64 }],
    tempoBpm: 60,
    beatsPerBar: 4,
    countInBeats: 4,
    latencyMs: 0,
    durationSec: 12.3,
    local: { accuracy: 1, correct: 3, wrong: 0, missing: 0, bars: [] },
    ...extra,
  });

  it("saves the attempt, shows the scores and raises the tempo when the ladder says so", async () => {
    const { node, runs, api } = setup();
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finished());
    await flush();
    expect(api.keyboardAttempt).toHaveBeenCalledWith("e1", {
      mode: "scored",
      start_bar: 1,
      end_bar: 12,
      passage_id: null,
      beats_per_bar: 4,
      count_in_beats: 4,
      latency_ms: 0,
      duration_sec: 12.3,
      notes: [{ t: 0, midi: 60 }, { t: 600, midi: 62 }, { t: 2400, midi: 64 }],
      tempo_bpm: 60,
    });
    const text = node.textContent;
    expect(text).toContain("Clean run");
    expect(text).toContain("97");
    expect(text).toContain("Next run: ♩ = 62");
    expect(text).toContain("about ♩ = 59");
    expect(node.querySelector('input[aria-label="Tempo in beats per minute"]').value).toBe("62");
    expect(node.querySelectorAll(".heat-cell")).toHaveLength(2);
    expect(startButton(node).hidden).toBe(false);
    expect(node.querySelector(".keyboard-result").textContent).not.toMatch(/null|undefined/);
  });

  it("marks the bars that went wrong in the strip", async () => {
    const attempt = attemptResult({
      clean: false,
      accuracy: 0.6,
      overall: 55,
      ladder: { recommended_tempo: 60, current_tempo: 60, clean_streak: 0, runs_needed: 2, target_tempo: 100, raised: false, reached_target: false },
      bars: [{ bar: 1, expected: 2, correct: 2, wrong: 0, missing: 0, accuracy: 1 }, { bar: 2, expected: 1, correct: 0, wrong: 2, missing: 1, accuracy: 0 }],
    });
    const { node, runs } = setup({ attempt });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finished());
    await flush();
    const cells = [...node.querySelectorAll(".heat-cell")];
    expect(cells.map((cell) => cell.className.match(/heat-(good|fair|bad)/)[1])).toEqual(["good", "bad"]);
    expect(cells[1].title).toContain("2 wrong");
    expect(node.textContent).toContain("Keep going");
    expect(node.querySelector(".keyboard-result").textContent).not.toMatch(/null|undefined/);
    expect(node.querySelector('input[aria-label="Tempo in beats per minute"]').value).toBe("60");
  });

  it("still shows the notes result and says the run was not saved when saving fails", async () => {
    const { node, runs } = setup({ failSave: true });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finished({ local: { accuracy: 0.5, correct: 1, wrong: 1, missing: 2, bars: [{ bar: 1, expected: 2, correct: 1, wrong: 1, missing: 1, accuracy: 0.33 }] } }));
    await flush();
    expect(node.textContent).toContain("This run wasn't saved");
    expect(node.textContent).toContain("you appear to be offline");
    expect(node.querySelectorAll(".heat-cell")).toHaveLength(1);
  });

  it("can be stopped part-way through", async () => {
    const { node, runs } = setup();
    await choose(node);
    startButton(node).click();
    await flush();
    const stop = [...node.querySelectorAll("button")].find((button) => button.textContent === "Stop");
    expect(stop.hidden).toBe(false);
    stop.click();
    expect(runs[0].stop).toHaveBeenCalled();
  });
});
