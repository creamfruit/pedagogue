import { el } from "./dom.js";

const FALLBACK = {
  tide: "#6fb7b3",
  accent: "#cee9e2",
  mauve: "#b5a1af",
  starlight: "#eef5f3",
  bgSunk: "#060b15",
  text: "#e4eeee",
  textDim: "#9fb3b8",
  textFaint: "#62757f",
  lineStrong: "#21304f",
};

const TOKENS = {
  tide: "--tide",
  accent: "--accent",
  mauve: "--mauve",
  starlight: "--starlight",
  bgSunk: "--bg-sunk",
  text: "--text",
  textDim: "--text-dim",
  textFaint: "--text-faint",
  lineStrong: "--line-strong",
};

let cached = null;

export function palette() {
  if (cached) return cached;
  const style = getComputedStyle(document.documentElement);
  cached = Object.fromEntries(
    Object.entries(TOKENS).map(([key, token]) => [key, style.getPropertyValue(token).trim() || FALLBACK[key]])
  );
  return cached;
}

export const ERA_STYLE = {
  Baroque: { tone: "tide", spiked: false },
  Classical: { tone: "tide", spiked: true },
  Romantic: { tone: "accent", spiked: false },
  Impressionist: { tone: "accent", spiked: true },
  Modern: { tone: "mauve", spiked: false },
  Contemporary: { tone: "mauve", spiked: true },
};

export function eraGlyph(era) {
  const style = ERA_STYLE[era];
  if (!style) return el("span", { class: "era-glyph", style: "color:var(--text)" });
  return el("span", {
    class: `era-glyph${style.spiked ? " era-glyph-spiked" : ""}`,
    style: `color:var(--${style.tone})`,
    "aria-hidden": "true",
  });
}

export function difficultyTone(difficulty) {
  if (difficulty >= 90) return "starlight";
  if (difficulty >= 78) return "tide";
  if (difficulty >= 60) return "accent";
  return "mauve";
}
