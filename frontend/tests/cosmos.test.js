import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const calls = { arc: 0, clearRect: 0 };

function stubContext() {
  const gradient = { addColorStop: () => {} };
  const target = {};
  return new Proxy(target, {
    get(_, key) {
      if (key === "arc") return () => (calls.arc += 1);
      if (key === "clearRect") return () => (calls.clearRect += 1);
      if (key === "createRadialGradient" || key === "createLinearGradient") return () => gradient;
      if (key in target) return target[key];
      return () => {};
    },
    set(_, key, value) {
      target[key] = value;
      return true;
    },
  });
}

function setWidth(width, height = 844) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
}

function setHidden(value) {
  Object.defineProperty(document, "hidden", { configurable: true, value });
  document.dispatchEvent(new Event("visibilitychange"));
}

let raf;
let cancel;
let running = [];

async function start({ width = 1280, native = false } = {}) {
  vi.resetModules();
  setWidth(width);
  vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: false, isAndroid: false, platformName: "web" }));
  const cosmos = await import("../src/lib/cosmos.js");
  const stop = cosmos.startCosmos();
  running.push(stop);
  return { cosmos, stop };
}

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = "";
  document.body.className = "";
  document.documentElement.className = "";
  calls.arc = 0;
  calls.clearRect = 0;
  raf = vi.fn(() => 7);
  cancel = vi.fn();
  vi.stubGlobal("requestAnimationFrame", raf);
  vi.stubGlobal("cancelAnimationFrame", cancel);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => stubContext());
  window.matchMedia = vi.fn(() => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }));
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

afterEach(() => {
  running.forEach((stop) => stop());
  running = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.matchMedia;
});

describe("the starfield on a phone", () => {
  it("draws far fewer stars than on a desktop", async () => {
    const desktop = await start({ width: 1280 });
    const desktopStars = calls.arc;
    desktop.stop();
    calls.arc = 0;
    const phone = await start({ width: 390 });
    expect(calls.arc).toBeGreaterThan(0);
    expect(calls.arc / desktopStars).toBeLessThan(0.2);
    phone.stop();
  });

  it("scales the star count by a fixed phone share of the density", async () => {
    const { cosmos } = await start({ width: 390 });
    const layer = { density: 0.0002 };
    expect(cosmos.starCount(390, 844, layer)).toBe(Math.round(390 * 844 * 0.0002 * cosmos.PHONE_STAR_SHARE));
    expect(cosmos.starCount(1280, 800, layer)).toBe(Math.round(1280 * 800 * 0.0002));
    expect(cosmos.PHONE_STAR_SHARE).toBeLessThan(0.5);
  });

  it("counts a screen as a phone up to 760px wide", async () => {
    const { cosmos } = await start({ width: 390 });
    expect(cosmos.isPhoneScreen(412)).toBe(true);
    expect(cosmos.isPhoneScreen(760)).toBe(true);
    expect(cosmos.isPhoneScreen(761)).toBe(false);
  });
});

describe("pausing to save the battery", () => {
  it("animates while the app is showing", async () => {
    await start({ width: 390 });
    expect(raf).toHaveBeenCalled();
  });

  it("stops when the app goes to the background and starts again when it returns", async () => {
    await start({ width: 390 });
    raf.mockClear();
    setHidden(true);
    expect(cancel).toHaveBeenCalled();
    expect(raf).not.toHaveBeenCalled();
    setHidden(false);
    expect(raf).toHaveBeenCalled();
  });

  it("does not start at all when the screen is not visible", async () => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    await start({ width: 390 });
    expect(raf).not.toHaveBeenCalled();
  });

  it("stops on page hide", async () => {
    await start({ width: 390 });
    window.dispatchEvent(new Event("pagehide"));
    expect(cancel).toHaveBeenCalled();
  });

  it("rests behind the full-screen mission and wakes afterwards", async () => {
    await start({ width: 390 });
    raf.mockClear();
    cancel.mockClear();
    document.body.classList.add("immersive");
    await Promise.resolve();
    expect(cancel).toHaveBeenCalled();
    document.body.classList.remove("immersive");
    await Promise.resolve();
    expect(raf).toHaveBeenCalled();
  });

  it("listens to the native app state when it runs in an app", async () => {
    const listeners = [];
    vi.doMock("@capacitor/app", () => ({ App: { addListener: vi.fn(async (name, handler) => (listeners.push([name, handler]), { remove: vi.fn() })) } }));
    await start({ width: 390, native: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listeners.map(([name]) => name)).toEqual(["appStateChange"]);
    raf.mockClear();
    listeners[0][1]({ isActive: false });
    expect(cancel).toHaveBeenCalled();
    listeners[0][1]({ isActive: true });
    expect(raf).toHaveBeenCalled();
  });

  it("stops listening when it is taken down", async () => {
    const { stop } = await start({ width: 390 });
    stop();
    raf.mockClear();
    setHidden(false);
    expect(document.querySelector(".cosmos")).toBe(null);
  });
});

describe("the starfield with reduced motion", () => {
  it("draws one still frame and never animates when the setting is on", async () => {
    localStorage.setItem("pp.motion", "reduce");
    await start({ width: 390 });
    expect(raf).not.toHaveBeenCalled();
    expect(calls.clearRect).toBeGreaterThan(0);
  });

  it("never animates when the device asks for less motion", async () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    await start({ width: 1280 });
    expect(raf).not.toHaveBeenCalled();
  });

  it("stops at once when the setting is switched on, and resumes when it goes off", async () => {
    await start({ width: 390 });
    const motion = await import("../src/lib/motion.js");
    cancel.mockClear();
    motion.setMotionSetting("reduce");
    expect(cancel).toHaveBeenCalled();
    raf.mockClear();
    motion.setMotionSetting("system");
    expect(raf).toHaveBeenCalled();
  });
});
