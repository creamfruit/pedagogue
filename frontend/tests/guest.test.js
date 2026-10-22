import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const GUEST = { id: "g1", email: "guest-1@guest.pedagogue.app", display_name: null, is_guest: true };
const REAL = { id: "r1", email: "ana@example.com", display_name: "Ana", is_guest: false };

async function load({ native = false } = {}) {
  vi.resetModules();
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
  const client = await import("../src/api/client.js");
  const spies = {
    guest: vi.spyOn(client.api, "guest").mockResolvedValue({ access_token: "guest-token" }),
    me: vi.spyOn(client.api, "me").mockResolvedValue(GUEST),
    login: vi.spyOn(client.api, "login").mockResolvedValue({ access_token: "real-token" }),
    register: vi.spyOn(client.api, "register").mockResolvedValue({ access_token: "real-token" }),
    profile: vi.spyOn(client.api, "profileSummary").mockResolvedValue({}),
    status: vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({ complete: false }),
    plan: vi.spyOn(client.api, "billingPlan").mockResolvedValue(null),
    refresh: vi.spyOn(client.api, "refreshToken").mockResolvedValue(null),
    starters: vi.spyOn(client.api, "starterPieces").mockResolvedValue([
      { id: 1, title: "Minuet in G", composer: "Petzold", difficulty_score: "18.0" },
      { id: 2, title: "Fur Elise", composer: "Beethoven", difficulty_score: "35.0" },
    ]),
    quick: vi.spyOn(client.api, "quickStart").mockResolvedValue({ status: { complete: true }, entry_id: "e1", piece_title: "Minuet in G" }),
    search: vi.spyOn(client.api, "searchPieces").mockResolvedValue([{ id: 9, title: "Gymnopedie No. 1", composer: { name: "Satie" }, difficulty_score: "28.0" }]),
  };
  const { store } = await import("../src/lib/store.js");
  const nav = await import("../src/router.js");
  vi.spyOn(nav, "navigate").mockImplementation(() => {});
  return { client, spies, store, nav };
}

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '<div id="toasts"></div>';
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("a guest on first launch", () => {
  it("is created with a stored token and counts as signed in", async () => {
    const { client, store, spies } = await load({ native: true });
    const user = await store.startGuest();
    expect(spies.guest).toHaveBeenCalled();
    expect(client.tokenStore.get()).toBe("guest-token");
    expect(user.is_guest).toBe(true);
    expect(store.isAuthenticated).toBe(true);
    expect(store.isGuest).toBe(true);
  });

  it("survives a restart with the same token", async () => {
    const { client, store, spies } = await load({ native: true });
    client.tokenStore.set("guest-token");
    await store.hydrate();
    expect(spies.guest).not.toHaveBeenCalled();
    expect(store.isGuest).toBe(true);
  });

  it("starts the guest from /start on the web and remembers the launch", async () => {
    const { store, spies, nav } = await load();
    const { startView, firstLaunch } = await import("../src/views/start.js");
    expect(firstLaunch()).toBe(true);
    await startView(document.createElement("main"));
    expect(spies.guest).toHaveBeenCalled();
    expect(nav.navigate).toHaveBeenCalledWith("/onboarding", { replace: true });
    expect(store.isGuest).toBe(true);
    expect(firstLaunch()).toBe(false);
  });

  it("says so, and offers another go, when it cannot start", async () => {
    const { spies } = await load();
    spies.guest.mockRejectedValue(Object.assign(new Error("offline"), { detail: "you appear to be offline" }));
    const { startView } = await import("../src/views/start.js");
    const outlet = document.createElement("main");
    await startView(outlet);
    expect(outlet.textContent).toContain("Couldn't get started");
    expect(outlet.textContent).toContain("you appear to be offline");
    expect(outlet.textContent).toContain("Try again");
  });

  it("is only created on the very first native launch", async () => {
    const source = (await import("../src/main.js?raw")).default;
    expect(source).toMatch(/isNative && !store\.isAuthenticated && !store\.serverDown && firstLaunch\(\)/);
    expect(source).toMatch(/route\("\/start", startView, \{ open: true \}\)/);
    expect(source).toMatch(/isPublic && !store\.isGuest\) return "\/"/);
  });

  it("is never linked to RevenueCat as a customer", async () => {
    const source = (await import("../src/main.js?raw")).default;
    expect(source).toContain("store.user && !store.user.is_guest ? store.user.id : null");
  });
});

describe("the sixty-second onboarding", () => {
  async function open() {
    const loaded = await load();
    const { onboardingView } = await import("../src/views/onboarding.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await onboardingView(outlet);
    return { ...loaded, outlet };
  }

  it("asks for a level first, with four large choices", async () => {
    const { outlet } = await open();
    expect(outlet.querySelector(".quick-title").textContent).toContain("How would you describe your playing?");
    expect([...outlet.querySelectorAll(".quick-level")].map((button) => button.dataset.level)).toEqual(["beginner", "intermediate", "advanced", "professional"]);
    expect(outlet.querySelectorAll("input, select")).toHaveLength(0);
  });

  it("then offers a handful of pieces for that level and a search", async () => {
    const { outlet, spies } = await open();
    outlet.querySelector('[data-level="beginner"]').click();
    await flush();
    expect(spies.starters).toHaveBeenCalledWith("beginner");
    expect(outlet.querySelector(".quick-title").textContent).toContain("Pick one piece");
    expect([...outlet.querySelectorAll(".quick-piece")].map((button) => button.textContent)).toEqual(["Minuet in GPetzold · gentle", "Fur EliseBeethoven · moderate"]);
    expect(outlet.querySelector(".quick-search")).not.toBe(null);
  });

  it("goes straight into the first mission once a piece is picked", async () => {
    const { outlet, spies, nav } = await open();
    outlet.querySelector('[data-level="intermediate"]').click();
    await flush();
    outlet.querySelector('[data-piece="2"]').click();
    await flush();
    await flush();
    expect(spies.quick).toHaveBeenCalledWith({ self_level: "intermediate", piece_id: 2 });
    expect(nav.navigate).toHaveBeenCalledWith("/mission?first=1", { replace: true });
  });

  it("finds other pieces by search", async () => {
    vi.useFakeTimers();
    const { outlet, spies } = await open();
    outlet.querySelector('[data-level="advanced"]').click();
    await vi.advanceTimersByTimeAsync(0);
    const input = outlet.querySelector(".quick-search");
    input.value = "gymno";
    input.dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(400);
    expect(spies.search).toHaveBeenCalledWith("gymno", 8);
    expect(outlet.textContent).toContain("Gymnopedie No. 1");
    expect(outlet.textContent).toContain("Satie");
    vi.useRealTimers();
  });

  it("stays on the page and says so when the piece cannot be started", async () => {
    const { outlet, spies, nav } = await open();
    spies.quick.mockRejectedValue(Object.assign(new Error("no"), { detail: "that piece isn't in the catalogue" }));
    outlet.querySelector('[data-level="beginner"]').click();
    await flush();
    outlet.querySelector('[data-piece="1"]').click();
    await flush();
    await flush();
    expect(document.querySelector(".toast-error").textContent).toContain("isn't in the catalogue");
    expect(nav.navigate).not.toHaveBeenCalled();
    expect(outlet.querySelector(".quick").classList.contains("is-busy")).toBe(false);
  });

  it("lets you go back to change the level", async () => {
    const { outlet } = await open();
    outlet.querySelector('[data-level="beginner"]').click();
    await flush();
    outlet.querySelector(".back-btn").click();
    expect(outlet.querySelector(".quick-title").textContent).toContain("How would you describe");
  });

  it("falls back to search when there are no suggestions", async () => {
    const { outlet, spies } = await open();
    spies.starters.mockRejectedValue(Object.assign(new Error("x"), { detail: "boom" }));
    outlet.querySelector('[data-level="beginner"]').click();
    await flush();
    await flush();
    expect(outlet.textContent).toContain("boom");
    expect(outlet.querySelector(".quick-search")).not.toBe(null);
  });
});

describe("signing up or in as a guest", () => {
  async function asGuest() {
    const loaded = await load();
    loaded.client.tokenStore.set("guest-token");
    await loaded.store.hydrate();
    expect(loaded.store.isGuest).toBe(true);
    return loaded;
  }

  it("sends the guest token with the sign-up so the backend can merge it", async () => {
    const { store, spies, client } = await asGuest();
    spies.me.mockResolvedValue(REAL);
    await store.signUp({ email: "ana@example.com", password: "sturdy-pass-123" });
    expect(spies.register).toHaveBeenCalledWith({ email: "ana@example.com", password: "sturdy-pass-123" }, { guestToken: "guest-token" });
    expect(client.tokenStore.get()).toBe("real-token");
    expect(store.isGuest).toBe(false);
  });

  it("sends it with a sign-in too", async () => {
    const { store, spies } = await asGuest();
    spies.me.mockResolvedValue(REAL);
    await store.signIn("ana@example.com", "sturdy-pass-123");
    expect(spies.login).toHaveBeenCalledWith("ana@example.com", "sturdy-pass-123", { guestToken: "guest-token" });
  });

  it("sends no guest token when a real person signs in", async () => {
    const loaded = await load();
    loaded.spies.me.mockResolvedValue(REAL);
    await loaded.store.signIn("ana@example.com", "sturdy-pass-123");
    expect(loaded.spies.login).toHaveBeenCalledWith("ana@example.com", "sturdy-pass-123", { guestToken: null });
  });

  it("puts the guest token in an X-Guest-Token header", async () => {
    vi.resetModules();
    const client = await import("../src/api/client.js");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({ access_token: "t" }), { status: 200, headers: { "content-type": "application/json" } }));
    await client.api.login("a@b.c", "pw", { guestToken: "guest-token" });
    expect(fetchSpy.mock.calls[0][1].headers["X-Guest-Token"]).toBe("guest-token");
    await client.api.register({ email: "a@b.c" }, { guestToken: "guest-token" });
    expect(fetchSpy.mock.calls[1][1].headers["X-Guest-Token"]).toBe("guest-token");
    await client.api.login("a@b.c", "pw");
    expect(fetchSpy.mock.calls[2][1].headers["X-Guest-Token"]).toBeUndefined();
  });

  it("tells a guest on the sign-up page that their progress comes with them", async () => {
    const { store } = await asGuest();
    expect(store.isGuest).toBe(true);
    const { registerView, loginView } = await import("../src/views/auth.js");
    const outlet = document.createElement("main");
    registerView(outlet);
    expect(outlet.textContent).toContain("Your progress so far comes with you.");
    const login = document.createElement("main");
    loginView(login, {});
    expect(login.textContent).toContain("what you've done as a guest joins your account");
    expect(login.textContent).not.toContain("without an account");
  });

  it("offers a way in without an account to people who are not signed in", async () => {
    await load();
    const { loginView } = await import("../src/views/auth.js");
    const outlet = document.createElement("main");
    loginView(outlet, {});
    expect(outlet.querySelector('a[href="/start"]').textContent).toBe("Try it without an account");
  });
});

describe("the gentle prompt to keep progress", () => {
  it("is shown once, after a first completed mission, and can be dismissed", async () => {
    const { shouldPromptGuest, markGuestPrompted } = await import("../src/lib/guestPrompt.js");
    expect(shouldPromptGuest(GUEST)).toBe(true);
    expect(shouldPromptGuest(REAL)).toBe(false);
    expect(shouldPromptGuest(null)).toBe(false);
    markGuestPrompted();
    expect(shouldPromptGuest(GUEST)).toBe(false);
  });

  it("appears on the mission-complete screen for a guest who did something", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"] });
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
    vi.doMock("../src/lib/wakeLock.js", () => ({ keepAwake: vi.fn(async () => () => {}) }));
    const client = await import("../src/api/client.js");
    const step = { index: 0, kind: "warmup", title: "Warm up", minutes: 1, why: "A slow, even pattern to wake your hands up before the real work.", tempo_bpm: 72, star_entry_id: "e1", piece_title: "Minuet" };
    const mission = { id: "m1", day: new Date().toLocaleDateString("en-CA"), kind: "first", total_minutes: 1, steps: [step], progress: [], completed_at: null, next_index: 0 };
    vi.spyOn(client.api, "missionToday").mockResolvedValue(mission);
    vi.spyOn(client.api, "missionStep").mockResolvedValue({
      mission: { ...mission, progress: [{ index: 0, status: "done", seconds: 60, minutes: 1 }], next_index: null, completed_at: "2026-10-22T10:00:00Z" },
      lit: { entry_id: "e1", piece_title: "Minuet" },
      finished: true,
      xp: 12,
      gold: 1,
      streak: { current: 1, longest: 1, today_done: true, min_minutes: 5, minutes_today: 5, state: "lit", freezes: 1, freeze_cap: 2, frozen_days: [], next_freeze_in: 6 },
    });
    vi.spyOn(client.api, "me").mockResolvedValue(GUEST);
    vi.spyOn(client.api, "profileSummary").mockResolvedValue({});
    vi.spyOn(client.api, "onboardingStatus").mockResolvedValue({});
    vi.spyOn(client.api, "billingPlan").mockResolvedValue(null);
    vi.spyOn(client.api, "refreshToken").mockResolvedValue(null);
    client.tokenStore.set("guest-token");
    const { store } = await import("../src/lib/store.js");
    await store.hydrate();
    const nav = await import("../src/router.js");
    vi.spyOn(nav, "navigate").mockImplementation(() => {});
    const { missionView } = await import("../src/views/mission.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await missionView(outlet, { query: { first: "1" } });
    const root = outlet.querySelector(".mission-screen");
    root.click();
    await vi.advanceTimersByTimeAsync(30_000);
    root.click();
    await vi.advanceTimersByTimeAsync(0);
    expect(root.textContent).toContain("Mission complete");
    expect(root.textContent).toContain("Keep your progress");
    root.querySelector('[data-control="guest-create"]').click();
    expect(nav.navigate).toHaveBeenCalledWith("/register");
    root.querySelector('[data-control="guest-later"]').click();
    expect(root.querySelector(".guest-card")).toBe(null);
    expect(localStorage.getItem("pp.guestPrompt")).toBe("1");
    vi.useRealTimers();
  });
});

describe("what a guest sees elsewhere", () => {
  it("is offered an account instead of delete in Settings", async () => {
    const { store, client } = await load();
    client.tokenStore.set("guest-token");
    await store.hydrate();
    const { settingsView } = await import("../src/views/settings.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await settingsView(outlet);
    expect(outlet.textContent).toContain("You're practising as a guest.");
    expect(outlet.textContent).not.toContain("Delete my account");
  });

  it("has a create-account card on Me", async () => {
    const { store, client } = await load();
    client.tokenStore.set("guest-token");
    await store.hydrate();
    const { meView } = await import("../src/views/me.js");
    const outlet = document.createElement("main");
    meView(outlet);
    expect(outlet.textContent).toContain("Keep your progress");
    expect(outlet.textContent).toContain("Guest pianist");
  });

  it("asks a guest to create an account before upgrading", async () => {
    const { store, client, spies } = await load();
    client.tokenStore.set("guest-token");
    await store.hydrate();
    vi.spyOn(client.api, "billingPrices").mockResolvedValue({ available: true, trial_days: 7, prices: [{ interval: "month", amount: 900, currency: "usd" }] });
    const { pricingView } = await import("../src/views/pricing.js");
    const outlet = document.createElement("main");
    document.body.append(outlet);
    await pricingView(outlet);
    expect(outlet.textContent).toContain("Create a free account");
    expect([...outlet.querySelectorAll("button")].filter((button) => /trial|Subscribe/.test(button.textContent))).toHaveLength(0);
    expect(spies.me).toHaveBeenCalled();
  });

  it("will not let a guest sign out and lose their progress", async () => {
    const source = (await import("../src/main.js?raw")).default;
    expect(source).toMatch(/if \(store\.isGuest\) \{[\s\S]*?navigate\("\/register"\);[\s\S]*?return;/);
  });
});
