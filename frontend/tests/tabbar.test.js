import { beforeEach, describe, expect, it, vi } from "vitest";
import indexHtml from "../index.html?raw";
import mainSource from "../src/main.js?raw";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function mount() {
  const doc = new DOMParser().parseFromString(indexHtml, "text/html");
  document.body.innerHTML = doc.body.innerHTML;
  return document.getElementById("tabbar");
}

describe("the phone tab bar", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("has four tabs named Today, Sky, Library and Me, in that order", () => {
    const bar = mount();
    const tabs = [...bar.querySelectorAll("a")];
    expect(tabs.map((tab) => tab.textContent.trim())).toEqual(["Today", "Sky", "Library", "Me"]);
    expect(tabs.map((tab) => tab.getAttribute("href"))).toEqual(["/", "/constellation", "/repertoire", "/me"]);
    expect(bar.getAttribute("aria-label")).toBe("Main tabs");
  });

  it("is hidden until someone is signed in", () => {
    expect(mount().hidden).toBe(true);
  });

  it("keeps the top navigation for wide screens", () => {
    mount();
    const labels = [...document.querySelectorAll("#nav a")].map((link) => link.textContent.trim());
    expect(labels).toEqual(["Today", "Repertoire", "Constellation", "Practice", "Progress", "Observatory"]);
  });

  it("lights the tab for the page you are on, including the pages under Me", async () => {
    mount();
    vi.resetModules();
    const router = await import("../src/router.js");
    const host = document.createElement("main");
    document.body.append(host);
    router.route("/me", () => {});
    router.route("/progress", () => {});
    router.route("/constellation", () => {});
    await router.startRouter(host);
    const activeLabel = () => [...document.querySelectorAll("#tabbar a.active")].map((tab) => tab.textContent.trim());
    for (const [path, label] of [["/me", "Me"], ["/progress", "Me"], ["/constellation", "Sky"]]) {
      window.history.pushState({}, "", path);
      await router.resolve();
      expect(activeLabel()).toEqual([label]);
    }
  });

  it("gives each tab a large target and respects the home-indicator area", () => {
    expect(styles).toMatch(/\.tabbar-item\s*{[^}]*min-height:\s*64px/);
    expect(styles).toMatch(/\.tabbar\s*{[^}]*padding:\s*0 var\(--safe-right\) var\(--safe-bottom\) var\(--safe-left\)/);
    expect(styles).toMatch(/@media \(max-width: 760px\)[\s\S]*\.tabbar \{[^}]*display: grid/);
  });

  it("registers the Me page and shows the bar only for signed-in people who are not setting up", () => {
    expect(mainSource).toContain('route("/me", meView)');
    expect(mainSource).toMatch(/const showTabs = authed && !settingUp/);
  });
});

describe("the Me page", () => {
  it("lists the places that used to live in the top navigation", async () => {
    vi.resetModules();
    const { meView } = await import("../src/views/me.js");
    const outlet = document.createElement("main");
    meView(outlet);
    const hrefs = [...outlet.querySelectorAll(".me-row")].map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining(["/progress", "/observatory", "/practice", "/roulette", "/settings", "/credits"]));
    for (const row of outlet.querySelectorAll(".me-row")) expect(row.hasAttribute("data-link")).toBe(true);
  });
});
