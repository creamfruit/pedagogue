import { el } from "./dom.js";

// Canvas drawing cannot use CSS custom properties directly, so this reads the
// four accent tokens (and the neutrals) from styles.css :root at runtime. The
// fallbacks only matter if the stylesheet has not loaded; keep them in sync.
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

// Six eras on three warm accents. Chronological pairs share a hue and the later
// era of each pair is drawn with diffraction spikes, so every era stays
// distinguishable without a fifth colour.
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

// Heat ramp for the "difficulty" star cosmetic: mauve for the easiest pieces,
// then mint, tide, and starlight for the hardest.
export function difficultyTone(difficulty) {
  if (difficulty >= 90) return "starlight";
  if (difficulty >= 75) return "tide";
  if (difficulty >= 55) return "accent";
  return "mauve";
}
