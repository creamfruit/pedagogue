export const FIGURE_PARALLAX = 0.6;
const SEEN_KEY = "pp.sky-figures-seen";
const BLOOM_TICKS = 240;

const ring = (count, radius = 0.85, start = -Math.PI / 2) =>
  Array.from({ length: count }, (_, index) => {
    const angle = start + (index / count) * Math.PI * 2;
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  });
const chain = (count, from = 0) => Array.from({ length: count - 1 }, (_, index) => [from + index, from + index + 1]);
const loop = (count, from = 0) => [...chain(count, from), [from + count - 1, from]];
const arc = (count, radius, from, to) =>
  Array.from({ length: count }, (_, index) => {
    const angle = from + ((to - from) * index) / (count - 1);
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  });
const chevron = (dy) => [[-1, 0.6 + dy], [-0.5, 0.05 + dy], [0, -0.5 + dy], [0.5, 0.05 + dy], [1, 0.6 + dy]];

export const FIGURES = {
  first_piece: { points: [[0, 0], [0.9, -0.55], [0.55, 0.8]], edges: [[0, 1], [0, 2]], size: 22 },
  first_learned: { points: [[-0.95, 0.3], [0, -0.2], [0.95, 0.1]], edges: chain(3), size: 26 },
  five_learned: { points: [[-1, -0.4], [-0.5, 0.5], [0, -0.1], [0.5, 0.55], [1, -0.35]], edges: chain(5), size: 32 },
  twenty_learned: {
    points: [[0, -1], [0, -0.35], [0, 0.35], [0, 1], [-0.9, -0.2], [-0.45, -0.3], [0.45, -0.3], [0.9, -0.2]],
    edges: [[0, 1], [1, 2], [2, 3], [4, 5], [5, 1], [1, 6], [6, 7]],
    size: 40,
  },
  first_submission: { points: [[0, 0], ...ring(6)], edges: loop(6, 1), size: 26 },
  first_pass: { points: [[-0.9, 0], [-0.3, 0.6], [0.9, -0.8]], edges: chain(3), size: 24 },
  grade_ninety: { points: [[0, -1], [0.6, -0.1], [0, 1], [-0.6, -0.1]], edges: loop(4), size: 28 },
  flawless: { points: ring(5, 1), edges: [[0, 2], [2, 4], [4, 1], [1, 3], [3, 0]], size: 34 },
  five_graded: { points: arc(5, 1, Math.PI * 1.1, Math.PI * 1.9), edges: chain(5), size: 32 },
  grade_eight_club: { points: ring(8, 0.9, -Math.PI / 8), edges: loop(8), size: 32 },
  virtuoso: {
    points: [[-1, 0.6], [-1, -0.5], [-0.5, 0.1], [0, -0.9], [0.5, 0.1], [1, -0.5], [1, 0.6]],
    edges: [...chain(7), [6, 0]],
    size: 36,
  },
  polyrhythm_steady: {
    points: [[-1, -0.4], [0, -0.4], [1, -0.4], [-0.5, 0.5], [0.5, 0.5]],
    edges: [[0, 3], [3, 1], [1, 4], [4, 2]],
    size: 30,
  },
  level_five: { points: chevron(0), edges: chain(5), size: 28 },
  level_ten: { points: [...chevron(-0.45), ...chevron(0.45)], edges: [...chain(5), ...chain(5, 5)], size: 34 },
  first_fortune: { points: [[0, 0], ...ring(7, 0.8)], edges: loop(7, 1), size: 28 },
  streak_three: { points: [[-0.9, 0.25], [0, 0], [0.9, -0.25]], edges: chain(3), size: 26 },
  streak_week: {
    points: [[-1, -0.35], [-0.55, -0.2], [-0.15, -0.05], [0.2, 0.1], [0.3, 0.65], [0.95, 0.75], [1, 0.2]],
    edges: [...chain(7), [6, 3]],
    size: 38,
  },
  streak_month: {
    points: [...arc(5, 1, -Math.PI * 0.62, Math.PI * 0.62), ...arc(3, 0.62, Math.PI * 0.38, -Math.PI * 0.38).map(([x, y]) => [x - 0.28, y])],
    edges: [...chain(5), [4, 5], ...chain(3, 5), [7, 0]],
    size: 34,
  },
};

const ORDER = Object.keys(FIGURES);

function clamp(value, low, high) {
  return low > high ? (low + high) / 2 : Math.min(Math.max(value, low), high);
}

function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

export function figureFor(code) {
  if (FIGURES[code]) return FIGURES[code];
  const seed = hash(code);
  const count = 3 + (seed % 4);
  const points = Array.from({ length: count }, (_, index) => {
    const angle = ((seed >> (index * 3)) % 360) * (Math.PI / 180);
    const radius = 0.4 + (((seed >> (index * 2)) % 60) / 100);
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  });
  return { points, edges: chain(count), size: 28 };
}

export function anchorFor(code) {
  const index = ORDER.indexOf(code);
  const slot = index === -1 ? hash(code) % 97 : index;
  const count = index === -1 ? 97 : ORDER.length;
  const angle = -Math.PI / 2 + (slot / count) * Math.PI * 2 + (index === -1 ? 0.13 : 0);
  const reach = 0.4 + ((slot * 7) % 5) * 0.025;
  return { angle, reach };
}

export function layoutFigures(achievements, width, height) {
  return achievements
    .filter((achievement) => achievement.earned)
    .map((achievement) => {
      const shape = figureFor(achievement.code);
      const { angle, reach } = anchorFor(achievement.code);
      const scale = shape.size * Math.min(1, Math.max(0.7, Math.min(width, height) / 560));
      const margin = scale * 1.1 + 14;
      const cx = clamp(width / 2 + Math.cos(angle) * width * reach, margin, width - margin);
      const cy = clamp(height / 2 + Math.sin(angle) * height * reach, margin, height - margin - 12);
      const stars = shape.points.map(([x, y], index) => ({ x: cx + x * scale, y: cy + y * scale, lead: index === 0, phase: (hash(achievement.code) + index * 97) % 628 / 100 }));
      return { achievement, cx, cy, radius: scale * 1.15, stars, edges: shape.edges, bloom: 0 };
    });
}

export function toFigureSpace(point, transform) {
  const zoom = 1 + (transform.k - 1) * FIGURE_PARALLAX;
  return { x: (point.x - transform.x * FIGURE_PARALLAX) / zoom, y: (point.y - transform.y * FIGURE_PARALLAX) / zoom };
}

export function figureAt(figures, point, slack = 10) {
  let best = null;
  let bestDistance = Infinity;
  figures.forEach((figure) => {
    figure.stars.forEach((star) => {
      const distance = Math.hypot(star.x - point.x, star.y - point.y);
      if (distance <= slack && distance < bestDistance) {
        best = figure;
        bestDistance = distance;
      }
    });
    figure.edges.forEach(([a, b]) => {
      const from = figure.stars[a];
      const to = figure.stars[b];
      const vx = to.x - from.x;
      const vy = to.y - from.y;
      const length = vx * vx + vy * vy;
      if (!length) return;
      const t = Math.max(0, Math.min(1, ((point.x - from.x) * vx + (point.y - from.y) * vy) / length));
      const distance = Math.hypot(point.x - (from.x + t * vx), point.y - (from.y + t * vy));
      if (distance <= slack * 0.6 && distance + 2 < bestDistance) {
        best = figure;
        bestDistance = distance + 2;
      }
    });
  });
  return best;
}

export function markNewFigures(figures) {
  let seen = [];
  try {
    seen = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
  } catch {
    seen = [];
  }
  const known = new Set(seen);
  const fresh = figures.filter((figure) => !known.has(figure.achievement.code));
  fresh.forEach((figure) => {
    figure.bloom = BLOOM_TICKS;
  });
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...known, ...fresh.map((figure) => figure.achievement.code)]));
  } catch {
    return fresh.length;
  }
  return fresh.length;
}

function sparkle(ctx, x, y, reach, width) {
  ctx.beginPath();
  ctx.moveTo(x, y - reach);
  ctx.quadraticCurveTo(x + width, y - width, x + reach, y);
  ctx.quadraticCurveTo(x + width, y + width, x, y + reach);
  ctx.quadraticCurveTo(x - width, y + width, x - reach, y);
  ctx.quadraticCurveTo(x - width, y - width, x, y - reach);
  ctx.closePath();
  ctx.fill();
}

export function drawFigures(ctx, figures, { transform, colors, clock, reduceMotion, hovered, font }) {
  if (!figures.length) return;
  const zoom = 1 + (transform.k - 1) * FIGURE_PARALLAX;
  ctx.save();
  ctx.translate(transform.x * FIGURE_PARALLAX, transform.y * FIGURE_PARALLAX);
  ctx.scale(zoom, zoom);
  figures.forEach((figure) => {
    const active = figure === hovered;
    const bloom = figure.bloom > 0 ? figure.bloom / BLOOM_TICKS : 0;
    if (figure.bloom > 0) figure.bloom -= 1;

    if (bloom > 0) {
      const halo = ctx.createRadialGradient(figure.cx, figure.cy, 0, figure.cx, figure.cy, figure.radius * (1.4 + (1 - bloom) * 0.8));
      halo.addColorStop(0, colors.tide);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = 0.16 * bloom;
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(figure.cx, figure.cy, figure.radius * 2.2, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.strokeStyle = colors.tide;
    ctx.lineWidth = (active ? 1.3 : 0.9) / zoom;
    ctx.globalAlpha = active ? 0.62 : 0.26 + bloom * 0.3;
    ctx.setLineDash([3 / zoom, 3 / zoom]);
    ctx.beginPath();
    figure.edges.forEach(([a, b]) => {
      ctx.moveTo(figure.stars[a].x, figure.stars[a].y);
      ctx.lineTo(figure.stars[b].x, figure.stars[b].y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = colors.tide;
    figure.stars.forEach((star) => {
      const twinkle = reduceMotion ? 1 : 0.78 + 0.22 * Math.sin(clock * 0.03 + star.phase);
      const reach = (star.lead ? 5.2 : 3.4) * (active ? 1.25 : 1) * (1 + bloom * 0.5);
      ctx.globalAlpha = Math.min(1, (active ? 1 : 0.82) * twinkle + bloom * 0.2);
      sparkle(ctx, star.x, star.y, reach / zoom, reach * 0.18 / zoom);
    });

    if (active || bloom > 0) {
      ctx.globalAlpha = active ? 1 : bloom;
      ctx.font = `${10.5 / zoom}px ${font}`;
      ctx.textAlign = "center";
      ctx.fillStyle = colors.tide;
      const lowest = Math.max(...figure.stars.map((star) => star.y));
      ctx.fillText(figure.achievement.name.toUpperCase(), figure.cx, lowest + 16 / zoom);
    }
  });
  ctx.globalAlpha = 1;
  ctx.restore();
}
