import { beforeEach, describe, expect, it, vi } from "vitest";

const FREE_PLAN = {
  plan: "free",
  name: "Free",
  limits: { is_pro: false, active_pieces: 5, pdf_score_reading: false, share_cards: false, cloud_sync: false, keyboard_history_attempts: 3, tempo_ladder_ceiling: 0.8 },
  messages: {
    active_pieces: { message: "The Free plan keeps 5 pieces in progress at a time.", upgrade: "Finish or shelve one, or move to Pro for as many as you like." },
    pdf_score_reading: { message: "Reading PDF scores is part of Pro.", upgrade: "Move to Pro to have your PDF scores read." },
  },
};

const PRO_PLAN = { ...FREE_PLAN, plan: "pro", name: "Pro", limits: { ...FREE_PLAN.limits, is_pro: true, active_pieces: null, pdf_score_reading: true, share_cards: true, cloud_sync: true } };

async function load({ native = false, plan = FREE_PLAN } = {}) {
  vi.resetModules();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  const client = await import("../src/api/client.js");
  vi.spyOn(client.api, "billingPlan").mockResolvedValue(plan);
  vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c" });
  vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
  vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
  vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
  client.tokenStore.set("token");
  const { store } = await import("../src/lib/store.js");
  await store.hydrate();
  const planLib = await import("../src/lib/plan.js");
  const prompt = await import("../src/components/upgradePrompt.js");
  return { client, store, planLib, prompt };
}

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
  localStorage.clear();
});

describe("plan state", () => {
  it("loads the plan with the signed-in user and answers feature questions", async () => {
    const { planLib } = await load();
    expect(planLib.isPro()).toBe(false);
    expect(planLib.canUse("pdf_score_reading")).toBe(false);
    expect(planLib.canUse("share_cards")).toBe(false);
  });

  it("opens every Pro feature for a Pro user", async () => {
    const { planLib } = await load({ plan: PRO_PLAN });
    expect(planLib.isPro()).toBe(true);
    expect(planLib.canUse("pdf_score_reading")).toBe(true);
    expect(planLib.canUse("cloud_sync")).toBe(true);
  });

  it("does not lock client-only features when the plan could not be loaded", async () => {
    vi.resetModules();
    const client = await import("../src/api/client.js");
    vi.spyOn(client.api, "billingPlan").mockRejectedValue(new Error("down"));
    vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c" });
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
    vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
    client.tokenStore.set("token");
    const { store } = await import("../src/lib/store.js");
    await store.hydrate();
    const planLib = await import("../src/lib/plan.js");
    expect(store.plan).toBe(null);
    expect(planLib.canUse("share_cards")).toBe(true);
  });

  it("forgets the plan on sign out", async () => {
    const { store } = await load();
    expect(store.plan.plan).toBe("free");
    store.signOut();
    expect(store.plan).toBe(null);
  });
});

describe("plan limit errors", () => {
  it("are recognised from the 402 body and read as their message", async () => {
    const { client } = await load();
    const detail = { code: "plan_limit", feature: "active_pieces", message: "The Free plan keeps 5 pieces in progress at a time.", upgrade: "Move to Pro." };
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 402, headers: { "content-type": "application/json" } }));
    const error = await client.request("/repertoire", { method: "POST", body: {} }).catch((caught) => caught);
    expect(error.isPlanLimit).toBe(true);
    expect(error.planFeature).toBe("active_pieces");
    expect(error.detail).toBe(detail.message);
  });

  it("are not confused with other errors", async () => {
    const { client } = await load();
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "nope" }), { status: 409, headers: { "content-type": "application/json" } }));
    const error = await client.request("/repertoire", { method: "POST", body: {} }).catch((caught) => caught);
    expect(error.isPlanLimit).toBe(false);
    expect(error.detail).toBe("nope");
  });
});

describe("upgrade prompts on the website", () => {
  it("explains the limit and offers a way to see Pro", async () => {
    const { prompt } = await load();
    prompt.showUpgrade("active_pieces");
    const text = document.body.textContent;
    expect(text).toContain("The Free plan keeps 5 pieces in progress at a time.");
    expect(text).toContain("Finish or shelve one");
    expect([...document.querySelectorAll("button")].some((button) => button.textContent === "See Pro")).toBe(true);
  });

  it("turns a plan-limit failure into the prompt and any other failure into a toast", async () => {
    const { client, prompt } = await load();
    const limit = new client.ApiError(402, "The Free plan keeps 5 pieces in progress at a time.", { detail: { code: "plan_limit", feature: "active_pieces", message: "The Free plan keeps 5 pieces in progress at a time.", upgrade: "Move to Pro." } });
    expect(prompt.explainFailure(limit, "fallback")).toBe(true);
    expect(document.querySelector(".modal")).not.toBe(null);
    document.body.innerHTML = '<div id="toasts"></div>';
    expect(prompt.explainFailure(new client.ApiError(500, "boom"), "fallback")).toBe(false);
    expect(document.querySelector(".toast-error").textContent).toBe("boom");
  });

  it("renders an inline notice that links to the pricing page", async () => {
    const { prompt } = await load();
    const notice = prompt.upgradeNotice("pdf_score_reading");
    expect(notice.textContent).toContain("Reading PDF scores is part of Pro.");
    expect(notice.querySelector("a").getAttribute("href")).toBe("/pricing");
  });
});

describe("upgrade prompts inside the apps", () => {
  it("say what is limited but carry no button or link to buy", async () => {
    const { prompt } = await load({ native: true });
    prompt.showUpgrade("active_pieces");
    const text = document.body.textContent;
    expect(text).toContain("The Free plan keeps 5 pieces in progress at a time.");
    expect(text).not.toContain("move to Pro");
    expect(text).not.toContain("See Pro");
    expect(document.querySelector("a")).toBe(null);
    const notice = prompt.upgradeNotice("pdf_score_reading");
    expect(notice.querySelector("a")).toBe(null);
    expect(notice.textContent).not.toContain("Move to Pro");
  });
});

describe("cloud sync on the device", () => {
  async function readRepertoire(plan) {
    const loaded = await load({ plan });
    const { deviceStore } = await import("../src/lib/deviceStore.js");
    const saved = vi.spyOn(deviceStore, "set").mockResolvedValue(true);
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "content-type": "application/json" } }));
    await loaded.client.request("/repertoire");
    return saved.mock.calls.map(([key]) => key);
  }

  it("keeps an offline copy of your data for Pro", async () => {
    const keys = await readRepertoire(PRO_PLAN);
    expect(keys.some((key) => key.startsWith("cache:") && key.includes("/repertoire"))).toBe(true);
  });

  it("keeps no offline copy of your data on Free, other than the plan itself", async () => {
    const keys = await readRepertoire(FREE_PLAN);
    expect(keys.filter((key) => key.includes("/repertoire"))).toEqual([]);
  });
});
