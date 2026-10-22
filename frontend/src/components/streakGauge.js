import { el } from "../lib/dom.js";

const SVG = "http://www.w3.org/2000/svg";
const CYCLE = 7;

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

export function streakMessage(streak) {
  const left = Math.max((streak.min_minutes || 5) - (streak.minutes_today || 0), 1);
  const minutes = `${left} more minute${left === 1 ? "" : "s"}`;
  switch (streak.state) {
    case "lit":
      return streak.current <= 1 ? "Day 1 is lit. Come back tomorrow and it grows." : `Today is lit. ${streak.current} days in a row.`;
    case "covered":
      return `You rested yesterday, and a streak freeze covered it. Your ${streak.current}-day streak is safe.`;
    case "waiting":
      return `Practise ${minutes} today to keep your ${streak.current}-day streak glowing.`;
    case "fresh":
      return `A fresh start. Your best was ${streak.longest} days, and that stays on your record.`;
    default:
      return `Practise ${streak.min_minutes || 5} minutes today to light your first day.`;
  }
}

export function freezeLine(streak) {
  const count = streak.freezes ?? 0;
  if (!count) return `No freezes ready. You earn one after ${streak.next_freeze_in ?? 7} more days in a row.`;
  return `${count} streak freeze${count === 1 ? "" : "s"} ready. A missed day uses one, so nothing is lost.`;
}

function ring(streak, size) {
  const lit = streak.current > 0 ? ((streak.current - 1) % CYCLE) + 1 : 0;
  const node = svg("svg", { class: "streak-ring", viewBox: "0 0 72 72", width: size, height: size, "aria-hidden": "true" });
  const radius = 30;
  const gap = 0.22;
  const span = (Math.PI * 2) / CYCLE;
  for (let index = 0; index < CYCLE; index += 1) {
    const start = index * span + gap / 2 - Math.PI / 2;
    const end = (index + 1) * span - gap / 2 - Math.PI / 2;
    const point = (angle) => `${(36 + radius * Math.cos(angle)).toFixed(2)} ${(36 + radius * Math.sin(angle)).toFixed(2)}`;
    node.append(svg("path", { d: `M${point(start)} A${radius} ${radius} 0 0 1 ${point(end)}`, class: `streak-ring-seg${index < lit ? " is-lit" : ""}`, fill: "none" }));
  }
  return node;
}

export function streakGauge(streak, { compact = false } = {}) {
  if (!streak) return null;
  const size = compact ? 64 : 84;
  const freezes = Array.from({ length: streak.freeze_cap ?? 2 }, (_, index) =>
    el("span", { class: `streak-freeze${index < (streak.freezes ?? 0) ? " is-ready" : ""}`, title: index < (streak.freezes ?? 0) ? "Streak freeze ready" : "Empty slot" }, "❄︎")
  );
  return el(
    "div",
    { class: `streak-gauge${compact ? " streak-gauge-compact" : ""}`, "data-state": streak.state || "new" },
    el("div", { class: "streak-dial" }, ring(streak, size), el("span", { class: "streak-dial-count mono" }, String(streak.current))),
    el(
      "div",
      { class: "streak-gauge-text" },
      el("div", { class: "streak-title" }, streak.current === 1 ? "day in a row" : "days in a row"),
      el("p", { class: "streak-gauge-message", role: "status" }, streakMessage(streak)),
      el("div", { class: "streak-freezes", title: freezeLine(streak) }, ...freezes, el("span", { class: "faint streak-freeze-note" }, freezeLine(streak)))
    )
  );
}
