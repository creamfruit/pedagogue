import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SHOWN = {
  available: true,
  trial_days: 7,
  prices: [
    { interval: "month", amount: 900, currency: "usd" },
    { interval: "year", amount: 7900, currency: "usd" },
  ],
};

async function load({ native = false } = {}) {
  vi.resetModules();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  const client = await import("../src/api/client.js");
  const spies = {
    prices: vi.spyOn(client.api, "billingPrices").mockResolvedValue(SHOWN),
    checkout: vi.spyOn(client.api, "billingCheckout").mockResolvedValue({ url: "https://checkout.stripe.test/c/1" }),
    portal: vi.spyOn(client.api, "billingPortal").mockResolvedValue({ url: "https://billing.stripe.test/p/1" }),
    plan: vi.spyOn(client.api, "billingPlan").mockResolvedValue({ plan: "pro", limits: { is_pro: true } }),
  };
  const billing = await import("../src/lib/billing.js");
  const iap = await import("../src/lib/inAppPurchases.js");
  const { store } = await import("../src/lib/store.js");
  vi.spyOn(billing.redirect, "to").mockImplementation(() => {});
  return { billing, iap, spies, store, client };
}

function fakeProvider(overrides = {}) {
  return {
    name: "revenuecat",
    isAvailable: () => true,
    loadOfferings: vi.fn(async () => [{ id: "pro_monthly", interval: "month", price: "$9.00", trialDays: 7 }]),
    purchase: vi.fn(async () => ({ entitled: true })),
    restore: vi.fn(async () => ({ restored: true })),
    manage: vi.fn(async () => {}),
    ...overrides,
  };
}

async function signIn({ client, store }) {
  vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c" });
  vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
  vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
  vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
  client.tokenStore.set("token");
  await store.hydrate();
}

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("on the website", () => {
  it("sells through Stripe and shows prices from the backend", async () => {
    const { billing, spies } = await load();
    expect(billing.billingMode()).toBe("stripe");
    expect(billing.offersVisible()).toBe(true);
    const options = await billing.loadOptions();
    expect(spies.prices).toHaveBeenCalled();
    expect(options.map((option) => [option.interval, option.label, option.trialDays])).toEqual([
      ["month", "Monthly", 7],
      ["year", "Yearly", 7],
    ]);
    expect(options[0].price).toMatch(/9/);
  });

  it("shows no options while the backend says checkout is not open", async () => {
    const { billing, spies } = await load();
    spies.prices.mockResolvedValue({ available: false, trial_days: 7, prices: [] });
    expect(await billing.loadOptions()).toEqual([]);
  });

  it("starts Checkout and sends the browser there", async () => {
    const { billing, spies } = await load();
    const result = await billing.subscribe({ interval: "year" });
    expect(spies.checkout).toHaveBeenCalledWith({ interval: "year" });
    expect(billing.redirect.to).toHaveBeenCalledWith("https://checkout.stripe.test/c/1");
    expect(result.redirected).toBe(true);
  });

  it("opens the customer portal", async () => {
    const { billing, spies } = await load();
    await billing.manageBilling();
    expect(spies.portal).toHaveBeenCalled();
    expect(billing.redirect.to).toHaveBeenCalledWith("https://billing.stripe.test/p/1");
  });

  it("ignores a registered in-app provider, because the website sells through Stripe", async () => {
    const { billing, iap } = await load();
    const provider = fakeProvider();
    iap.registerInAppPurchaseProvider(provider);
    expect(billing.billingMode()).toBe("stripe");
    await billing.subscribe({ interval: "month" });
    expect(provider.purchase).not.toHaveBeenCalled();
  });
});

describe("inside the iOS and Android apps", () => {
  it("sells nothing and never touches Stripe", async () => {
    const { billing, spies } = await load({ native: true });
    expect(billing.billingMode()).toBe("none");
    expect(billing.offersVisible()).toBe(false);
    expect(billing.stripeAllowed()).toBe(false);
    expect(await billing.loadOptions()).toEqual([]);
    await expect(billing.subscribe({ interval: "month" })).rejects.toThrow();
    await expect(billing.manageBilling()).rejects.toThrow();
    expect(await billing.restorePurchases()).toEqual({ restored: false });
    expect(spies.prices).not.toHaveBeenCalled();
    expect(spies.checkout).not.toHaveBeenCalled();
    expect(spies.portal).not.toHaveBeenCalled();
    expect(billing.redirect.to).not.toHaveBeenCalled();
  });

  it("has no provider until one is registered", async () => {
    const { iap } = await load({ native: true });
    expect(iap.inAppPurchases.available).toBe(false);
    expect(iap.inAppPurchases.providerName).toBe("none");
    expect(await iap.inAppPurchases.loadOfferings()).toEqual([]);
    await expect(iap.inAppPurchases.purchase({})).rejects.toThrow("not available");
  });
});

describe("when a provider such as RevenueCat is registered in the apps", () => {
  async function withProvider(overrides) {
    const loaded = await load({ native: true });
    const provider = fakeProvider(overrides);
    loaded.iap.registerInAppPurchaseProvider(provider);
    return { ...loaded, provider };
  }

  it("switches to in-app purchases and still never uses Stripe", async () => {
    const { billing, provider, spies } = await withProvider();
    expect(billing.billingMode()).toBe("in-app");
    expect(billing.offersVisible()).toBe(true);
    const options = await billing.loadOptions();
    expect(options).toEqual([{ id: "pro_monthly", interval: "month", label: "Monthly", price: "$9.00", trialDays: 7 }]);
    expect(provider.loadOfferings).toHaveBeenCalled();
    expect(spies.prices).not.toHaveBeenCalled();
  });

  it("buys through the provider and then reloads the plan", async () => {
    const loaded = await withProvider();
    await signIn(loaded);
    loaded.spies.plan.mockClear();
    const result = await loaded.billing.subscribe({ id: "pro_monthly", interval: "month" });
    expect(loaded.provider.purchase).toHaveBeenCalledWith({ id: "pro_monthly", interval: "month" });
    expect(loaded.spies.plan).toHaveBeenCalled();
    expect(result.entitled).toBe(true);
    expect(loaded.spies.checkout).not.toHaveBeenCalled();
    expect(loaded.billing.redirect.to).not.toHaveBeenCalled();
  });

  it("manages and restores through the provider", async () => {
    const loaded = await withProvider();
    await signIn(loaded);
    await loaded.billing.manageBilling();
    expect(loaded.provider.manage).toHaveBeenCalled();
    expect(await loaded.billing.restorePurchases()).toEqual({ restored: true });
    expect(loaded.spies.portal).not.toHaveBeenCalled();
  });

  it("goes back to showing nothing if the provider says it is not available", async () => {
    const { billing } = await withProvider({ isAvailable: () => false });
    expect(billing.billingMode()).toBe("none");
  });
});

describe("registering a provider", () => {
  it("refuses one that is missing parts of the interface", async () => {
    const { iap } = await load({ native: true });
    expect(() => iap.registerInAppPurchaseProvider({ name: "half", isAvailable: () => true })).toThrow(/loadOfferings, purchase, restore, manage/);
    expect(() => iap.registerInAppPurchaseProvider(null)).toThrow();
    expect(iap.inAppPurchases.providerName).toBe("none");
  });

  it("can be cleared again", async () => {
    const { iap } = await load({ native: true });
    iap.registerInAppPurchaseProvider(fakeProvider());
    expect(iap.inAppPurchases.available).toBe(true);
    iap.clearInAppPurchaseProvider();
    expect(iap.inAppPurchases.available).toBe(false);
  });
});

describe("the apps' bundle", () => {
  const sources = import.meta.glob("../src/**/*.js", { query: "?raw", import: "default", eager: true });

  it("reaches Stripe only through lib/billing.js", () => {
    const callers = Object.entries(sources)
      .filter(([path, source]) => /billingCheckout|billingPortal|billingPrices/.test(source) && !path.endsWith("/api/client.js"))
      .map(([path]) => path.replace("../src/", ""));
    expect(callers).toEqual(["lib/billing.js"]);
  });

  it("holds no Stripe addresses or keys in the source", () => {
    const offenders = Object.entries(sources)
      .filter(([, source]) => /stripe\.com|js\.stripe|pk_live|pk_test|sk_live|sk_test/.test(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
