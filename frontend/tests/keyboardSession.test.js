import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { keyboardSession, reviewLine } from "../src/views/keyboardSession.js";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const REFERENCE = {
  available: true,
  piece_id: 5,
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

function setup({ reference = REFERENCE, status = "ready", attempt = attemptResult(), failSave = false, heat = { attempts: 0, bars: [] }, overview = { sections: [] } } = {}) {
  const api = {
    repertoire: vi.fn(async () => ({ items: [{ id: "e1", status: "learning", piece: { title: "Octave study" } }, { id: "e2", status: "learnt", piece: { title: "Old piece" } }] })),
    keyboardReference: vi.fn(async () => reference),
    keyboardLadder: vi.fn(async () => ({ recommended_tempo: 60, current_tempo: null, clean_streak: 0, runs_needed: 2, target_tempo: 100, raised: false, reached_target: false })),
    keyboardNotes: vi.fn(async () => NOTES),
    keyboardAttempt: vi.fn(async () => {
      if (failSave) throw Object.assign(new Error("offline"), { detail: "you appear to be offline" });
      return attempt;
    }),
    keyboardHeat: vi.fn(async () => heat),
    pieceOverview: vi.fn(async () => overview),
    blob: vi.fn(async () => new Blob(["png"])),
    closeSession: vi.fn(async () => ({})),
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
  const onSession = vi.fn();
  const session = keyboardSession({ controller, api, createRun, onSession });
  document.body.append(session.node);
  return { api, session, runs, node: session.node, onSession };
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

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:crop");
  URL.revokeObjectURL = vi.fn();
});

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

  it("says plainly when there is no reference and offers only free play", async () => {
    const message = "Note checking isn't available for this piece because it has no MusicXML or MIDI reference.";
    const { node, runs, api } = setup({ reference: { available: false, message, passages: [], target_tempo_bpm: 100, beats_per_bar: 4 } });
    await choose(node);
    expect(node.textContent).toContain(message);
    const modes = [...node.querySelector('select[aria-label="How to play"]').options].map((option) => option.textContent);
    expect(modes).toEqual(["Free play against the metronome"]);
    expect(node.querySelector('select[aria-label="Passage"]').closest(".keyboard-options").hidden).toBe(true);
    expect(node.querySelector('select[aria-label="Beats per bar"]').hidden).toBe(false);
    expect(startButton(node).disabled).toBe(false);
    startButton(node).click();
    await flush();
    expect(api.keyboardNotes).not.toHaveBeenCalled();
    expect(runs).toHaveLength(1);
    expect(runs[0].config).toMatchObject({ mode: "free", notes: [], tempoBpm: 60, beatsPerBar: 4, countInBeats: 4, maxSeconds: 120 });
  });

  it("offers free play alongside the scored modes when there is a reference", async () => {
    const { node, api } = setup();
    await choose(node);
    const mode = node.querySelector('select[aria-label="How to play"]');
    expect([...mode.options].map((option) => option.value)).toEqual(["scored", "wait", "free"]);
    mode.value = "free";
    mode.dispatchEvent(new Event("change"));
    await flush();
    expect(node.querySelector('select[aria-label="Passage"]').closest(".keyboard-options").hidden).toBe(true);
    expect(api.keyboardLadder).toHaveBeenLastCalledWith("e1", { mode: "free" });
    expect(node.textContent).toContain("it can't check notes");
  });

  it("does not offer the scored modes if the piece it was last on had no reference", async () => {
    const { node, api } = setup();
    await choose(node);
    api.keyboardReference.mockResolvedValueOnce({ available: false, message: "No reference.", passages: [], target_tempo_bpm: 100, beats_per_bar: 4 });
    await choose(node, "e2");
    expect([...node.querySelector('select[aria-label="How to play"]').options].map((option) => option.value)).toEqual(["free"]);
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

  it("saves a free-play run without bars and says note checking is unavailable", async () => {
    const attempt = attemptResult({
      mode: "free",
      expected: 0,
      correct: 0,
      missing: 0,
      accuracy: null,
      clean: true,
      played: 16,
      timing: 94,
      evenness: 88,
      achieved_tempo_bpm: null,
      note_checking: false,
      message: "Note checking isn't available for free play. This only measures how evenly you play against the metronome.",
      bars: [{ bar: 1, expected: 0, correct: 0, wrong: 0, missing: 0, accuracy: null, timing_score: 96, timing_error_ms: 8 }, { bar: 2, expected: 0, correct: 0, wrong: 0, missing: 0, accuracy: null, timing_score: 40, timing_error_ms: 70 }],
      ladder: { recommended_tempo: 60, current_tempo: 60, clean_streak: 1, runs_needed: 2, target_tempo: 100, raised: false, reached_target: false },
    });
    const { node, runs, api } = setup({ attempt, reference: { available: false, message: "No reference.", passages: [], target_tempo_bpm: 100, beats_per_bar: 4 } });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish({ mode: "free", notes: [{ t: 0, midi: 60 }, { t: 300, midi: 62 }], tempoBpm: 60, beatsPerBar: 4, countInBeats: 4, latencyMs: 0, durationSec: 9, local: null });
    await flush();
    expect(api.keyboardAttempt).toHaveBeenCalledWith("e1", {
      mode: "free",
      start_bar: null,
      end_bar: null,
      passage_id: null,
      beats_per_bar: 4,
      count_in_beats: 4,
      latency_ms: 0,
      duration_sec: 9,
      notes: [{ t: 0, midi: 60 }, { t: 300, midi: 62 }],
      tempo_bpm: 60,
    });
    const shown = node.querySelector(".keyboard-result").textContent;
    expect(shown).toContain("Note checking isn't available");
    expect(shown).toContain("Timing");
    expect(shown).toContain("Evenness");
    expect(shown).not.toContain("Notes right");
    expect(shown).not.toMatch(/null|undefined/);
    expect([...node.querySelectorAll(".heat-cell")].map((cell) => cell.className.match(/heat-(good|fair|bad)/)[1])).toEqual(["good", "bad"]);
  });

  it("still explains free play when the run could not be saved", async () => {
    const { node, runs } = setup({ failSave: true, reference: { available: false, message: "No reference.", passages: [], target_tempo_bpm: 100, beats_per_bar: 4 } });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish({ mode: "free", notes: [{ t: 0, midi: 60 }], tempoBpm: 60, beatsPerBar: 4, countInBeats: 4, latencyMs: 0, durationSec: 4, local: null });
    await flush();
    const shown = node.querySelector(".keyboard-result").textContent;
    expect(shown).toContain("This run wasn't saved");
    expect(shown).toContain("Note checking isn't available");
    expect(shown).not.toMatch(/null|undefined/);
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

const finishedRun = () => ({
  mode: "scored",
  notes: [{ t: 0, midi: 60 }],
  tempoBpm: 60,
  beatsPerBar: 4,
  countInBeats: 4,
  latencyMs: 0,
  durationSec: 12,
  local: { accuracy: 1, correct: 1, wrong: 0, missing: 0, bars: [] },
});

describe("the strip and the score", () => {
  const section = { start_measure: 9, end_measure: 11, score_crop: "/submissions/s1/crops/0", score_page: 2 };

  it("shows how the last runs went bar by bar before the next one", async () => {
    const heat = { attempts: 3, bars: [{ bar: 1, attempts: 3, accuracy: 1, wrong: 0, missing: 0 }, { bar: 2, attempts: 3, accuracy: 0.4, wrong: 4, missing: 3 }] };
    const { node, api } = setup({ heat });
    await choose(node);
    expect(api.keyboardHeat).toHaveBeenCalledWith("e1", { start_bar: 1, end_bar: 12 });
    expect(node.querySelector(".heat-caption").textContent).toBe("Your last 3 runs here, bar by bar");
    expect([...node.querySelectorAll(".heat-cell")].map((cell) => cell.className.match(/heat-(good|fair|bad)/)[1])).toEqual(["good", "bad"]);
  });

  it("shows nothing when there is no history yet", async () => {
    const { node } = setup();
    await choose(node);
    expect(node.querySelector(".keyboard-board").hidden).toBe(true);
  });

  it("puts the strip directly above the crop of the chosen passage", async () => {
    const heat = { attempts: 2, bars: [{ bar: 9, attempts: 2, accuracy: 0.5, wrong: 2, missing: 2 }] };
    const { node, api } = setup({ heat, overview: { sections: [section] } });
    await choose(node);
    const passage = node.querySelector('select[aria-label="Passage"]');
    passage.value = "7";
    passage.dispatchEvent(new Event("change"));
    await flush();
    await flush();
    expect(api.pieceOverview).toHaveBeenCalledWith(5);
    expect(api.blob).toHaveBeenCalledWith("/submissions/s1/crops/0");
    const board = node.querySelector(".keyboard-board");
    expect(board.classList.contains("has-crop")).toBe(true);
    const order = [...board.children].map((child) => child.className.split(" ")[0]);
    expect(order.indexOf("heat")).toBeLessThan(order.indexOf("keyboard-crop-image"));
    expect(board.querySelector(".keyboard-crop-image img").getAttribute("src")).toBe("blob:crop");
    expect(board.querySelector(".keyboard-crop-image img").alt).toBe("Bars 9 to 11 from your score");
  });

  it("only fetches the overview once and has no crop for bars that were not marked", async () => {
    const { node, api } = setup({ overview: { sections: [section] } });
    await choose(node);
    const passage = node.querySelector('select[aria-label="Passage"]');
    passage.value = "custom";
    passage.dispatchEvent(new Event("change"));
    await flush();
    passage.value = "7";
    passage.dispatchEvent(new Event("change"));
    await flush();
    await flush();
    passage.value = "whole";
    passage.dispatchEvent(new Event("change"));
    await flush();
    expect(api.pieceOverview).toHaveBeenCalledTimes(1);
    expect(node.querySelector(".keyboard-crop-image").hidden).toBe(true);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:crop");
  });

  it("marks the bars of the run just played above the same crop", async () => {
    const { node, runs } = setup({ overview: { sections: [section] } });
    await choose(node);
    const passage = node.querySelector('select[aria-label="Passage"]');
    passage.value = "7";
    passage.dispatchEvent(new Event("change"));
    await flush();
    await flush();
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finishedRun());
    await flush();
    expect(node.querySelector(".heat-caption").textContent).toBe("How each bar went");
    expect(node.querySelectorAll(".heat-cell")).toHaveLength(2);
    expect(node.querySelector(".keyboard-board").classList.contains("has-crop")).toBe(true);
  });
});

describe("feeding the session, XP and review", () => {
  const fed = { session_id: "s9", session_minutes: 7, xp_awarded: 15, next_review_at: new Date(Date.now() + 5.4 * 86400000).toISOString() };

  it("tells the player what they earned and when to come back", async () => {
    const { node, runs, onSession } = setup({ attempt: attemptResult(fed) });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finishedRun());
    await flush();
    const text = node.querySelector(".keyboard-result").textContent;
    expect(text).toContain("+15 XP for clearing a new tempo");
    expect(text).toContain("This session: 7 minutes of keyboard practice so far.");
    expect(text).toContain("Come back to this piece in about 5 days");
    expect(onSession).toHaveBeenCalledTimes(1);
  });

  it("finishes the session on request so the minutes count for the streak and XP", async () => {
    const { node, runs, api, onSession } = setup({ attempt: attemptResult(fed) });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finishedRun());
    await flush();
    const finish = [...node.querySelectorAll("button")].find((button) => button.textContent === "Finish session");
    finish.click();
    await flush();
    await flush();
    expect(api.closeSession).toHaveBeenCalledWith("s9", {});
    expect(node.querySelector(".keyboard-session-line").textContent).toContain("Session finished");
    expect([...node.querySelectorAll("button")].some((button) => button.textContent === "Finish session")).toBe(false);
    expect(onSession).toHaveBeenCalledTimes(2);
  });

  it("keeps the button if the session could not be closed", async () => {
    const { node, runs, api } = setup({ attempt: attemptResult(fed) });
    await choose(node);
    api.closeSession.mockRejectedValueOnce(Object.assign(new Error("no"), { detail: "that practice session is already closed" }));
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finishedRun());
    await flush();
    const finish = [...node.querySelectorAll("button")].find((button) => button.textContent === "Finish session");
    finish.click();
    await flush();
    await flush();
    expect(finish.disabled).toBe(false);
    expect(document.body.textContent).toContain("already closed");
  });

  it("says nothing about a session when no minutes were counted", async () => {
    const { node, runs } = setup({ attempt: attemptResult({ session_id: null, session_minutes: null, xp_awarded: 0, next_review_at: null }) });
    await choose(node);
    startButton(node).click();
    await flush();
    await runs[0].config.onFinish(finishedRun());
    await flush();
    const text = node.querySelector(".keyboard-result").textContent;
    expect(text).not.toContain("This session");
    expect(text).not.toContain("XP");
    expect(text).not.toContain("Come back");
  });
});

describe("review wording", () => {
  const now = new Date("2026-10-19T12:00:00Z");

  it("says how soon to come back", () => {
    expect(reviewLine("2026-10-19T09:00:00Z", now)).toBe("This piece is due for another look today.");
    expect(reviewLine("2026-10-20T12:00:00Z", now)).toBe("Come back to this piece tomorrow to keep it fresh.");
    expect(reviewLine("2026-10-26T12:00:00Z", now)).toBe("Come back to this piece in about 7 days to keep it fresh.");
    expect(reviewLine(null, now)).toBeNull();
  });
});
