import { el } from "../lib/dom.js";

export const GOOD_ACCURACY = 0.95;
export const FAIR_ACCURACY = 0.75;

export function heatLevel(item) {
  if (!item) return "idle";
  if (item.accuracy === null || item.accuracy === undefined) {
    if (item.timing_score !== null && item.timing_score !== undefined) return item.timing_score >= 75 ? "good" : item.timing_score >= 50 ? "fair" : "bad";
    return item.pending ? "pending" : "idle";
  }
  if (item.pending) return "pending";
  if (item.accuracy >= GOOD_ACCURACY) return "good";
  if (item.accuracy >= FAIR_ACCURACY) return "fair";
  return "bad";
}

const MARKS = { good: "✓", fair: "◆", bad: "▲", pending: "·", idle: "" };

export function describeBar(item) {
  if (!item) return "";
  const parts = [`Bar ${item.bar}`];
  if (item.expected) parts.push(`${item.correct} of ${item.expected} notes right`);
  if (item.wrong) parts.push(`${item.wrong} wrong`);
  if (item.missing && !item.pending) parts.push(`${item.missing} missed`);
  if (item.late) parts.push(`${item.late} late`);
  if (item.early) parts.push(`${item.early} early`);
  if (item.tempo_bpm) parts.push(`about ♩ = ${Math.round(item.tempo_bpm)}`);
  if (item.timing_error_ms !== null && item.timing_error_ms !== undefined) parts.push(`${item.timing_error_ms > 0 ? "+" : ""}${Math.round(item.timing_error_ms)} ms from the beat`);
  return parts.join(" · ");
}

export function barsFromTally(tally) {
  return tally.map((item) => ({
    ...item,
    missing: Math.max(item.expected - item.correct, 0),
    accuracy: item.expected + item.wrong ? item.correct / (item.expected + item.wrong) : null,
    pending: item.wrong === 0 && item.correct < item.expected,
  }));
}

export function heatStrip({ label = "How each bar went" } = {}) {
  const list = el("ol", { class: "heat-strip", "aria-label": label });
  const node = el("div", { class: "heat" }, list);

  function update(bars) {
    list.replaceChildren(
      ...bars.map((item) => {
        const level = heatLevel(item);
        return el(
          "li",
          { class: `heat-cell heat-${level}`, title: describeBar(item), "aria-label": `${describeBar(item)}, ${level}` },
          el("span", { class: "heat-mark", "aria-hidden": "true" }, MARKS[level]),
          el("span", { class: "heat-bar mono" }, String(item.bar))
        );
      })
    );
    node.hidden = !bars.length;
  }

  node.hidden = true;
  return { node, update };
}
