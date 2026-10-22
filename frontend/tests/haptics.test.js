import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const impact = vi.fn(async () => {});
const notification = vi.fn(async () => {});
const loaded = vi.fn();

function mockPlugin() {
  vi.doMock("@capacitor/haptics", () => {
    loaded();
    return {
      Haptics: { impact, notification },
      ImpactStyle: { Light: "LIGHT", Medium: "MEDIUM" },
      NotificationType: { Success: "SUCCESS" },
    };
  });
}

beforeEach(() => {
  vi.resetModules();
  impact.mockClear();
  notification.mockClear();
  loaded.mockClear();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"] });
  document.body.innerHTML = '<div id="toasts"></div>';
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("haptic feedback", () => {
  it("does nothing on the web, and does not even load the plugin", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
    mockPlugin();
    const haptics = await import("../src/lib/haptics.js");
    haptics.lightTap();
    haptics.stepComplete();
    haptics.starLit();
    await vi.advanceTimersByTimeAsync(500);
    expect(loaded).not.toHaveBeenCalled();
    expect(impact).not.toHaveBeenCalled();
    expect(notification).not.toHaveBeenCalled();
  });

  it("gives a medium tap when a step is completed in the apps", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    mockPlugin();
    const haptics = await import("../src/lib/haptics.js");
    haptics.stepComplete();
    await vi.advanceTimersByTimeAsync(0);
    expect(impact).toHaveBeenCalledWith({ style: "MEDIUM" });
  });

  it("gives a soft success pulse a moment after, when a star lights", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    mockPlugin();
    const haptics = await import("../src/lib/haptics.js");
    haptics.starLit();
    await vi.advanceTimersByTimeAsync(50);
    expect(notification).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);
    expect(notification).toHaveBeenCalledWith({ type: "SUCCESS" });
  });

  it("keeps the light tap used elsewhere", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: false, isAndroid: true, platformName: "android" }));
    mockPlugin();
    const haptics = await import("../src/lib/haptics.js");
    haptics.lightTap();
    await vi.advanceTimersByTimeAsync(0);
    expect(impact).toHaveBeenCalledWith({ style: "LIGHT" });
  });

  it("never throws when the plugin is missing", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    vi.doMock("@capacitor/haptics", () => {
      throw new Error("not installed");
    });
    const haptics = await import("../src/lib/haptics.js");
    expect(() => {
      haptics.stepComplete();
      haptics.starLit();
    }).not.toThrow();
    await vi.advanceTimersByTimeAsync(500);
  });
});

describe("haptics in the mission", () => {
  const STEPS = [
    { index: 0, kind: "warmup", title: "Warm up", minutes: 2, why: "A slow, even pattern to wake your hands up before the real work.", tempo_bpm: 72, star_entry_id: "e1", piece_title: "Etude" },
    { index: 1, kind: "review", title: "Review", minutes: 3, why: "Nocturne was last played 14 days ago.", tempo_bpm: 66, star_entry_id: "e2", piece_title: "Nocturne" },
  ];
  const mission = (progress = [], next = 0) => ({ id: "m1", day: new Date().toLocaleDateString("en-CA"), kind: "daily", total_minutes: 5, steps: STEPS, progress, completed_at: null, next_index: next });

  async function run(native) {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
    vi.doMock("../src/lib/wakeLock.js", () => ({ keepAwake: vi.fn(async () => () => {}) }));
    mockPlugin();
    const client = await import("../src/api/client.js");
    vi.spyOn(client.api, "missionToday").mockResolvedValue(mission());
    const answers = [
      { mission: mission([{ index: 0, status: "done", seconds: 60, minutes: 1 }], 1), lit: { entry_id: "e1", piece_title: "Etude" }, finished: false, xp: 0, gold: 0, streak: {} },
      { mission: mission([{ index: 0, status: "done" }, { index: 1, status: "skipped" }], null), lit: null, finished: true, xp: 4, gold: 0, streak: { current: 1, longest: 1, today_done: true, min_minutes: 5, minutes_today: 5, state: "lit", freezes: 1, freeze_cap: 2, frozen_days: [], next_freeze_in: 6 } },
    ];
    vi.spyOn(client.api, "missionStep").mockImplementation(async () => answers.shift());
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    const nav = await import("../src/router.js");
    vi.spyOn(nav, "navigate").mockImplementation(() => {});
    const { missionView } = await import("../src/views/mission.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await missionView(outlet, { query: {} });
    return outlet.querySelector(".mission-screen");
  }

  it("buzzes for a finished step and for the star, but not for a skipped one", async () => {
    const root = await run(true);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(40_000);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(impact).toHaveBeenCalledTimes(1);
    expect(impact).toHaveBeenCalledWith({ style: "MEDIUM" });
    await vi.advanceTimersByTimeAsync(200);
    expect(notification).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1500);
    impact.mockClear();
    notification.mockClear();
    root.querySelector('[data-control="skip"]').click();
    await vi.advanceTimersByTimeAsync(400);
    expect(impact).not.toHaveBeenCalled();
    expect(notification).not.toHaveBeenCalled();
  });

  it("stays silent on the web", async () => {
    const root = await run(false);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(40_000);
    root.click();
    await vi.advanceTimersByTimeAsync(500);
    expect(impact).not.toHaveBeenCalled();
    expect(notification).not.toHaveBeenCalled();
  });
});
