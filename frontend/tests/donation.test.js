import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const URL_ = "https://donate.example.test/pedagogue";

async function load({ native = false, url = URL_ } = {}) {
  vi.resetModules();
  vi.stubEnv("VITE_DONATION_URL", url);
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  return import("../src/components/donate.js");
}

async function bootPage({ native = false, url = URL_ } = {}) {
  vi.resetModules();
  vi.stubEnv("VITE_DONATION_URL", url);
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  const client = await import("../src/api/client.js");
  const plan = {
    plan: "free",
    name: "Free",
    limits: { is_pro: false, active_pieces: 5, pdf_score_reading: false, share_cards: false, cloud_sync: false, keyboard_history_attempts: 3, tempo_ladder_ceiling: 0.8 },
    usage: { active_pieces: 1 },
    subscription: null,
    can_start_trial: true,
    trial_days: 7,
    messages: {},
    billing: { checkout: true, portal: false, intervals: ["month"] },
  };
  vi.spyOn(client.api, "billingPlan").mockResolvedValue(plan);
  vi.spyOn(client.api, "billingPrices").mockResolvedValue({ available: true, trial_days: 7, prices: [{ interval: "month", amount: 900, currency: "usd" }] });
  vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c", is_admin: false });
  vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
  vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
  vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
  client.tokenStore.set("token");
  const { store } = await import("../src/lib/store.js");
  await store.hydrate();
}

let outlet;

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
  outlet = document.createElement("main");
  document.body.append(outlet);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("the donation button on the website", () => {
  it("is a link that opens the donation page in a new tab without leaking the opener", async () => {
    const { donateLink, donationAvailable } = await load();
    expect(donationAvailable()).toBe(true);
    const link = donateLink();
    expect(link.getAttribute("href")).toBe(URL_);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.textContent).toBe("Make a donation");
  });

  it("appears in Settings as its own section", async () => {
    await bootPage();
    const { settingsView } = await import("../src/views/settings.js");
    await settingsView(outlet);
    const link = outlet.querySelector("a[data-donate]");
    expect(link.getAttribute("href")).toBe(URL_);
    expect(link.closest("section").textContent).toContain("Support Pedagogue");
    expect(link.closest("section").textContent).toContain("The Free plan stays free.");
  });

  it("appears on the Pricing page as a quiet alternative to Pro", async () => {
    await bootPage();
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.querySelector("a[data-donate]").getAttribute("href")).toBe(URL_);
    expect(outlet.querySelector(".donate-note").textContent).toContain("A one-off donation");
  });

  it("is absent when no donation page is set", async () => {
    const { donateLink, supportSection, donateNote, donationAvailable } = await load({ url: "" });
    expect(donationAvailable()).toBe(false);
    expect([donateLink(), supportSection(), donateNote()]).toEqual([null, null, null]);
  });

  it("refuses an address that is not http or https", async () => {
    const { donateLink } = await load({ url: "javascript:alert(1)" });
    expect(donateLink()).toBe(null);
  });
});

describe("the donation button inside the apps", () => {
  it("is hidden, whatever address is set", async () => {
    const { donateLink, supportSection, donateNote, donationAvailable } = await load({ native: true });
    expect(donationAvailable()).toBe(false);
    expect([donateLink(), supportSection(), donateNote()]).toEqual([null, null, null]);
  });

  it("is missing from Settings", async () => {
    await bootPage({ native: true });
    const { settingsView } = await import("../src/views/settings.js");
    await settingsView(outlet);
    expect(outlet.querySelector("a[data-donate]")).toBe(null);
    expect(outlet.textContent).not.toContain("Support Pedagogue");
    expect(outlet.innerHTML).not.toContain("donate.example.test");
  });

  it("is missing from the Pricing page", async () => {
    await bootPage({ native: true });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.querySelector("a[data-donate]")).toBe(null);
    expect(outlet.innerHTML).not.toContain("donate.example.test");
  });
});

describe("where the address is read", () => {
  const sources = import.meta.glob("../src/**/*.js", { query: "?raw", import: "default", eager: true });

  it("is only used through the donation component", () => {
    const users = Object.entries(sources)
      .filter(([, source]) => /DONATION_URL/.test(source))
      .map(([path]) => path.replace("../src/", ""))
      .sort();
    expect(users).toEqual(["components/donate.js", "lib/features.js"]);
  });
});
