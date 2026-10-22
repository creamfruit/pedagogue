import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function product(overrides = {}) {
  return {
    identifier: "pedagogue_pro_monthly",
    priceString: "$9.99",
    price: 9.99,
    currencyCode: "USD",
    introPrice: null,
    defaultOption: null,
    ...overrides,
  };
}

function monthly(overrides = {}) {
  return { identifier: "$rc_monthly", packageType: "MONTHLY", product: product(overrides) };
}

function annual(overrides = {}) {
  return { identifier: "$rc_annual", packageType: "ANNUAL", product: product({ identifier: "pedagogue_pro_yearly", priceString: "$79.99", price: 79.99, ...overrides }) };
}

function fakePurchases(overrides = {}) {
  return {
    configure: vi.fn(async () => {}),
    logIn: vi.fn(async () => ({})),
    logOut: vi.fn(async () => ({})),
    getOfferings: vi.fn(async () => ({ current: { availablePackages: [annual(), monthly()] } })),
    checkTrialOrIntroductoryPriceEligibility: vi.fn(async () => ({})),
    purchasePackage: vi.fn(async () => ({ customerInfo: { entitlements: { active: { pro: {} } } } })),
    restorePurchases: vi.fn(async () => ({ customerInfo: { entitlements: { active: { pro: {} } } } })),
    getCustomerInfo: vi.fn(async () => ({ customerInfo: { managementURL: "https://apps.apple.com/account/subscriptions" } })),
    ...overrides,
  };
}

async function load({ platform = "ios", userId = "user-1" } = {}) {
  vi.resetModules();
  const native = platform !== "web";
  vi.doMock("../src/lib/platform.js", () => ({
    isNative: native,
    isIOS: platform === "ios",
    isAndroid: platform === "android",
    platformName: platform,
  }));
  const module = await import("../src/lib/revenuecat.js");
  const iap = await import("../src/lib/inAppPurchases.js");
  const purchases = fakePurchases();
  const provider = module.createRevenueCatProvider(purchases, { getUserId: () => userId });
  return { module, iap, purchases, provider };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.doUnmock("@revenuecat/purchases-capacitor");
  vi.restoreAllMocks();
});

describe("reading the offerings", () => {
  it("shows the store's own monthly and yearly prices, monthly first", async () => {
    const { provider } = await load();
    const options = await provider.loadOfferings();
    expect(options.map((option) => [option.id, option.interval, option.price, option.amount, option.currency])).toEqual([
      ["$rc_monthly", "month", "$9.99", 999, "usd"],
      ["$rc_annual", "year", "$79.99", 7999, "usd"],
    ]);
  });

  it("leaves out packages that are not monthly or yearly", async () => {
    const { provider, purchases } = await load();
    purchases.getOfferings.mockResolvedValue({ current: { availablePackages: [monthly(), { identifier: "$rc_lifetime", packageType: "LIFETIME", product: product() }] } });
    expect((await provider.loadOfferings()).map((option) => option.interval)).toEqual(["month"]);
  });

  it("returns nothing when there is no current offering", async () => {
    const { provider, purchases } = await load();
    purchases.getOfferings.mockResolvedValue({ current: null });
    expect(await provider.loadOfferings()).toEqual([]);
  });

  it("shows a 7-day trial on iPhone when the customer is eligible", async () => {
    const { provider, purchases } = await load({ platform: "ios" });
    const intro = { price: 0, cycles: 1, periodUnit: "DAY", periodNumberOfUnits: 7 };
    purchases.getOfferings.mockResolvedValue({ current: { availablePackages: [monthly({ introPrice: intro })] } });
    purchases.checkTrialOrIntroductoryPriceEligibility.mockResolvedValue({ pedagogue_pro_monthly: { status: 2 } });
    expect((await provider.loadOfferings())[0].trialDays).toBe(7);
  });

  it("shows no trial on iPhone when the customer already used it or the store can't tell", async () => {
    const { provider, purchases } = await load({ platform: "ios" });
    const intro = { price: 0, cycles: 1, periodUnit: "DAY", periodNumberOfUnits: 7 };
    purchases.getOfferings.mockResolvedValue({ current: { availablePackages: [monthly({ introPrice: intro })] } });
    purchases.checkTrialOrIntroductoryPriceEligibility.mockResolvedValue({ pedagogue_pro_monthly: { status: 1 } });
    expect((await provider.loadOfferings())[0].trialDays).toBe(0);
    purchases.checkTrialOrIntroductoryPriceEligibility.mockResolvedValue({ pedagogue_pro_monthly: { status: 0 } });
    expect((await provider.loadOfferings())[0].trialDays).toBe(0);
    purchases.checkTrialOrIntroductoryPriceEligibility.mockRejectedValue(new Error("offline"));
    expect((await provider.loadOfferings())[0].trialDays).toBe(0);
  });

  it("does not count a paid introductory price as a free trial", async () => {
    const { provider, purchases } = await load({ platform: "ios" });
    const intro = { price: 0.99, cycles: 1, periodUnit: "MONTH", periodNumberOfUnits: 1 };
    purchases.getOfferings.mockResolvedValue({ current: { availablePackages: [monthly({ introPrice: intro })] } });
    purchases.checkTrialOrIntroductoryPriceEligibility.mockResolvedValue({ pedagogue_pro_monthly: { status: 2 } });
    expect((await provider.loadOfferings())[0].trialDays).toBe(0);
  });

  it("shows the free phase of the offer Google Play picked for this customer", async () => {
    const { provider, purchases } = await load({ platform: "android" });
    const defaultOption = { freePhase: { billingPeriod: { unit: "DAY", value: 7, iso8601: "P7D" } } };
    purchases.getOfferings.mockResolvedValue({ current: { availablePackages: [monthly({ defaultOption }), annual()] } });
    const options = await provider.loadOfferings();
    expect(options.map((option) => option.trialDays)).toEqual([7, 0]);
    expect(purchases.checkTrialOrIntroductoryPriceEligibility).not.toHaveBeenCalled();
  });

  it("reads a free trial given in weeks", async () => {
    const { module } = await load({ platform: "android" });
    expect(module.trialDaysOf({ defaultOption: { freePhase: { billingPeriod: { unit: "WEEK", value: 1 } } } })).toBe(7);
  });
});

describe("buying, restoring and managing", () => {
  it("buys the chosen package and says the customer is entitled", async () => {
    const { provider, purchases } = await load();
    const [month] = await provider.loadOfferings();
    const result = await provider.purchase(month);
    expect(purchases.purchasePackage).toHaveBeenCalledWith({ aPackage: expect.objectContaining({ identifier: "$rc_monthly" }) });
    expect(result).toEqual({ entitled: true, cancelled: false });
  });

  it("treats closing the store sheet as a cancel, not an error", async () => {
    const { provider, purchases } = await load();
    const [month] = await provider.loadOfferings();
    purchases.purchasePackage.mockRejectedValue({ userCancelled: true, code: "1", message: "cancelled" });
    expect(await provider.purchase(month)).toEqual({ entitled: false, cancelled: true });
    purchases.purchasePackage.mockRejectedValue({ code: "1", message: "cancelled" });
    expect((await provider.purchase(month)).cancelled).toBe(true);
  });

  it("passes a real store error on in plain words", async () => {
    const { provider, purchases } = await load();
    const [month] = await provider.loadOfferings();
    purchases.purchasePackage.mockRejectedValue({ code: "2", message: "The payment method was declined." });
    await expect(provider.purchase(month)).rejects.toThrow("The payment method was declined.");
  });

  it("refuses a package that was never offered", async () => {
    const { provider } = await load();
    await expect(provider.purchase({ id: "$rc_weekly" })).rejects.toThrow(/isn't available/);
  });

  it("restores earlier purchases", async () => {
    const { provider, purchases } = await load();
    expect(await provider.restore()).toEqual({ restored: true });
    purchases.restorePurchases.mockResolvedValue({ customerInfo: { entitlements: { active: {} } } });
    expect(await provider.restore()).toEqual({ restored: false });
  });

  it("opens the store's own subscription page to manage", async () => {
    const { module, provider, purchases } = await load();
    const open = vi.spyOn(module.opener, "open").mockImplementation(() => {});
    await provider.manage();
    expect(open).toHaveBeenCalledWith("https://apps.apple.com/account/subscriptions");
    purchases.getCustomerInfo.mockRejectedValue(new Error("offline"));
    await provider.manage();
    expect(open).toHaveBeenLastCalledWith("https://apps.apple.com/account/subscriptions");
  });

  it("falls back to Google Play's subscription page on Android", async () => {
    const { module, provider, purchases } = await load({ platform: "android" });
    const open = vi.spyOn(module.opener, "open").mockImplementation(() => {});
    purchases.getCustomerInfo.mockResolvedValue({ customerInfo: { managementURL: null } });
    await provider.manage();
    expect(open).toHaveBeenCalledWith("https://play.google.com/store/account/subscriptions");
  });
});

describe("linking the customer to the Pedagogue user", () => {
  it("logs RevenueCat in as the Pedagogue user id before reading offerings or buying", async () => {
    const { provider, purchases } = await load({ userId: "6f1c0b52-2d3e-4a47-9b8a-0a1f6f6f0e11" });
    await provider.loadOfferings();
    expect(purchases.logIn).toHaveBeenCalledWith({ appUserID: "6f1c0b52-2d3e-4a47-9b8a-0a1f6f6f0e11" });
    await provider.loadOfferings();
    expect(purchases.logIn).toHaveBeenCalledTimes(1);
  });

  it("logs out when the person signs out, and in again as the next person", async () => {
    let current = "user-1";
    const { module } = await load();
    const purchases = fakePurchases();
    const provider = module.createRevenueCatProvider(purchases, { getUserId: () => current });
    await provider.syncUser();
    current = undefined;
    await provider.syncUser();
    current = "user-2";
    await provider.syncUser();
    expect(purchases.logIn.mock.calls.map((call) => call[0].appUserID)).toEqual(["user-1", "user-2"]);
    expect(purchases.logOut).toHaveBeenCalledTimes(1);
  });

  it("does not log out a customer who was never logged in", async () => {
    const { module } = await load();
    const purchases = fakePurchases();
    const provider = module.createRevenueCatProvider(purchases, { getUserId: () => null });
    await provider.syncUser();
    expect(purchases.logIn).not.toHaveBeenCalled();
    expect(purchases.logOut).not.toHaveBeenCalled();
  });
});

describe("starting RevenueCat", () => {
  async function start({ platform, env = {}, plugin = fakePurchases() }) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({
      isNative: platform !== "web",
      isIOS: platform === "ios",
      isAndroid: platform === "android",
      platformName: platform,
    }));
    vi.doMock("@revenuecat/purchases-capacitor", () => ({ Purchases: plugin }));
    for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
    const module = await import("../src/lib/revenuecat.js");
    const iap = await import("../src/lib/inAppPurchases.js");
    const started = await module.startPurchases({ getUserId: () => "user-1" });
    return { module, iap, plugin, started };
  }

  const KEYS = { VITE_REVENUECAT_IOS_API_KEY: "appl_ios_key", VITE_REVENUECAT_ANDROID_API_KEY: "goog_android_key" };

  it("never starts on the website, even with keys set", async () => {
    const { plugin, iap, started } = await start({ platform: "web", env: KEYS });
    expect(started).toBe(null);
    expect(plugin.configure).not.toHaveBeenCalled();
    expect(iap.inAppPurchases.available).toBe(false);
  });

  it("uses the iOS key on iPhone", async () => {
    const { plugin, iap } = await start({ platform: "ios", env: KEYS });
    expect(plugin.configure).toHaveBeenCalledWith({ apiKey: "appl_ios_key" });
    expect(iap.inAppPurchases.providerName).toBe("revenuecat");
    expect(iap.inAppPurchases.available).toBe(true);
    expect(plugin.logIn).toHaveBeenCalledWith({ appUserID: "user-1" });
  });

  it("uses the Android key on Android", async () => {
    const { plugin } = await start({ platform: "android", env: KEYS });
    expect(plugin.configure).toHaveBeenCalledWith({ apiKey: "goog_android_key" });
  });

  it("sells nothing in the app when its key is not set", async () => {
    const { plugin, iap, started } = await start({ platform: "ios", env: { VITE_REVENUECAT_IOS_API_KEY: "  ", VITE_REVENUECAT_ANDROID_API_KEY: "goog_android_key" } });
    expect(started).toBe(null);
    expect(plugin.configure).not.toHaveBeenCalled();
    expect(iap.inAppPurchases.available).toBe(false);
  });

  it("stays off if RevenueCat refuses to start", async () => {
    const plugin = fakePurchases({ configure: vi.fn(async () => { throw new Error("bad key"); }) });
    const { iap, started } = await start({ platform: "ios", env: KEYS, plugin });
    expect(started).toBe(null);
    expect(iap.inAppPurchases.available).toBe(false);
  });
});

const PRO_PLAN = { plan: "pro", limits: { is_pro: true }, subscription: { status: "active", provider: "revenuecat", interval: "month" } };
const FREE_PLAN = { plan: "free", name: "Free", limits: { is_pro: false, active_pieces: 5, keyboard_history_attempts: 3, tempo_ladder_ceiling: 0.8 }, usage: { active_pieces: 1 }, subscription: null, can_start_trial: false, trial_days: 7, billing: {} };

describe("the Pro upgrade screen inside the apps", () => {
  let outlet;

  beforeEach(() => {
    document.body.innerHTML = '<div id="toasts"></div>';
    outlet = document.createElement("main");
    document.body.append(outlet);
    window.history.replaceState({}, "", "/pricing");
    vi.stubEnv("VITE_DONATION_URL", "https://donate.example.test/pedagogue");
  });

  async function boot({ plan = FREE_PLAN, offerings, purchase, restore } = {}) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    const client = await import("../src/api/client.js");
    const spies = {
      plan: vi.spyOn(client.api, "billingPlan").mockResolvedValue(plan),
      prices: vi.spyOn(client.api, "billingPrices").mockResolvedValue({ available: true, trial_days: 7, prices: [] }),
      checkout: vi.spyOn(client.api, "billingCheckout"),
      portal: vi.spyOn(client.api, "billingPortal"),
    };
    vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c" });
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
    vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
    client.tokenStore.set("token");
    const { store } = await import("../src/lib/store.js");
    await store.hydrate();
    const billing = await import("../src/lib/billing.js");
    billing.settle.attempts = 3;
    billing.settle.wait = 0;
    const iap = await import("../src/lib/inAppPurchases.js");
    const provider = {
      name: "revenuecat",
      isAvailable: () => true,
      loadOfferings: vi.fn(async () => offerings ?? [
        { id: "$rc_monthly", interval: "month", price: "$9.99", amount: 999, currency: "usd", trialDays: 7 },
        { id: "$rc_annual", interval: "year", price: "$79.99", amount: 7999, currency: "usd", trialDays: 0 },
      ]),
      purchase: vi.fn(purchase ?? (async () => ({ entitled: true, cancelled: false }))),
      restore: vi.fn(restore ?? (async () => ({ restored: true }))),
      manage: vi.fn(async () => {}),
    };
    iap.registerInAppPurchaseProvider(provider);
    return { spies, store, provider, billing };
  }

  const buttons = () => [...outlet.querySelectorAll("button")];
  const byText = (text) => buttons().find((button) => button.textContent.includes(text));

  it("shows the store's prices and the trial only where the store offers it", async () => {
    await boot();
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("$9.99 / month");
    expect(outlet.textContent).toContain("$79.99 / year");
    expect(outlet.textContent).toContain("Save 33%");
    expect(buttons().filter((button) => button.textContent === "Start 7-day free trial")).toHaveLength(1);
    expect(buttons().filter((button) => button.textContent === "Subscribe")).toHaveLength(1);
    expect(outlet.textContent).toContain("Try Pro free for 7 days");
    expect(outlet.textContent).toContain("charged when the trial ends unless you cancel at least 24 hours before");
    expect(outlet.textContent).toContain("renews automatically");
    expect([...outlet.querySelectorAll("a")].map((link) => link.getAttribute("href"))).toEqual(expect.arrayContaining(["/terms", "/privacy"]));
  });

  it("offers no trial when the store offers none", async () => {
    await boot({ offerings: [{ id: "$rc_monthly", interval: "month", price: "$9.99", amount: 999, currency: "usd", trialDays: 0 }] });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).not.toContain("Try Pro free");
    expect(buttons().filter((button) => button.textContent === "Subscribe")).toHaveLength(1);
  });

  it("starts the store purchase for the chosen plan and welcomes the new member", async () => {
    const { provider, spies, billing } = await boot();
    spies.plan.mockResolvedValueOnce(FREE_PLAN).mockResolvedValue(PRO_PLAN);
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    byText("Start 7-day free trial").click();
    await flush();
    await flush();
    expect(provider.purchase).toHaveBeenCalledWith(expect.objectContaining({ id: "$rc_monthly", interval: "month" }));
    expect(document.querySelector(".toast-success").textContent).toContain("Welcome to Pro");
    expect(spies.checkout).not.toHaveBeenCalled();
    expect(spies.prices).not.toHaveBeenCalled();
    expect(billing.billingMode()).toBe("in-app");
  });

  it("says the purchase is being confirmed when the webhook has not arrived yet", async () => {
    await boot();
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    byText("Subscribe").click();
    await flush();
    await flush();
    await flush();
    expect(document.querySelector(".toast-info").textContent).toContain("Your purchase went through");
    expect(byText("Subscribe").disabled).toBe(false);
  });

  it("does nothing, and shows no error, when the customer closes the store sheet", async () => {
    const { spies } = await boot({ purchase: async () => ({ entitled: false, cancelled: true }) });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    spies.plan.mockClear();
    byText("Subscribe").click();
    await flush();
    await flush();
    expect(document.querySelector(".toast")).toBe(null);
    expect(spies.plan).not.toHaveBeenCalled();
    expect(byText("Subscribe").disabled).toBe(false);
  });

  it("shows a store error and lets the customer try again", async () => {
    await boot({ purchase: async () => { throw new Error("The payment method was declined."); } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    byText("Subscribe").click();
    await flush();
    expect(document.querySelector(".toast-error").textContent).toContain("declined");
    expect(byText("Subscribe").disabled).toBe(false);
  });

  it("restores purchases from the Pro screen", async () => {
    const { provider, spies } = await boot();
    spies.plan.mockResolvedValueOnce(FREE_PLAN).mockResolvedValue(PRO_PLAN);
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    byText("Restore purchases").click();
    await flush();
    await flush();
    expect(provider.restore).toHaveBeenCalled();
    expect(document.querySelector(".toast-success").textContent).toContain("restored");
  });

  it("tells the customer when there is nothing to restore", async () => {
    await boot({ restore: async () => ({ restored: false }) });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    byText("Restore purchases").click();
    await flush();
    await flush();
    expect(document.querySelector(".toast-info").textContent).toContain("No earlier purchase");
  });

  it("shows a Pro member a way to manage the subscription in the store", async () => {
    const { provider } = await boot({ plan: { ...FREE_PLAN, ...PRO_PLAN, usage: { active_pieces: 1 } } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("You have Pro.");
    byText("Manage subscription").click();
    await flush();
    expect(provider.manage).toHaveBeenCalled();
  });

  it("offers no manage button for a subscription bought on the website, and says nothing about the store", async () => {
    await boot({ plan: { ...FREE_PLAN, ...PRO_PLAN, subscription: { ...PRO_PLAN.subscription, provider: "stripe" } } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("You have Pro.");
    expect(outlet.textContent).not.toContain("App Store");
    expect(byText("Manage subscription")).toBeUndefined();
    const { billingSection } = await import("../src/views/billingSection.js");
    expect([...billingSection().querySelectorAll("button")].map((button) => button.textContent)).toEqual(["Restore purchases"]);
  });

  it("tells a store subscriber the subscription is managed in the store", async () => {
    await boot({ plan: { ...FREE_PLAN, ...PRO_PLAN } });
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    expect(outlet.textContent).toContain("Bought in the App Store or Google Play. Manage or cancel it there.");
  });

  it("keeps every Stripe and donation link out of the screens", async () => {
    const { spies } = await boot();
    const { pricingView } = await import("../src/views/pricing.js");
    await pricingView(outlet);
    const { billingSection } = await import("../src/views/billingSection.js");
    const { supportSection } = await import("../src/components/donate.js");
    const { DONATION_URL } = await import("../src/lib/features.js");
    const section = billingSection();
    document.body.append(section);
    expect(DONATION_URL).toBe("");
    expect(supportSection()).toBe(null);
    const hrefs = [...document.querySelectorAll("a")].map((link) => link.getAttribute("href") || "");
    expect(hrefs.filter((href) => /^https?:/.test(href))).toEqual([]);
    expect(document.querySelector("[data-donate]")).toBe(null);
    expect(document.body.textContent).not.toMatch(/donation|chip in|stripe/i);
    expect(spies.prices).not.toHaveBeenCalled();
    expect(spies.checkout).not.toHaveBeenCalled();
    expect(spies.portal).not.toHaveBeenCalled();
  });

  it("shows restore and manage in the Settings plan section", async () => {
    const { provider } = await boot();
    const { billingSection } = await import("../src/views/billingSection.js");
    const section = billingSection();
    expect(section.querySelector("a[href='/pricing']").textContent).toBe("See Pro");
    const restore = [...section.querySelectorAll("button")].find((button) => button.textContent === "Restore purchases");
    restore.click();
    await flush();
    expect(provider.restore).toHaveBeenCalled();
  });
});

describe("a store subscription seen on the website", () => {
  async function onWeb(plan) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
    const billing = await import("../src/lib/billing.js");
    const summary = await import("../src/lib/planSummary.js");
    return { billing, summary, plan };
  }

  it("says where to manage it and offers no portal button", async () => {
    const plan = { ...FREE_PLAN, ...PRO_PLAN, billing: { checkout: true, portal: false, intervals: [] } };
    const { billing, summary } = await onWeb(plan);
    expect(billing.billingMode()).toBe("stripe");
    expect(billing.canManageBilling(plan)).toBe(false);
    expect(summary.describePlan(plan).lines).toContain("Bought in the App Store or Google Play. Manage or cancel it there.");
  });

  it("still opens the portal for a website subscriber", async () => {
    const plan = { ...FREE_PLAN, ...PRO_PLAN, subscription: { ...PRO_PLAN.subscription, provider: "stripe" }, billing: { checkout: true, portal: true, intervals: [] } };
    const { billing, summary } = await onWeb(plan);
    expect(billing.canManageBilling(plan)).toBe(true);
    expect(summary.describePlan(plan).lines.join(" ")).not.toContain("App Store");
  });
});

describe("the account deletion warning", () => {
  async function warningFor(plan) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    const client = await import("../src/api/client.js");
    vi.spyOn(client.api, "billingPlan").mockResolvedValue(plan);
    vi.spyOn(client.api, "me").mockResolvedValue({ id: "u1", email: "a@b.c" });
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
    vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
    client.tokenStore.set("token");
    const { store } = await import("../src/lib/store.js");
    await store.hydrate();
    const { storeSubscriptionWarning } = await import("../src/views/settings.js");
    return storeSubscriptionWarning();
  }

  it("warns someone whose Pro was bought in a store that deleting does not cancel it", async () => {
    const warning = await warningFor({ ...FREE_PLAN, ...PRO_PLAN });
    expect(warning.textContent).toContain("deleting your account doesn't cancel it");
  });

  it("stays quiet for Free and for Pro bought on the website", async () => {
    expect(await warningFor(FREE_PLAN)).toBe(null);
    const website = { ...FREE_PLAN, ...PRO_PLAN, subscription: { ...PRO_PLAN.subscription, provider: "stripe" } };
    expect(await warningFor(website)).toBe(null);
  });
});
