import { el } from "./dom.js";

// Canvas drawing cannot use CSS custom properties directly, so this reads the
// four accent tokens (and the neutrals) from styles.css :root at runtime. The
// fallbacks only matter if the stylesheet has not loaded; keep them in sync.
const FALLBACK = {
  yellow: "#ffd08a",
  accent: "#ff4fa3",
  violet: "#a78bfa",
  starlight: "#e8ecf5",
  bgSunk: "#04050c",
  text: "#e4e3ef",
  textDim: "#9d9eb6",
  textFaint: "#666982",
  lineStrong: "#2a2f4a",
};

const TOKENS = {
  yellow: "--yellow",
  accent: "--accent",
  violet: "--violet",
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
  Baroque: { tone: "yellow", spiked: false },
  Classical: { tone: "yellow", spiked: true },
  Romantic: { tone: "accent", spiked: false },
  Impressionist: { tone: "accent", spiked: true },
  Modern: { tone: "violet", spiked: false },
  Contemporary: { tone: "violet", spiked: true },
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

// Heat ramp for the "difficulty" star cosmetic: violet for the easiest pieces,
// then pink, yellow, and starlight for the hardest.
export function difficultyTone(difficulty) {
  if (difficulty >= 90) return "starlight";
  if (difficulty >= 75) return "yellow";
  if (difficulty >= 55) return "accent";
  return "violet";
}
