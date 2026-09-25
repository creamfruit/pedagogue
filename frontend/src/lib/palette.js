import { el } from "./dom.js";

// Canvas drawing cannot use CSS custom properties directly, so this reads the
// four accent tokens (and the neutrals) from styles.css :root at runtime. The
// fallbacks only matter if the stylesheet has not loaded; keep them in sync.
const FALLBACK = {
  yellow: "#ffd08a",
  orange: "#f0a13c",
  pink: "#e05a78",
  black: "#020202",
  text: "#ddd9d3",
  textDim: "#9a958d",
  textFaint: "#63605a",
  lineStrong: "#2b2e33",
};

const TOKENS = {
  yellow: "--yellow",
  orange: "--orange",
  pink: "--pink",
  black: "--black",
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
  cached.white = "#ffffff";
  return cached;
}

// Six eras on three warm accents. Chronological pairs share a hue and the later
// era of each pair is drawn with diffraction spikes, so every era stays
// distinguishable without a fifth colour.
export const ERA_STYLE = {
  Baroque: { tone: "yellow", spiked: false },
  Classical: { tone: "yellow", spiked: true },
  Romantic: { tone: "orange", spiked: false },
  Impressionist: { tone: "orange", spiked: true },
  Modern: { tone: "pink", spiked: false },
  Contemporary: { tone: "pink", spiked: true },
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

// Heat ramp for the "difficulty" star cosmetic: pink for the easiest pieces,
// then orange, yellow, and white-hot for the hardest.
export function difficultyTone(difficulty) {
  if (difficulty >= 90) return "white";
  if (difficulty >= 75) return "yellow";
  if (difficulty >= 55) return "orange";
  return "pink";
}
