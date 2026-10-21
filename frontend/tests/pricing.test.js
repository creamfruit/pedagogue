import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import mainSource from "../src/main.js?raw";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const LIMITS = { is_pro: false, active_pieces: 5, pdf_score_reading: false, share_cards: false, cloud_sync: false, keyboard_history_attempts: 3, tempo_ladder_ceiling: 0.8 };

const FREE = {
  plan: "free",
  name: "Free",
  limits: LIMITS,
  usage: { active_pieces: 3 },
  subscription: null,
  can_start_trial: true,
  trial_days: 7,
  messages: {},
  billing: { checkout: true, portal: false, intervals: ["month", "year"] },
};

const PRO = {
  ...FREE,
  plan: "pro",
  name: "Pro",
  limits: { ...LIMITS, is_pro: true, active_pieces: null, pdf_score_reading: true, share_cards: true, cloud_sync: true },
  subscription: { status: "active", interval: "month", trial_end: null, current_period_end: "2026-11-21T12:00:00Z", cancel_at_period_end: false, provider: "stripe" },
  can_start_trial: false,
  billing: { checkout: true, portal: true, intervals: ["month", "year"] },
};

const PRICES = {
  available: true,
  trial_days: 7,
  prices: [
    { interval: "month", amount: 900, currency: "usd" },
    { interval: "year", amount: 7900, currency: "usd" },
  ],
};

async function boot({ native = false, plan = FREE, signedIn = true, admin = false, prices = PRICES } = {}) {
  vi.resetModules();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  const client = await import("../src/api/client.js");
  const spies = {
    plan: vi.spyOn(client.api, "billingPlan").mockResolvedValue(plan),
    prices: vi.spyOn(client.api, "billingPrices").mockResolvedValue(prices),
    checkout: vi.spyOn(client.api, "billingCheckout").mockResolvedValue({ url: "https://checkout.stripe.test/c/1" }),
    portal: vi.spyOn(client.api, "billingPortal").mockResolvedValue({ url: "https://billing.stripe.test/p/1" }),
    subscribers: vi.spyOn(client.api, "billingSubscribers"),
  };
  vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c", is_admin: admin });
  vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
  vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
  vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
  if (signedIn) client.tokenStore.set("token");
  else client.tokenStore.clear();
  const { store } = await import("../src/lib/store.js");
  await store.hydrate();
  const billing = await import("../src/lib/billing.js");
  vi.spyOn(billing.redirect, "to").mockImplementation(() => {});
  return { client, spies, store, billing };
}

const buttons = (root) => [...root.querySelectorAll("button")];
const byText = (root, text) => buttons(root).find((button) => button.textContent.includes(text));
const links = (root) => [...root.querySelectorAll("a")].map((link) => link.textContent);

let outlet;

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
  outlet = document.createElement("main");
  document.body.append(outlet);
  window.history.replaceState({}, "", "/pricing");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("describing a plan", () => {
  async function describe_(plan) {
    const { describePlan } = await import("../src/lib/planSummary.js");
    return describePlan(plan);
  }

  it("counts pieces on Free", async () => {
    const summary = await describe_(FREE);
    expect(summary).toMatchObject({ name: "Free", pro: false, warn: false });
    expect(summary.lines).toEqual(["3 of 5 pieces in progress."]);
  });

  it("says when a trial ends and that it charges unless cancelled", async () => {
    const plan = { ...PRO, subscription: { ...PRO.subscription, status: "trialing", trial_end: "2026-10-28T12:00:00Z", current_period_end: "2026-10-28T12:00:00Z" } };
    const summary = await describe_(plan);
    expect(summary.lines[0]).toMatch(/free trial of Pro runs until .*2026/);
    expect(summary.lines[1]).toContain("charged then unless you cancel");
  });

  it("says a trial that is cancelled will not charge", async () => {
    const plan = { ...PRO, subscription: { ...PRO.subscription, status: "trialing", trial_end: "2026-10-28T12:00:00Z", cancel_at_period_end: true } };
    expect((await describe_(plan)).lines[1]).toContain("won't be charged");
  });

  it("says when Pro renews, and when it stops", async () => {
    expect((await describe_(PRO)).lines[0]).toMatch(/^Pro, monthly, renewing on .*2026\.$/);
    const ending = { ...PRO, subscription: { ...PRO.subscription, cancel_at_period_end: true } };
    expect((await describe_(ending)).lines[0]).toMatch(/^Pro until .*2026\. It won't renew\.$/);
  });

  it("warns about a failed payment", async () => {
    const summary = await describe_({ ...PRO, subscription: { ...PRO.subscription, status: "past_due" } });
    expect(summary.warn).toBe(true);
    expect(summary.lines[0]).toContain("last payment didn't go through");
  });

  it("reassures someone whose Pro has ended", async () => {
    const summary = await describe_({ ...FREE, subscription: { status: "canceled", interval: "month", current_period_end: "2026-10-01T12:00:00Z", trial_end: null, cancel_at_period_end: false, provider: "stripe" } });
    expect(summary.pro).toBe(false);
    expect(summary.lines[0]).toMatch(/Your Pro plan ended on .*2026\. Your pieces and history are all still here\./);
  });

  it("works out what the yearly price saves", async () => {
    const { savingsPercent } = await import("../src/lib/planSummary.js");
    expect(savingsPercent([{ interval: "month", amount: 900 }, { interval: "year", amount: 7900 }])).toBe(27);
    expect(savingsPercent([{ interval: "month", amount: 900 }])).toBe(0);
  });
});

describe("the Pricing page on the website", () => {
  it("compares Free and Pro and starts the 7-day trial", async () => {
    const { spies, billing } = await boot();
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    const text = outlet.textContent;
    expect(text).toContain("Up to 5");
    expect(text).toContain("Unlimited");
    expect(text).toContain("Last 3 runs");
    expect(text).toContain("PDF score reading");
    expect(text).toContain("Save 27%");
    expect(text).toContain("Try Pro free for 7 days");
    const start = buttons(outlet).filter((button) => button.textContent === "Start 7-day free trial");
    expect(start).toHaveLength(2);
    start[1].click();
    await flush();
    expect(spies.checkout).toHaveBeenCalledWith({ interval: "year" });
    expect(billing.redirect.to).toHaveBeenCalledWith("https://checkout.stripe.test/c/1");
  });

  it("offers a plain subscribe once the trial has been used", async () => {
    await boot({ plan: { ...FREE, can_start_trial: false } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(buttons(outlet).map((button) => button.textContent).filter((text) => !text.includes("Back"))).toEqual(["Subscribe", "Subscribe"]);
    expect(outlet.textContent).not.toContain("Try Pro free");
  });

  it("tells a signed-out visitor to create an account first, with no buy buttons", async () => {
    const { spies } = await boot({ signedIn: false });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(links(outlet)).toEqual(expect.arrayContaining(["Create a free account", "Sign in"]));
    expect(buttons(outlet).filter((button) => /trial|Subscribe/.test(button.textContent))).toHaveLength(0);
    expect(outlet.textContent).toContain("$9.00");
    expect(spies.checkout).not.toHaveBeenCalled();
  });

  it("shows a Pro member their plan and a way to manage billing", async () => {
    const { spies, billing } = await boot({ plan: PRO });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("You have Pro.");
    expect(spies.prices).not.toHaveBeenCalled();
    byText(outlet, "Manage billing").click();
    await flush();
    expect(spies.portal).toHaveBeenCalled();
    expect(billing.redirect.to).toHaveBeenCalledWith("https://billing.stripe.test/p/1");
  });

  it("says plainly when Pro is not open yet", async () => {
    await boot({ prices: { available: false, trial_days: 7, prices: [] } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("Pro isn't open for sign-up yet");
    expect(buttons(outlet).filter((button) => /trial|Subscribe/.test(button.textContent))).toHaveLength(0);
  });

  it("reports a cancelled checkout without charging anything", async () => {
    await boot();
    window.history.replaceState({}, "", "/pricing?billing=cancelled");
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(document.querySelector(".toast").textContent).toContain("Nothing was charged");
    expect(window.location.search).toBe("");
  });
});

describe("the Pricing page inside the apps", () => {
  it("is only information: no prices, no buttons, no links to buy, no Stripe", async () => {
    const { spies } = await boot({ native: true });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("Your plan");
    expect(buttons(outlet).filter((button) => !button.textContent.includes("Back"))).toHaveLength(0);
    expect(outlet.textContent).not.toMatch(/\$|trial|Subscribe/);
    expect(spies.prices).not.toHaveBeenCalled();
    expect(spies.checkout).not.toHaveBeenCalled();
  });

  it("is not reachable at all: the router sends the apps to Settings", () => {
    expect(mainSource).toMatch(/pathname === PRICING_PATH && !offersVisible\(\)\) return store\.isAuthenticated \? "\/settings" : "\/login"/);
  });
});

describe("the Settings plan section", () => {
  it("offers the trial to someone on Free, on the website", async () => {
    await boot();
    const { billingSection } = await import("../src/views/billingSection.js");
    const section = billingSection();
    expect(section.textContent).toContain("You're on the Free plan.");
    expect(section.textContent).toContain("3 of 5 pieces in progress.");
    const link = section.querySelector("a[href='/pricing']");
    expect(link.textContent).toBe("Try Pro free for 7 days");
  });

  it("offers Manage billing to someone with Pro, and opens the portal", async () => {
    const { spies } = await boot({ plan: PRO });
    const { billingSection } = await import("../src/views/billingSection.js");
    const section = billingSection();
    expect(section.textContent).toContain("You have Pro.");
    expect(section.textContent).toMatch(/renewing on/);
    byText(section, "Manage billing").click();
    await flush();
    expect(spies.portal).toHaveBeenCalled();
  });

  it("shows a failed payment as a warning", async () => {
    await boot({ plan: { ...PRO, subscription: { ...PRO.subscription, status: "past_due" } } });
    const { billingSection } = await import("../src/views/billingSection.js");
    expect(billingSection().querySelector(".plan-warning")).not.toBe(null);
  });

  it("inside the apps shows the plan and nothing to buy or manage", async () => {
    const { spies } = await boot({ native: true, plan: PRO });
    const { billingSection } = await import("../src/views/billingSection.js");
    const section = billingSection();
    expect(section.textContent).toContain("You have Pro.");
    expect(section.querySelectorAll("button, a")).toHaveLength(0);
    const free = await boot({ native: true });
    const { billingSection: again } = await import("../src/views/billingSection.js");
    expect(again().querySelectorAll("button, a")).toHaveLength(0);
    expect(spies.portal).not.toHaveBeenCalled();
    expect(free.spies.portal).not.toHaveBeenCalled();
  });

  it("links administrators to the subscriber list, even in the apps", async () => {
    await boot({ admin: true, native: true });
    const { billingSection } = await import("../src/views/billingSection.js");
    expect(links(billingSection())).toEqual(["Subscribers"]);
  });

  it("does not show the subscriber link to anyone else", async () => {
    await boot();
    const { billingSection } = await import("../src/views/billingSection.js");
    expect(links(billingSection())).not.toContain("Subscribers");
  });

  it("waits for the webhook after Checkout and welcomes the new Pro member", async () => {
    const { spies } = await boot();
    spies.plan.mockResolvedValueOnce(FREE).mockResolvedValue(PRO);
    window.history.replaceState({}, "", "/settings?billing=success");
    const { confirmCheckout } = await import("../src/views/billingSection.js");
    vi.useFakeTimers();
    const done = confirmCheckout();
    await vi.advanceTimersByTimeAsync(1600);
    vi.useRealTimers();
    expect(await done).toBe(true);
    expect(document.querySelector(".toast-success").textContent).toContain("Welcome to Pro");
    expect(window.location.search).toBe("");
  });

  it("does nothing when you did not just come back from Checkout", async () => {
    const { spies } = await boot();
    spies.plan.mockClear();
    window.history.replaceState({}, "", "/settings");
    const { confirmCheckout } = await import("../src/views/billingSection.js");
    expect(await confirmCheckout()).toBe(false);
    expect(spies.plan).not.toHaveBeenCalled();
  });
});

describe("the subscriber list", () => {
  const item = (email, status, extra = {}) => ({
    user_id: email,
    email,
    name: null,
    status,
    is_pro: ["active", "trialing", "past_due"].includes(status),
    interval: "month",
    provider: "stripe",
    trial_end: null,
    current_period_end: "2026-11-21T12:00:00Z",
    cancel_at_period_end: false,
    started_at: "2026-10-01T12:00:00Z",
    ...extra,
  });

  it("is for administrators only", async () => {
    const { spies } = await boot({ admin: false });
    const { subscribersView } = await import("../src/views/subscribers.js");
    await subscribersView(outlet);
    expect(outlet.textContent).toContain("This page is for administrators.");
    expect(spies.subscribers).not.toHaveBeenCalled();
  });

  it("lists people with their status, plan and dates, and filters", async () => {
    const { spies } = await boot({ admin: true });
    spies.subscribers.mockResolvedValue({
      total: 2,
      items: [item("ana@example.com", "trialing", { trial_end: "2026-10-28T12:00:00Z" }), item("bo@example.com", "canceled", { interval: "year" })],
      counts: { pro: 1, by_status: { trialing: 1, canceled: 1 } },
    });
    const { subscribersView } = await import("../src/views/subscribers.js");
    await subscribersView(outlet);
    const rows = [...outlet.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("ana@example.com");
    expect(rows[0].textContent).toContain("Trial");
    expect(rows[0].textContent).toMatch(/Trial ends .*2026/);
    expect(rows[1].textContent).toContain("Cancelled");
    expect(rows[1].textContent).toContain("Yearly");
    expect(outlet.textContent).toContain("1 with Pro now · 2 in total");
    expect(spies.subscribers).toHaveBeenLastCalledWith({ limit: 50, offset: 0, status: undefined });
    const select = outlet.querySelector("select");
    select.value = "pro";
    select.dispatchEvent(new Event("change"));
    await flush();
    expect(spies.subscribers).toHaveBeenLastCalledWith({ limit: 50, offset: 0, status: "pro" });
  });

  it("pages through a long list", async () => {
    const { spies } = await boot({ admin: true });
    spies.subscribers
      .mockResolvedValueOnce({ total: 3, items: [item("a@x.io", "active"), item("b@x.io", "active")], counts: { pro: 3, by_status: { active: 3 } } })
      .mockResolvedValueOnce({ total: 3, items: [item("c@x.io", "active")], counts: { pro: 3, by_status: { active: 3 } } });
    const { subscribersView } = await import("../src/views/subscribers.js");
    await subscribersView(outlet);
    const more = byText(outlet, "Show more");
    expect(more.hidden).toBe(false);
    more.click();
    await flush();
    expect(spies.subscribers).toHaveBeenLastCalledWith({ limit: 50, offset: 2, status: undefined });
    expect(outlet.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(more.hidden).toBe(true);
  });

  it("says when nobody has subscribed", async () => {
    const { spies } = await boot({ admin: true });
    spies.subscribers.mockResolvedValue({ total: 0, items: [], counts: { pro: 0, by_status: {} } });
    const { subscribersView } = await import("../src/views/subscribers.js");
    await subscribersView(outlet);
    expect(outlet.textContent).toContain("Nobody here yet.");
  });
});
