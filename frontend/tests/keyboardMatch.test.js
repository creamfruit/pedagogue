import { describe, expect, it } from "vitest";
import { barStatus, countNotes, createBarTally, createLiveMatcher, createWaitMatcher, groupReference, localSummary } from "../src/lib/keyboardMatch.js";

const SCALE = [60, 62, 64, 65, 67, 69, 71, 72];
const scale = () => SCALE.map((midi, index) => [index, midi, 1 + Math.floor(index / 4)]);

describe("grouping the reference", () => {
  it("joins notes struck together into one chord and keeps the bar", () => {
    const events = groupReference([
      [1, 62, 1],
      [0, 64, 1],
      [0, 60, 1],
      [0.01, 67, 1],
    ]);
    expect(events.map((event) => [...event.pitches].sort())).toEqual([[60, 64, 67], [62]]);
    expect(countNotes(events)).toBe(4);
  });
});

describe("wait for me", () => {
  it("only moves on when the right note is played", () => {
    const matcher = createWaitMatcher(groupReference(scale()));
    expect(matcher.expected).toEqual([60]);
    expect(matcher.press(61)).toMatchObject({ result: "wrong", advanced: false });
    expect(matcher.expected).toEqual([60]);
    expect(matcher.press(60)).toMatchObject({ result: "correct", advanced: true });
    expect(matcher.expected).toEqual([62]);
    expect(matcher.totals).toEqual({ correct: 1, wrong: 1 });
  });

  it("waits for every note of a chord, in any order", () => {
    const matcher = createWaitMatcher(groupReference([[0, 60, 1], [0, 64, 1], [0, 67, 1], [1, 62, 1]]));
    expect(matcher.press(67).advanced).toBe(false);
    expect(matcher.expected).toEqual([60, 64]);
    expect(matcher.press(60).advanced).toBe(false);
    expect(matcher.press(64).advanced).toBe(true);
    expect(matcher.expected).toEqual([62]);
  });

  it("reports the bar it is waiting in and when the passage is finished", () => {
    const matcher = createWaitMatcher(groupReference(scale()));
    SCALE.slice(0, 4).forEach((midi) => matcher.press(midi));
    expect(matcher.bar).toBe(2);
    let last;
    SCALE.slice(4).forEach((midi) => {
      last = matcher.press(midi);
    });
    expect(last.done).toBe(true);
    expect(matcher.done).toBe(true);
    expect(matcher.press(60).result).toBe("done");
  });

  it("tallies wrong presses against the bar being waited in", () => {
    const matcher = createWaitMatcher(groupReference(scale()));
    SCALE.slice(0, 4).forEach((midi) => matcher.press(midi));
    matcher.press(99);
    const bars = Object.fromEntries(matcher.bars().map((item) => [item.bar, item]));
    expect(bars[1]).toMatchObject({ correct: 4, wrong: 0 });
    expect(bars[2]).toMatchObject({ correct: 0, wrong: 1 });
  });
});

describe("live matching against a tempo", () => {
  it("marks notes on time as correct with their timing error", () => {
    const matcher = createLiveMatcher(groupReference(scale()), 120);
    expect(matcher.play(60, 10)).toMatchObject({ result: "correct", bar: 1, errorMs: 10 });
    expect(matcher.play(62, 560)).toMatchObject({ result: "correct", errorMs: 60 });
  });

  it("marks a note that is not in the music as wrong in the nearest bar", () => {
    const matcher = createLiveMatcher(groupReference(scale()), 120);
    expect(matcher.play(61, 2100)).toEqual({ result: "wrong", bar: 2 });
    expect(matcher.totals).toEqual({ correct: 0, wrong: 1 });
  });

  it("does not let one expected note be matched twice", () => {
    const matcher = createLiveMatcher(groupReference([[0, 60, 1], [1, 62, 1]]), 120);
    expect(matcher.play(60, 0).result).toBe("correct");
    expect(matcher.play(60, 20).result).toBe("wrong");
  });

  it("matches repeated notes to the nearest one that is still free", () => {
    const matcher = createLiveMatcher(groupReference([0, 1, 2, 3].map((index) => [index, 60, 1])), 120);
    matcher.play(60, 0);
    matcher.play(60, 1000);
    expect(matcher.play(60, 1480).errorMs).toBe(-20);
    expect(matcher.totals).toEqual({ correct: 3, wrong: 0 });
  });
});

describe("local summary", () => {
  it("counts what is missing and gives each bar an accuracy", () => {
    const tally = createBarTally(groupReference(scale()));
    tally.get(1).correct = 4;
    tally.get(2).correct = 2;
    tally.get(2).wrong = 1;
    const summary = localSummary(tally);
    expect(summary).toMatchObject({ expected: 8, correct: 6, wrong: 1, missing: 2 });
    expect(summary.accuracy).toBeCloseTo(6 / 9, 4);
    expect(summary.bars.map((item) => item.accuracy)).toEqual([1, 2 / 5]);
  });

  it("names how each bar is going", () => {
    expect(barStatus({ expected: 4, correct: 4, wrong: 0 })).toBe("right");
    expect(barStatus({ expected: 4, correct: 2, wrong: 0 })).toBe("pending");
    expect(barStatus({ expected: 4, correct: 4, wrong: 1 })).toBe("wrong");
    expect(barStatus(undefined)).toBe("idle");
  });
});
