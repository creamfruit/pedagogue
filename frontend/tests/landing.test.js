import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import mainSource from "../src/main.js?raw";
import viteConfig from "../vite.config.js?raw";

describe("where signed-out visitors land", () => {
  async function target(options) {
    const { landingTarget } = await import("../src/lib/landing.js");
    return landingTarget(options);
  }

  it("sends a signed-out visitor to the website's landing page from the front door", async () => {
    expect(await target({ pathname: "/", authenticated: false, native: false })).toBe("/welcome");
  });

  it("leaves signed-in people on their Today page", async () => {
    expect(await target({ pathname: "/", authenticated: true, native: false })).toBe(null);
  });

  it("leaves every other address alone", async () => {
    for (const pathname of ["/login", "/register", "/pricing", "/privacy", "/repertoire", "/settings"]) {
      expect(await target({ pathname, authenticated: false, native: false })).toBe(null);
    }
  });

  it("never sends the apps to a website page", async () => {
    expect(await target({ pathname: "/", authenticated: false, native: true })).toBe(null);
  });

  it("is checked at start-up, before the app draws anything, and not when the server is down", () => {
    expect(mainSource).toMatch(/store\.serverDown \? null : landingTarget\(/);
    expect(mainSource).toMatch(/window\.location\.replace\(landing\)/);
    expect(mainSource.indexOf("landingTarget(")).toBeLessThan(mainSource.indexOf("app.hidden = false"));
  });
});

describe("the public pages are the server's, not the app's", () => {
  it("keeps the offline service worker from answering for them", () => {
    expect(viteConfig).toContain("welcome|music|composers");
    expect(viteConfig).toContain("sitemap");
    expect(viteConfig).toContain("robots");
    const denylist = viteConfig.match(/navigateFallbackDenylist: \[(.*)\]/)[1];
    expect(denylist).toContain("/api");
    const pattern = new RegExp(denylist.match(/\/\^\\\/\(welcome\|music\|composers\)\(\\\/\|\$\)\//)[0].slice(1, -1));
    for (const path of ["/welcome", "/music", "/music/12-chopin-nocturne", "/composers/3-bach"]) expect(pattern.test(path)).toBe(true);
    for (const path of ["/", "/repertoire", "/musical", "/login"]) expect(pattern.test(path)).toBe(false);
  });

  it("forwards them to the API while developing", () => {
    expect(viteConfig).toContain("rewrite: (path) => `/public${path}`");
  });
});

describe("the sign-in page", () => {
  let outlet;

  beforeEach(() => {
    document.body.innerHTML = '<div id="toasts"></div>';
    outlet = document.createElement("main");
    document.body.append(outlet);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function render(native) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
    const { loginView } = await import("../src/views/auth.js");
    loginView(outlet);
  }

  it("links to the landing page on the website with a full page load", async () => {
    await render(false);
    const about = [...outlet.querySelectorAll("a")].find((link) => link.textContent === "About Pedagogue");
    expect(about.getAttribute("href")).toBe("/welcome");
    expect(about.hasAttribute("data-link")).toBe(false);
  });

  it("does not link to it inside the apps", async () => {
    await render(true);
    expect([...outlet.querySelectorAll("a")].map((link) => link.textContent)).not.toContain("About Pedagogue");
    expect(outlet.textContent).toContain("Privacy policy");
  });
});
