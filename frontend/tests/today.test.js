import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const STEPS = [
  { index: 0, kind: "warmup", title: "Warm up: Rapid scales", minutes: 2, why: "Rapid scales is one of your lowest-rated techniques, so we start there." },
  { index: 1, kind: "passage", title: "Hardest passage: Etude", minutes: 5, why: "Bars 5-8 in Etude is the hardest section you haven't touched lately." },
  { index: 2, kind: "review", title: "Review: Nocturne", minutes: 3, why: "Nocturne was last played 14 days ago, so it's due a quick refresh." },
  { index: 3, kind: "playthrough", title: "Play through: Minuet", minutes: 4, why: "Minuet is closest to your target tempo, so run it start to finish." },
];

function missionBody(extra = {}) {
  return { id: "m1", day: new Date().toLocaleDateString("en-CA"), kind: "daily", total_minutes: 14, steps: STEPS, progress: [], completed_at: null, next_index: 0, ...extra };
}

async function boot(missionImpl) {
  vi.resetModules();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
  const client = await import("../src/api/client.js");
  vi.spyOn(client.api, "missionToday").mockImplementation(missionImpl);
  vi.spyOn(client.api, "repertoireStats").mockResolvedValue({ total: 3, active: 3, average_difficulty: 40, submissions: 0 });
  vi.spyOn(client.api, "load").mockResolvedValue(null);
  vi.spyOn(client.api, "repertoire").mockResolvedValue({ items: [] });
  vi.spyOn(client.api, "meteorShower").mockResolvedValue({ active: null });
  vi.spyOn(client.api, "rouletteToday").mockRejectedValue(new Error("none"));
  vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
  vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
  vi.spyOn(client.api, "billingPlan").mockResolvedValue(null);
  vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c", display_name: "Ana" });
  vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
  client.tokenStore.set("token");
  const { store } = await import("../src/lib/store.js");
  await store.hydrate();
  const { dashboardView } = await import("../src/views/dashboard.js");
  const outlet = document.createElement("main");
  document.body.append(outlet);
  await dashboardView(outlet);
  await flush();
  await flush();
  return { outlet, client };
}

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the Today screen", () => {
  it("is built around one large Start today's mission button", async () => {
    const { outlet } = await boot(async () => missionBody());
    const start = outlet.querySelector(".mission-start");
    expect(start.textContent).toBe("Start today's mission");
    expect(start.getAttribute("href")).toBe("/mission");
    expect(outlet.querySelectorAll(".mission-start")).toHaveLength(1);
    expect(outlet.querySelector(".mission-hero").compareDocumentPosition(outlet.querySelector(".today"))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("shows the four steps with the one-line reason for each and the time it takes", async () => {
    const { outlet } = await boot(async () => missionBody());
    const rows = [...outlet.querySelectorAll(".mission-step-row")];
    expect(rows.map((row) => row.dataset.kind)).toEqual(["warmup", "passage", "review", "playthrough"]);
    expect(rows[2].textContent).toContain("last played 14 days ago");
    expect(outlet.querySelector(".mission-hero-caption").textContent).toContain("14 minutes");
  });

  it("offers to continue a mission that is under way", async () => {
    const { outlet } = await boot(async () => missionBody({ progress: [{ index: 0, status: "done", seconds: 120, minutes: 2 }], next_index: 1 }));
    expect(outlet.querySelector(".mission-start").textContent).toBe("Continue today's mission");
    expect(outlet.querySelector(".mission-step-row.is-done")).not.toBe(null);
  });

  it("says a finished mission is done and points to the lit stars", async () => {
    const { outlet } = await boot(async () => missionBody({ completed_at: new Date().toISOString(), next_index: null, progress: STEPS.map((step) => ({ index: step.index, status: "done", seconds: 60, minutes: 1 })) }));
    expect(outlet.querySelector(".mission-start").textContent).toBe("See your lit stars");
    expect(outlet.querySelector(".mission-hero-caption").textContent).toContain("Nicely done");
  });

  it("still lets the player practise when the mission cannot be built", async () => {
    const { outlet } = await boot(async () => {
      throw new Error("down");
    });
    const start = outlet.querySelector(".mission-start");
    expect(start.getAttribute("href")).toBe("/practice");
    expect(outlet.querySelector(".mission-hero-caption").textContent).toContain("couldn't be built");
  });

  it("keeps the older cards under the mission", async () => {
    const { outlet } = await boot(async () => missionBody());
    expect(outlet.textContent).toContain("More for today");
    expect(outlet.textContent).toContain("Next up");
    expect(outlet.textContent).toContain("This week");
  });
});
