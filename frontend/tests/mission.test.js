import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const STEPS = [
  { index: 0, kind: "warmup", title: "Warm up: Rapid scales", minutes: 2, why: "Rapid scales is one of your lowest-rated techniques.", entry_id: "e1", piece_id: 1, piece_title: "Etude", technique: "Rapid scales", technique_id: 4, mechanic: "Even, relaxed fingers.", cue: "Even, relaxed fingers.", tempo_bpm: 72, star_entry_id: "e1", passage_id: null, bars: null },
  { index: 1, kind: "passage", title: "Hardest passage: Etude", minutes: 5, why: "Bars 5-8 in Etude is your hardest section.", entry_id: "e1", piece_id: 1, piece_title: "Etude", passage_id: 11, bars: "bars 5-8", cue: "Hands apart first.", tempo_bpm: 60, star_entry_id: "e1" },
  { index: 2, kind: "review", title: "Review: Nocturne", minutes: 3, why: "Nocturne was last played 14 days ago.", entry_id: "e2", piece_id: 2, piece_title: "Nocturne", passage_id: null, bars: null, tempo_bpm: 66, star_entry_id: "e2" },
  { index: 3, kind: "playthrough", title: "Play through: Minuet", minutes: 4, why: "Minuet is closest to your target tempo.", entry_id: "e3", piece_id: 3, piece_title: "Minuet", passage_id: null, bars: null, tempo_bpm: 90, star_entry_id: "e3" },
];

const done = (indexes) => indexes.map((index) => ({ index, status: "done", seconds: 60, minutes: 1 }));

function mission(extra = {}) {
  return { id: "m1", day: new Date().toLocaleDateString("en-CA"), kind: "daily", total_minutes: 14, steps: STEPS, progress: [], completed_at: null, next_index: 0, ...extra };
}

function fakeMetronome() {
  const state = { running: false, bpm: 72 };
  return {
    get running() {
      return state.running;
    },
    get bpm() {
      return state.bpm;
    },
    setBpm: vi.fn((value) => {
      state.bpm = value;
    }),
    start: vi.fn(() => {
      state.running = true;
      return true;
    }),
    stop: vi.fn(() => {
      state.running = false;
    }),
  };
}

let released;
let metronome;

async function open({ initial = mission(), query = {} } = {}) {
  vi.resetModules();
  released = vi.fn();
  metronome = fakeMetronome();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
  vi.doMock("../src/lib/wakeLock.js", () => ({ keepAwake: vi.fn(async () => released) }));
  vi.doMock("../src/lib/metronome.js", async (original) => ({ ...(await original()), createMetronome: vi.fn(() => metronome) }));
  const client = await import("../src/api/client.js");
  const spies = {
    today: vi.spyOn(client.api, "missionToday").mockResolvedValue(initial),
    step: vi.spyOn(client.api, "missionStep"),
    overview: vi.spyOn(client.api, "pieceOverview").mockResolvedValue({ sections: [{ id: 11, score_crop: "/submissions/s1/crops/0" }] }),
    blob: vi.spyOn(client.api, "blob").mockResolvedValue(new Blob(["x"], { type: "image/png" })),
    sight: vi.spyOn(client.api, "passageSightReading").mockRejectedValue(new Error("none")),
    profile: vi.spyOn(client.api, "profileSummary").mockResolvedValue({}),
  };
  URL.createObjectURL = vi.fn(() => "blob:crop");
  URL.revokeObjectURL = vi.fn();
  const { missionView } = await import("../src/views/mission.js");
  const nav = await import("../src/router.js");
  vi.spyOn(nav, "navigate").mockImplementation(() => {});
  const outlet = document.createElement("main");
  document.body.append(outlet);
  const dispose = await missionView(outlet, { query });
  return { outlet, dispose, spies, client, nav, root: outlet.querySelector(".mission-screen") };
}

function answerSteps(spies, startingProgress = []) {
  const progress = [...startingProgress];
  spies.step.mockImplementation(async (id, index, body) => {
    progress.push({ index, status: body.status, seconds: body.seconds, minutes: 1 });
    const next = STEPS.map((item) => item.index).find((i) => !progress.some((p) => p.index === i));
    return {
      mission: mission({ progress: [...progress], next_index: next ?? null, completed_at: next === undefined ? "2026-10-22T10:00:00Z" : null }),
      lit: body.status === "done" ? { entry_id: STEPS[index].star_entry_id, piece_title: STEPS[index].piece_title } : null,
      finished: next === undefined,
      xp: next === undefined ? 42 : 0,
      gold: 0,
      streak: { current: 1, today_done: true },
    };
  });
}

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
  document.body.className = "";
  localStorage.clear();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"] });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("starting the mission", () => {
  it("waits for one tap before it begins, and takes over the whole screen", async () => {
    const { root } = await open();
    expect(document.body.classList.contains("immersive")).toBe(true);
    expect(root.textContent).toContain("4 steps, about 14 minutes");
    expect(root.textContent).toContain("Tap anywhere to begin");
    expect(root.querySelector(".mission-timer")).toBe(null);
  });

  it("shows a progress arc with one segment per step", async () => {
    const { root } = await open();
    expect(root.querySelectorAll(".mission-arc-seg")).toHaveLength(4);
    expect(root.querySelector(".mission-arc").getAttribute("aria-label")).toContain("Step 1 of 4");
  });

  it("asks for a short first mission when sent from onboarding", async () => {
    const { spies } = await open({ query: { first: "1" } });
    expect(spies.today).toHaveBeenCalledWith(true);
  });

  it("goes back to Today when today's mission is already done", async () => {
    const { nav } = await open({ initial: mission({ completed_at: "2026-10-22T09:00:00Z" }) });
    expect(nav.navigate).toHaveBeenCalledWith("/", { replace: true });
  });

  it("says so when the mission cannot be loaded", async () => {
    vi.resetModules();
    const client = await import("../src/api/client.js");
    vi.spyOn(client.api, "missionToday").mockRejectedValue(Object.assign(new Error("down"), { detail: "The server is down." }));
    const { missionView } = await import("../src/views/mission.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await missionView(outlet, { query: {} });
    expect(outlet.textContent).toContain("Today's mission isn't ready");
    expect(outlet.textContent).toContain("The server is down.");
  });
});

describe("a practice step on the music stand", () => {
  async function begin(options) {
    const opened = await open(options);
    opened.root.click();
    await vi.advanceTimersByTimeAsync(0);
    return opened;
  }

  it("keeps the screen awake while it runs and lets go when you leave", async () => {
    const { dispose } = await begin();
    expect(released).not.toHaveBeenCalled();
    dispose();
    expect(released).toHaveBeenCalledTimes(1);
    expect(metronome.stop).toHaveBeenCalled();
    expect(document.body.classList.contains("immersive")).toBe(false);
  });

  it("shows a very large timer that counts up, and the planned time beside it", async () => {
    const { root } = await begin();
    const timer = root.querySelector(".mission-timer");
    expect(timer.textContent).toBe("00:00");
    await vi.advanceTimersByTimeAsync(65_000);
    expect(timer.textContent).toBe("01:05");
    expect(root.querySelector(".mission-timer-target").textContent).toBe("of 02:00");
  });

  it("says the time is up without nagging, and keeps counting", async () => {
    const { root } = await begin();
    await vi.advanceTimersByTimeAsync(125_000);
    expect(root.querySelector(".mission-timer").classList.contains("is-over")).toBe(true);
    expect(root.querySelector(".mission-note").textContent).toContain("That's the time");
  });

  it("offers the metronome as large controls and starts it where a drill needs one", async () => {
    const { root } = await begin();
    expect(metronome.setBpm).toHaveBeenCalledWith(72);
    expect(metronome.start).toHaveBeenCalled();
    const toggle = root.querySelector(".mission-metro-toggle");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    root.querySelector('[data-control="faster"]').click();
    expect(metronome.setBpm).toHaveBeenLastCalledWith(76);
    root.querySelector('[data-control="slower"]').click();
    toggle.click();
    expect(metronome.stop).toHaveBeenCalled();
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(localStorage.getItem("pp.mission.metronome")).toBe("off");
  });

  it("does not move on when a control is tapped", async () => {
    const { root, spies } = await begin();
    await vi.advanceTimersByTimeAsync(30_000);
    for (const control of ["faster", "slower", "metronome", "pause"]) root.querySelector(`[data-control="${control}"]`).click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).not.toHaveBeenCalled();
  });

  it("moves on with a tap anywhere and logs the seconds spent", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    await vi.advanceTimersByTimeAsync(45_000);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).toHaveBeenCalledWith("m1", 0, { status: "done", seconds: 45 });
    expect(root.textContent).toContain("Step done");
    expect(root.textContent).toContain("Etude is brighter in your sky");
  });

  it("lights a star with a short animation and remembers it for the Sky", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    await vi.advanceTimersByTimeAsync(40_000);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(root.querySelector(".star-burst")).not.toBe(null);
    expect(root.querySelectorAll(".star-burst-spark")).toHaveLength(8);
    expect(root.querySelector(".mission-interlude").classList.contains("is-still")).toBe(false);
    expect(JSON.parse(localStorage.getItem("pp.lit")).entries).toEqual(["e1"]);
  });

  it("holds the star still, and a little shorter, when motion is reduced", async () => {
    localStorage.setItem("pp.motion", "reduce");
    const { root, spies } = await begin();
    answerSteps(spies);
    await vi.advanceTimersByTimeAsync(40_000);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(root.querySelector(".mission-interlude").classList.contains("is-still")).toBe(true);
    await vi.advanceTimersByTimeAsync(1200);
    expect(root.querySelector(".mission-kicker").textContent).toContain("Hardest passage");
  });

  it("does not light a star for a skipped step", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    root.querySelector('[data-control="skip"]').click();
    await vi.advanceTimersByTimeAsync(0);
    expect(localStorage.getItem("pp.lit")).toBe(null);
  });

  it("counts a tap on the score itself as a tap anywhere", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    await vi.advanceTimersByTimeAsync(45_000);
    root.querySelector(".mission-visual").click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).toHaveBeenCalledWith("m1", 0, { status: "done", seconds: 45 });
  });

  it("goes on to the next step by itself after a moment", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    await vi.advanceTimersByTimeAsync(40_000);
    root.click();
    await vi.advanceTimersByTimeAsync(1500);
    expect(root.querySelector(".mission-kicker").textContent).toContain("Hardest passage");
    expect(root.querySelector(".mission-arc").getAttribute("aria-label")).toContain("Step 2 of 4");
  });

  it("ignores a stray tap in the first moments and asks twice before finishing very early", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    root.click();
    await vi.advanceTimersByTimeAsync(500);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
    root.click();
    expect(root.querySelector(".mission-note").textContent).toBe("Tap again to finish early");
    expect(spies.step).not.toHaveBeenCalled();
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).toHaveBeenCalledTimes(1);
  });

  it("lets you skip a step with no penalty and no star", async () => {
    const { root, spies } = await begin();
    answerSteps(spies);
    root.querySelector('[data-control="skip"]').click();
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.step).toHaveBeenCalledWith("m1", 0, { status: "skipped", seconds: 0 });
    expect(root.textContent).not.toContain("Step done");
    expect(root.querySelector(".mission-kicker").textContent).toContain("Hardest passage");
  });

  it("shows the score crop of the passage, as large as the screen allows", async () => {
    const { root, spies } = await begin({ initial: mission({ progress: done([0]), next_index: 1 }) });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);
    expect(spies.overview).toHaveBeenCalledWith(1);
    expect(spies.blob).toHaveBeenCalledWith("/submissions/s1/crops/0");
    const image = root.querySelector(".mission-score");
    expect(image.getAttribute("src")).toBe("blob:crop");
    expect(image.getAttribute("alt")).toContain("bars 5-8");
    expect(root.querySelector(".mission-visual").contains(image)).toBe(true);
    expect(root.textContent).toContain("Hands apart first.");
  });

  it("shows the engraved crop of an open score when the player has not uploaded their own", async () => {
    const opened = await open({ initial: mission({ progress: done([0]), next_index: 1 }) });
    opened.spies.overview.mockResolvedValue({ sections: [{ id: 11, image: "/catalog/passages/11/image" }] });
    opened.root.click();
    for (let i = 0; i < 4; i += 1) await vi.advanceTimersByTimeAsync(0);
    expect(opened.spies.blob).toHaveBeenCalledWith("/catalog/passages/11/image");
    const image = opened.root.querySelector(".mission-score");
    expect(image.getAttribute("src")).toBe("blob:crop");
    expect(image.getAttribute("alt")).toContain("open score");
    expect(opened.spies.sight).not.toHaveBeenCalled();
  });

  it("falls back to plain words when there is neither a score crop nor a pattern", async () => {
    const opened = await open({ initial: mission({ progress: done([0]), next_index: 1 }) });
    opened.spies.overview.mockResolvedValue({ sections: [] });
    opened.root.click();
    for (let i = 0; i < 4; i += 1) await vi.advanceTimersByTimeAsync(0);
    expect(opened.spies.sight).toHaveBeenCalledWith(11, undefined);
    expect(opened.root.querySelector(".mission-visual-text").textContent).toContain("Etude, bars 5-8");
  });

  it("starts the metronome off for a full play-through", async () => {
    await begin({ initial: mission({ progress: done([0, 1, 2]), next_index: 3 }) });
    expect(metronome.start).not.toHaveBeenCalled();
  });
});

describe("finishing", () => {
  it("shows a gentle ending with the xp earned and a way to the sky", async () => {
    const opened = await open({ initial: mission({ progress: done([0, 1, 2]), next_index: 3 }) });
    opened.root.click();
    await vi.advanceTimersByTimeAsync(0);
    answerSteps(opened.spies, done([0, 1, 2]));
    await vi.advanceTimersByTimeAsync(30_000);
    opened.root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(opened.root.textContent).toContain("Mission complete");
    expect(opened.root.textContent).toContain("+42 xp");
    expect(opened.root.querySelector('a[href="/constellation"]')).not.toBe(null);
    expect(released).toHaveBeenCalled();
  });

  it("is kind when everything was skipped", async () => {
    const skipped = [0, 1, 2].map((index) => ({ index, status: "skipped", seconds: 0, minutes: 0 }));
    const opened = await open({ initial: mission({ progress: skipped, next_index: 3 }) });
    opened.root.click();
    await vi.advanceTimersByTimeAsync(0);
    answerSteps(opened.spies, skipped);
    opened.root.querySelector('[data-control="skip"]').click();
    await vi.advanceTimersByTimeAsync(0);
    expect(opened.root.textContent).toContain("No pressure");
  });
});
