import { afterEach, describe, expect, it, vi } from "vitest";
import index from "../public/excerpts/index.json";

describe("technique excerpt library", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("ships only sources that allow commercial use", () => {
    const licences = Object.values(index.sources).map((source) => source.license);
    expect(licences.length).toBeGreaterThan(0);
    for (const licence of licences) expect(licence).not.toMatch(/NC/);
    expect(Object.keys(index.sources)).not.toContain("asap");
  });

  it("names a known source for every excerpt", () => {
    for (const excerpt of Object.values(index.excerpts)) {
      expect(index.sources[excerpt.source.kind], excerpt.id).toBeTruthy();
    }
  });

  it("attaches the licence to each excerpt it hands out", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => index })));
    const { excerptsFor } = await import("../src/lib/excerpts.js");
    const found = await excerptsFor("Repeated notes");
    expect(found.length).toBeGreaterThan(0);
    for (const excerpt of found) expect(excerpt.sourceInfo.license).toBeTruthy();
  });
});
