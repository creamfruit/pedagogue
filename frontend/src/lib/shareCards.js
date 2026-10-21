import { siteUrl, shareCanvas } from "./share.js";

export const CARD_WIDTH = 1080;
export const CARD_HEIGHT = 1350;

const FONT = '"Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace';

export const PALETTE = {
  top: "#102039",
  middle: "#0a1120",
  bottom: "#04080f",
  panel: "#101a2b",
  line: "#2f4468",
  text: "#e4eeee",
  dim: "#9fb3b8",
  accent: "#cee9e2",
  good: "#7fd1b0",
  warn: "#e8c26a",
  hot: "#e58f8f",
};

const MILESTONES = [3, 7, 14, 30, 60, 100, 200, 365, 500, 1000];

function seeded(seed) {
  let value = seed >>> 0;
  return () => {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

export function hostLabel() {
  const address = siteUrl("/");
  if (!address) return "Pedagogue";
  try {
    return new URL(address).host;
  } catch {
    return "Pedagogue";
  }
}

export function streakCardModel(streak) {
  const current = Math.max(0, Number(streak?.current) || 0);
  const longest = Math.max(current, Number(streak?.longest) || 0);
  const next = MILESTONES.find((milestone) => milestone > current) || current + 1;
  const previous = [...MILESTONES].reverse().find((milestone) => milestone <= current) || 0;
  return {
    current,
    longest,
    label: current === 1 ? "day in a row" : "days in a row",
    next,
    toNext: next - current,
    progress: next === previous ? 1 : (current - previous) / (next - previous),
    message: current ? `${next - current} more ${next - current === 1 ? "day" : "days"} to ${next}` : "Practise today to start a streak",
  };
}

export function bandColor(score) {
  const value = Number(score);
  if (value >= 60) return PALETTE.hot;
  if (value >= 30) return PALETTE.warn;
  return PALETTE.good;
}

export function pieceCardModel(overview) {
  const score = Number(overview?.difficulty_score);
  const sections = [...(overview?.sections || [])]
    .filter((section) => section.difficulty_score !== null && section.difficulty_score !== undefined)
    .sort((a, b) => Number(b.difficulty_score) - Number(a.difficulty_score));
  const hardest = sections[0] || (overview?.sections || [])[0] || null;
  const facts = [overview?.key_signature, overview?.year_composed, overview?.duration_sec ? overview.duration_label : null].filter(Boolean).map(String);
  return {
    title: overview?.title || "",
    composer: overview?.composer?.name || "",
    score: Number.isFinite(score) ? Math.round(score * 10) / 10 : null,
    band: overview?.difficulty_band && overview.difficulty_band !== "unrated" ? overview.difficulty_band : "",
    facts,
    techniques: (overview?.techniques || []).slice(0, 3).map((technique) => technique.name),
    hardest: hardest ? `${hardest.label || "Hardest section"} · ${hardest.measure_span}` : "",
  };
}

export function constellationCardModel(stars) {
  const count = Number(stars) || 0;
  return { count, label: count === 1 ? "star" : "stars" };
}

export function wrapLines(context, text, maxWidth, maxLines) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const trial = line ? `${line} ${word}` : word;
    if (context.measureText(trial).width <= maxWidth || !line) {
      line = trial;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    kept[maxLines - 1] = `${kept[maxLines - 1].replace(/[\s.,;:]+$/, "")}…`;
    return kept;
  }
  return lines;
}

function roundedRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  context.closePath();
}

export function drawBackdrop(context, { kicker, footer = hostLabel(), seed = 7 }) {
  const gradient = context.createLinearGradient(0, 0, 0, CARD_HEIGHT);
  gradient.addColorStop(0, PALETTE.top);
  gradient.addColorStop(0.45, PALETTE.middle);
  gradient.addColorStop(1, PALETTE.bottom);
  context.fillStyle = gradient;
  context.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  const random = seeded(seed);
  for (let index = 0; index < 90; index += 1) {
    const x = random() * CARD_WIDTH;
    const y = random() * CARD_HEIGHT;
    context.globalAlpha = 0.15 + random() * 0.5;
    context.fillStyle = PALETTE.accent;
    context.beginPath();
    context.arc(x, y, 0.8 + random() * 1.8, 0, Math.PI * 2);
    context.fill();
  }
  context.globalAlpha = 1;
  context.textBaseline = "alphabetic";
  context.textAlign = "left";
  context.fillStyle = PALETTE.accent;
  context.font = `600 34px ${FONT}`;
  context.fillText("PEDAGOGUE", 72, 110);
  context.fillStyle = PALETTE.dim;
  context.font = `500 26px ${MONO}`;
  context.textAlign = "right";
  context.fillText(String(kicker || "").toUpperCase(), CARD_WIDTH - 72, 110);
  context.textAlign = "left";
  context.strokeStyle = PALETTE.line;
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(72, 150);
  context.lineTo(CARD_WIDTH - 72, 150);
  context.stroke();
  context.fillStyle = PALETTE.dim;
  context.font = `500 28px ${FONT}`;
  context.textAlign = "center";
  context.fillText(footer, CARD_WIDTH / 2, CARD_HEIGHT - 70);
  context.textAlign = "left";
}

export function drawStreakCard(context, model, { footer } = {}) {
  drawBackdrop(context, { kicker: "Practice streak", footer, seed: 11 });
  const centreX = CARD_WIDTH / 2;
  const centreY = 640;
  const radius = 300;
  context.lineWidth = 34;
  context.lineCap = "round";
  context.strokeStyle = PALETTE.line;
  context.beginPath();
  context.arc(centreX, centreY, radius, 0, Math.PI * 2);
  context.stroke();
  if (model.progress > 0) {
    context.strokeStyle = PALETTE.accent;
    context.beginPath();
    context.arc(centreX, centreY, radius, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, model.progress));
    context.stroke();
  }
  context.textAlign = "center";
  context.fillStyle = PALETTE.text;
  context.font = `600 ${String(model.current).length > 3 ? 190 : 260}px ${FONT}`;
  context.fillText(String(model.current), centreX, centreY + 70);
  context.fillStyle = PALETTE.dim;
  context.font = `500 44px ${FONT}`;
  context.fillText(model.label, centreX, centreY + 150);
  context.fillStyle = PALETTE.text;
  context.font = `500 40px ${FONT}`;
  context.fillText(model.message, centreX, 1100);
  context.fillStyle = PALETTE.dim;
  context.font = `500 32px ${MONO}`;
  context.fillText(`longest streak ${model.longest}`, centreX, 1170);
  context.textAlign = "left";
}

export function drawPieceCard(context, model, { footer } = {}) {
  drawBackdrop(context, { kicker: "How hard is it?", footer, seed: 23 });
  context.textAlign = "left";
  context.fillStyle = PALETTE.text;
  context.font = `600 74px ${FONT}`;
  const titleLines = wrapLines(context, model.title, CARD_WIDTH - 144, 3);
  let y = 270;
  for (const line of titleLines) {
    context.fillText(line, 72, y);
    y += 88;
  }
  context.fillStyle = PALETTE.dim;
  context.font = `500 40px ${FONT}`;
  if (model.composer) {
    context.fillText(model.composer, 72, y + 10);
    y += 70;
  }
  const top = Math.max(y + 40, 560);
  context.fillStyle = PALETTE.panel;
  roundedRect(context, 72, top, CARD_WIDTH - 144, 330, 24);
  context.fill();
  context.strokeStyle = PALETTE.line;
  context.lineWidth = 2;
  context.stroke();
  const colour = model.score === null ? PALETTE.dim : bandColor(model.score);
  context.fillStyle = colour;
  context.font = `600 150px ${FONT}`;
  context.fillText(model.score === null ? "—" : String(model.score), 110, top + 170);
  context.fillStyle = PALETTE.dim;
  context.font = `500 36px ${FONT}`;
  context.fillText("out of 100", 110, top + 225);
  if (model.band) {
    context.fillStyle = colour;
    context.font = `600 42px ${FONT}`;
    context.textAlign = "right";
    context.fillText(model.band, CARD_WIDTH - 110, top + 90);
    context.textAlign = "left";
  }
  const barX = 110;
  const barY = top + 262;
  const barWidth = CARD_WIDTH - 220;
  context.fillStyle = PALETTE.bottom;
  roundedRect(context, barX, barY, barWidth, 24, 12);
  context.fill();
  if (model.score !== null) {
    const fill = context.createLinearGradient(barX, 0, barX + barWidth, 0);
    fill.addColorStop(0, PALETTE.good);
    fill.addColorStop(0.5, PALETTE.warn);
    fill.addColorStop(1, PALETTE.hot);
    context.fillStyle = fill;
    roundedRect(context, barX, barY, Math.max(24, (barWidth * model.score) / 100), 24, 12);
    context.fill();
  }
  let below = top + 330 + 60;
  if (model.hardest) {
    context.fillStyle = PALETTE.dim;
    context.font = `500 30px ${MONO}`;
    context.fillText("HARDEST SECTION", 72, below);
    context.fillStyle = PALETTE.text;
    context.font = `500 40px ${FONT}`;
    context.fillText(wrapLines(context, model.hardest, CARD_WIDTH - 144, 1)[0] || "", 72, below + 56);
    below += 130;
  }
  if (model.techniques.length) {
    context.fillStyle = PALETTE.dim;
    context.font = `500 30px ${MONO}`;
    context.fillText("TECHNIQUES", 72, below);
    let x = 72;
    let rowY = below + 40;
    context.font = `500 34px ${FONT}`;
    for (const name of model.techniques) {
      const width = context.measureText(name).width + 48;
      if (x + width > CARD_WIDTH - 72) {
        x = 72;
        rowY += 72;
      }
      context.strokeStyle = PALETTE.line;
      context.lineWidth = 2;
      roundedRect(context, x, rowY, width, 56, 28);
      context.stroke();
      context.fillStyle = PALETTE.text;
      context.fillText(name, x + 24, rowY + 38);
      x += width + 16;
    }
  }
}

export function drawConstellationCard(context, model, source, { footer, background = PALETTE.bottom } = {}) {
  drawBackdrop(context, { kicker: "My constellation", footer, seed: 31 });
  const frameX = 72;
  const frameY = 190;
  const frameWidth = CARD_WIDTH - 144;
  const frameHeight = 880;
  context.fillStyle = background;
  roundedRect(context, frameX, frameY, frameWidth, frameHeight, 24);
  context.fill();
  context.strokeStyle = PALETTE.line;
  context.lineWidth = 2;
  context.stroke();
  if (source && source.width && source.height) {
    const scale = Math.min(frameWidth / source.width, frameHeight / source.height);
    const width = source.width * scale;
    const height = source.height * scale;
    context.save();
    roundedRect(context, frameX, frameY, frameWidth, frameHeight, 24);
    context.clip();
    context.drawImage(source, frameX + (frameWidth - width) / 2, frameY + (frameHeight - height) / 2, width, height);
    context.restore();
  }
  context.textAlign = "center";
  context.fillStyle = PALETTE.text;
  context.font = `600 64px ${FONT}`;
  context.fillText(`${model.count} ${model.label}`, CARD_WIDTH / 2, 1170);
  context.fillStyle = PALETTE.dim;
  context.font = `500 32px ${FONT}`;
  context.fillText("every piece I've played, as a sky", CARD_WIDTH / 2, 1228);
  context.textAlign = "left";
}

function blankCanvas() {
  const canvas = document.createElement("canvas");
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser can't draw the card");
  return { canvas, context };
}

async function fontsReady() {
  try {
    await Promise.all([document.fonts?.load(`600 40px ${FONT}`), document.fonts?.load(`500 26px ${MONO}`)]);
  } catch {
    return;
  }
}

export async function renderStreakCard(streak) {
  await fontsReady();
  const { canvas, context } = blankCanvas();
  drawStreakCard(context, streakCardModel(streak));
  return canvas;
}

export async function renderPieceCard(overview) {
  await fontsReady();
  const { canvas, context } = blankCanvas();
  drawPieceCard(context, pieceCardModel(overview));
  return canvas;
}

export async function renderConstellationCard(source, stars, background) {
  await fontsReady();
  const { canvas, context } = blankCanvas();
  drawConstellationCard(context, constellationCardModel(stars), source, { background });
  return canvas;
}

export const CARD_COPY = {
  streak: (model) => ({
    title: "My practice streak",
    text: `${model.current} ${model.label} on Pedagogue.`,
    fileName: `pedagogue-streak-${model.current}.png`,
  }),
  piece: (model) => ({
    title: model.title,
    text: `${model.title}${model.composer ? ` by ${model.composer}` : ""}${model.score === null ? "" : ` scores ${model.score} out of 100 for difficulty`} on Pedagogue.`,
    fileName: `pedagogue-${String(model.title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "piece"}.png`,
  }),
  constellation: (model) => ({
    title: "My constellation",
    text: `My piano repertoire as a constellation: ${model.count} ${model.label} on Pedagogue.`,
    fileName: "pedagogue-constellation.png",
  }),
};

export async function shareCard(canvas, copy) {
  return shareCanvas(canvas, { ...copy, background: PALETTE.bottom, webShare: false });
}
