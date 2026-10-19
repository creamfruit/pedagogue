import { describe, expect, it } from "vitest";
import { barsFromTally, describeBar, heatLevel, heatStrip } from "../src/components/heatStrip.js";

describe("heat levels", () => {
  it("colours scored bars by how many notes were right", () => {
    expect(heatLevel({ bar: 1, accuracy: 1 })).toBe("good");
    expect(heatLevel({ bar: 1, accuracy: 0.95 })).toBe("good");
    expect(heatLevel({ bar: 1, accuracy: 0.8 })).toBe("fair");
    expect(heatLevel({ bar: 1, accuracy: 0.4 })).toBe("bad");
    expect(heatLevel({ bar: 1, accuracy: 0 })).toBe("bad");
  });

  it("colours free-play bars by timing instead", () => {
    expect(heatLevel({ bar: 1, accuracy: null, timing_score: 96 })).toBe("good");
    expect(heatLevel({ bar: 1, accuracy: null, timing_score: 60 })).toBe("fair");
    expect(heatLevel({ bar: 1, accuracy: null, timing_score: 20 })).toBe("bad");
    expect(heatLevel({ bar: 1, accuracy: null })).toBe("idle");
  });

  it("shows bars still being played as pending and unknown bars as idle", () => {
    expect(heatLevel({ bar: 1, accuracy: 1, pending: true })).toBe("pending");
    expect(heatLevel(undefined)).toBe("idle");
  });

  it("builds live bars from a tally", () => {
    const [done, partial, wrong] = barsFromTally([
      { bar: 1, expected: 4, correct: 4, wrong: 0 },
      { bar: 2, expected: 4, correct: 2, wrong: 0 },
      { bar: 3, expected: 4, correct: 1, wrong: 2 },
    ]);
    expect([heatLevel(done), heatLevel(partial), heatLevel(wrong)]).toEqual(["good", "pending", "bad"]);
  });
});

describe("the strip", () => {
  it("has a cell per bar with a mark as well as a colour and a description", () => {
    const strip = heatStrip();
    expect(strip.node.hidden).toBe(true);
    strip.update([
      { bar: 9, expected: 4, correct: 4, wrong: 0, missing: 0, accuracy: 1 },
      { bar: 10, expected: 4, correct: 1, wrong: 2, missing: 3, accuracy: 1 / 6, late: 1, timing_error_ms: 140, tempo_bpm: 71.4 },
    ]);
    expect(strip.node.hidden).toBe(false);
    const cells = [...strip.node.querySelectorAll(".heat-cell")];
    expect(cells.map((cell) => cell.querySelector(".heat-mark").textContent)).toEqual(["✓", "▲"]);
    expect(cells.map((cell) => cell.querySelector(".heat-bar").textContent)).toEqual(["9", "10"]);
    expect(cells[1].title).toBe("Bar 10 · 1 of 4 notes right · 2 wrong · 3 missed · 1 late · about ♩ = 71 · +140 ms from the beat");
    strip.update([]);
    expect(strip.node.hidden).toBe(true);
  });

  it("describes a free-play bar without talking about notes", () => {
    expect(describeBar({ bar: 2, expected: 0, correct: 0, wrong: 0, missing: 0, accuracy: null, early: 2, timing_error_ms: -35 })).toBe("Bar 2 · 2 early · -35 ms from the beat");
  });
});
