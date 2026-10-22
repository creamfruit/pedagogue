import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const base = { current: 0, longest: 0, today_done: false, minutes_today: 0, min_minutes: 5, next_bonus_xp: 10, last_day: null, freezes: 1, freeze_cap: 2, frozen_days: [], state: "new", next_freeze_in: 7 };

function mockMedia(matches) {
  const listeners = new Set();
  const query = {
    matches,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: (_, handler) => listeners.add(handler),
    removeEventListener: (_, handler) => listeners.delete(handler),
  };
  window.matchMedia = vi.fn(() => query);
  return {
    flip(value) {
      query.matches = value;
      listeners.forEach((handler) => handler({ matches: value }));
    },
  };
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.restoreAllMocks();
  delete window.matchMedia;
});

describe("the streak gauge", () => {
  async function gauge(streak, options) {
    const { streakGauge } = await import("../src/components/streakGauge.js");
    return streakGauge({ ...base, ...streak }, options);
  }

  it("lights the day and counts it", async () => {
    const node = await gauge({ current: 3, state: "lit", today_done: true, longest: 3 });
    expect(node.querySelector(".streak-dial-count").textContent).toBe("3");
    expect(node.textContent).toContain("Today is lit. 3 days in a row.");
    expect(node.querySelectorAll(".streak-ring-seg.is-lit")).toHaveLength(3);
  });

  it("says a missed day was covered by a free streak freeze and the streak is safe", async () => {
    const node = await gauge({ current: 9, state: "covered", freezes: 0, frozen_days: ["2026-10-21"], next_freeze_in: 5 });
    expect(node.textContent).toContain("You rested yesterday, and a streak freeze covered it. Your 9-day streak is safe.");
    expect(node.textContent).toContain("No freezes ready. You earn one after 5 more days in a row.");
    expect(node.dataset.state).toBe("covered");
  });

  it("shows how many freezes are ready", async () => {
    const node = await gauge({ current: 8, state: "waiting", freezes: 2, minutes_today: 2 });
    expect(node.querySelectorAll(".streak-freeze.is-ready")).toHaveLength(2);
    expect(node.textContent).toContain("2 streak freezes ready");
    expect(node.textContent).toContain("Practise 3 more minutes today to keep your 8-day streak glowing.");
  });

  it("starts over with a kind message and keeps the best on the record", async () => {
    const node = await gauge({ current: 0, longest: 14, state: "fresh" });
    expect(node.textContent).toContain("A fresh start. Your best was 14 days, and that stays on your record.");
    expect(node.querySelector(".streak-gauge-message").textContent).not.toMatch(/lost|broke|reset|failed|missed/i);
  });

  it("invites a first day for someone new", async () => {
    const node = await gauge({});
    expect(node.textContent).toContain("Practise 5 minutes today to light your first day.");
  });

  it("wraps the seven-day ring so the eighth day starts a new lap", async () => {
    const node = await gauge({ current: 8, state: "lit", today_done: true });
    expect(node.querySelectorAll(".streak-ring-seg.is-lit")).toHaveLength(1);
    const seventh = await gauge({ current: 7, state: "lit", today_done: true });
    expect(seventh.querySelectorAll(".streak-ring-seg.is-lit")).toHaveLength(7);
  });

  it("returns nothing when there is no streak yet", async () => {
    const { streakGauge } = await import("../src/components/streakGauge.js");
    expect(streakGauge(null)).toBe(null);
  });

  it("is what the Progress and Today summaries now show", async () => {
    const { streakSummary } = await import("../src/views/growth.js");
    const compact = streakSummary({ ...base, current: 2, state: "waiting" }, { compact: true });
    expect(compact.classList.contains("streak-gauge")).toBe(true);
    const full = streakSummary({ ...base, current: 2, longest: 5, state: "waiting" });
    expect(full.textContent).toContain("longest 5");
    expect(full.querySelector(".streak-gauge")).not.toBe(null);
  });
});

describe("the reduced-motion setting", () => {
  it("follows the device until the player asks for less motion", async () => {
    mockMedia(false);
    const motion = await import("../src/lib/motion.js");
    expect(motion.motionSetting()).toBe("system");
    expect(motion.reducedMotion()).toBe(false);
    motion.setMotionSetting("reduce");
    expect(motion.motionSetting()).toBe("reduce");
    expect(motion.reducedMotion()).toBe(true);
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(true);
    motion.setMotionSetting("system");
    expect(motion.reducedMotion()).toBe(false);
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(false);
  });

  it("always honours the device preference, whatever the setting says", async () => {
    mockMedia(true);
    const motion = await import("../src/lib/motion.js");
    expect(motion.motionSetting()).toBe("system");
    expect(motion.reducedMotion()).toBe(true);
    motion.applyMotion();
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(true);
  });

  it("reacts when the device preference changes while the app is open", async () => {
    const media = mockMedia(false);
    vi.resetModules();
    const motion = await import("../src/lib/motion.js");
    const heard = vi.fn();
    motion.onMotionChange(heard);
    motion.watchMotion();
    media.flip(true);
    expect(heard).toHaveBeenCalledWith(true);
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(true);
  });

  it("copes with a browser that has no media queries or storage", async () => {
    const motion = await import("../src/lib/motion.js");
    expect(() => motion.reducedMotion()).not.toThrow();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(motion.motionSetting()).toBe("system");
  });

  it("has a switch in Settings", async () => {
    mockMedia(false);
    vi.resetModules();
    const client = await import("../src/api/client.js");
    vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c", display_name: "Ana" });
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
    vi.spyOn(client.api, "billingPlan").mockResolvedValue(null);
    vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
    client.tokenStore.set("token");
    const { store } = await import("../src/lib/store.js");
    await store.hydrate();
    const { settingsView } = await import("../src/views/settings.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await settingsView(outlet);
    const toggle = outlet.querySelector("#reduce-motion");
    expect(toggle).not.toBe(null);
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    expect(localStorage.getItem("pp.motion")).toBe("reduce");
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(true);
  });

  it("switches animation off in the stylesheet for both the setting and the system preference", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
    expect(css).toMatch(/html\.reduce-motion \*,[\s\S]*?animation-duration: 0\.01ms !important/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });
});

describe("lit stars", () => {
  it("remembers today's stars once each and forgets yesterday's", async () => {
    const lit = await import("../src/lib/litStars.js");
    lit.rememberLit("e1");
    lit.rememberLit("e1");
    lit.rememberLit("e2");
    lit.rememberLit(null);
    expect([...lit.litToday()].sort()).toEqual(["e1", "e2"]);
    localStorage.setItem("pp.lit", JSON.stringify({ day: "2020-01-01", entries: ["old"] }));
    expect([...lit.litToday()]).toEqual([]);
    lit.forgetLit();
    expect(localStorage.getItem("pp.lit")).toBe(null);
  });

  it("builds a star with sparks that a still version can hold without animation", async () => {
    vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
    const { starBurst } = await import("../src/views/mission.js");
    const node = starBurst();
    expect(node.querySelectorAll(".star-burst-spark")).toHaveLength(8);
    expect(node.querySelector(".star-burst-star")).not.toBe(null);
    expect(node.getAttribute("aria-hidden")).toBe("true");
  });
});
