import { ERA_STYLE, difficultyTone, palette } from "./palette.js";

const SAMPLE_STARS = [
  { x: 0.18, y: 0.3, era: "Baroque", difficulty: 35 },
  { x: 0.32, y: 0.62, era: "Classical", difficulty: 48 },
  { x: 0.46, y: 0.24, era: "Romantic", difficulty: 82 },
  { x: 0.58, y: 0.55, era: "Romantic", difficulty: 92 },
  { x: 0.7, y: 0.3, era: "Impressionist", difficulty: 66 },
  { x: 0.84, y: 0.62, era: "Modern", difficulty: 88 },
  { x: 0.26, y: 0.84, era: "Contemporary", difficulty: 58 },
  { x: 0.76, y: 0.84, era: "Classical", difficulty: 40 },
];
const SAMPLE_LINKS = [
  [0, 1], [1, 3], [2, 3], [2, 4], [3, 5], [4, 5], [1, 6], [3, 7], [5, 7],
];
const BACKDROP = Array.from({ length: 70 }, (_, index) => ({
  x: ((index * 7919) % 1000) / 1000,
  y: ((index * 104729) % 997) / 997,
  size: 0.4 + ((index * 31) % 10) / 12,
  alpha: 0.15 + ((index * 17) % 10) / 22,
}));

function starColor(star, style, colors) {
  if (style.mode === "fixed" && style.color) return style.color;
  if (style.mode === "difficulty") return colors[difficultyTone(star.difficulty)];
  const era = ERA_STYLE[star.era];
  return era ? colors[era.tone] : colors.text;
}

export function drawSkyPreview(canvas, loadout) {
  const colors = palette();
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 320;
  const height = canvas.clientHeight || 200;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = colors.bgSunk;
  ctx.fillRect(0, 0, width, height);

  (loadout.nebula?.layers || []).forEach((layer) => {
    const cx = (layer.x / 100) * width;
    const cy = (layer.y / 100) * height;
    const radius = (layer.r / 100) * Math.max(width, height);
    const cloud = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    cloud.addColorStop(0, `rgba(${layer.color},${Math.min(layer.alpha * 2.2, 0.5)})`);
    cloud.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = cloud;
    ctx.fillRect(0, 0, width, height);
  });

  ctx.fillStyle = colors.starlight;
  BACKDROP.forEach((dot) => {
    ctx.globalAlpha = dot.alpha;
    ctx.beginPath();
    ctx.arc(dot.x * width, dot.y * height, dot.size, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;

  const link = loadout.link_style || { width: 1, alpha: 1, dash: null };
  ctx.lineWidth = link.width || 1;
  ctx.strokeStyle = colors.orange;
  ctx.globalAlpha = Math.min(0.5 * (link.alpha ?? 1), 1);
  ctx.setLineDash(link.dash || []);
  SAMPLE_LINKS.forEach(([a, b]) => {
    ctx.beginPath();
    ctx.moveTo(SAMPLE_STARS[a].x * width, SAMPLE_STARS[a].y * height);
    ctx.lineTo(SAMPLE_STARS[b].x * width, SAMPLE_STARS[b].y * height);
    ctx.stroke();
  });
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;

  const glow = loadout.glow || { scale: 1, core: 0.42 };
  const style = loadout.star_color || { mode: "era" };
  SAMPLE_STARS.forEach((star) => {
    const x = star.x * width;
    const y = star.y * height;
    const core = 2 + (star.difficulty / 100) * 4.5;
    const color = starColor(star, style, colors);
    const halo = core * 3.8 * (glow.scale ?? 1);
    if (halo > 0) {
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, halo);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = 0.28;
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, halo, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, core, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = colors.starlight;
    ctx.beginPath();
    ctx.arc(x, y, core * (glow.core ?? 0.42), 0, Math.PI * 2);
    ctx.fill();
  });
}
