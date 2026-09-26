import { el } from "./dom.js";

const DAY_MS = 24 * 60 * 60 * 1000;

export const STATUS_ORDER = ["learning", "polishing", "performance_ready", "wishlist", "retired"];

export const STATUS_LABEL = {
  learning: "Learning",
  polishing: "Polishing",
  performance_ready: "Performance ready",
  wishlist: "Wishlist",
  retired: "Retired",
};

export function daysSince(value) {
  if (!value) return null;
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((Date.now() - then) / DAY_MS));
}

export function lastPractisedLabel(value) {
  const days = daysSince(value);
  if (days === null) return "Not practised yet";
  if (days === 0) return "Practised today";
  if (days === 1) return "Practised yesterday";
  return `Last practised ${days} days ago`;
}

export function tempoShare(entry) {
  if (!entry.current_tempo_bpm || !entry.target_tempo_bpm) return null;
  return Math.min(100, Math.round((entry.current_tempo_bpm / entry.target_tempo_bpm) * 100));
}

export function tempoBar(entry) {
  const share = tempoShare(entry);
  if (share === null) return null;
  return el(
    "div",
    { class: "tempo-progress", title: `${entry.current_tempo_bpm} of ${entry.target_tempo_bpm} bpm` },
    el("div", { class: "bar" }, el("span", { style: `width:${share}%` })),
    el("span", { class: "faint mono" }, `${share}% of tempo`)
  );
}
