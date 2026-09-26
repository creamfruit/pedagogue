import { api } from "../api/client.js";
import { linkSummaryPanel } from "../components/overview.js";
import { el, empty, reveal, skeletonBlock } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import {
  DRIFT,
  createPointerTracker,
  createRipples,
  forceDrift,
  grab,
  moveGrab,
  release,
} from "../lib/drift.js";
import { ERA_STYLE, difficultyTone, eraGlyph, palette } from "../lib/palette.js";

// Link type is carried by accent and dash pattern together, so the three types
// stay distinct in the legend and on the canvas even where hues sit close.
const LINK_STYLES = {
  composer: { tone: "orange", dash: null },
  technique: { tone: "yellow", dash: [7, 4] },
  era_genre: { tone: "pink", dash: [1.5, 4] },
};

const LINK_LABELS = {
  composer: "composer",
  technique: "technique",
  era_genre: "era / genre",
};

// Star size grows exponentially with difficulty (0-100). The catalogue clusters
// between roughly 75 and 95, so a linear ramp left most stars looking alike.
// radius feeds mass and wall padding in lib/drift.js, so it scales with the same
// curve: a star that looks twice as big is also heavier to throw.
const DOT_MIN = 1.6;
const DOT_MAX = 9.5;
const RADIUS_PER_DOT = 2.8;

export function starDot(difficulty) {
  const t = Math.min(Math.max(difficulty ?? 50, 0), 100) / 100;
  return DOT_MIN * Math.pow(DOT_MAX / DOT_MIN, t);
}

const AMBIENT_ALPHA = 0.015;
const BACKDROP_STARS = 240;
const PARALLAX = 0.3;
const TRAIL_SPEED = 2.4;

export async function constellationView(outlet) {
  const legendHost = el("div", { class: "legend" });
  const canvas = el("canvas");
  const detail = el("div", { class: "panel", style: "margin-top:16px" });
  const drawerBody = el("div", { class: "sky-drawer-body" });
  const drawerClose = el("button", { type: "button", class: "sky-drawer-close", "aria-label": "Close details" }, "×");
  const drawer = el("aside", { class: "sky-drawer", hidden: true, "aria-label": "Selected star or connection", tabindex: "-1" }, drawerClose, drawerBody);

  function showDrawer(...content) {
    drawerBody.replaceChildren(...content.filter(Boolean));
    drawer.hidden = false;
    if (window.matchMedia("(max-width: 899px)").matches) drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeDrawer() {
    drawer.hidden = true;
    selectedLink = null;
    draw();
  }

  drawerClose.addEventListener("click", closeDrawer);
  drawer.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });

  function chartGuide() {
    const item = (term, meaning) => el("li", {}, el("strong", { style: "font-weight:500" }, term), " — ", meaning);
    const guide = reveal(
      "How to read the chart",
      el(
        "ul",
        { class: "chart-guide" },
        item("Lines", "join pieces that share a composer (solid orange), a technique (dashed yellow) or an era or genre (dotted pink). Tap a type in the legend to hide it."),
        item("Colour", "is the star's era: eras that follow each other share a hue, and the later one carries a cross of spikes. An equipped star colour from the Observatory replaces this."),
        item("Size", "is difficulty. Harder pieces are bigger stars, and heavier to throw."),
        item("Bright core", "marks a top-ten piece or the star you're holding."),
        item("Hollow, dashed star", "needs a verification take before it lights up."),
        item("Faded star", "is drifting from lack of practice; a fine dashed ring around it means it has frozen."),
        item("Dark core with a pale outline", "is a custom piece you added yourself.")
      )
    );
    return [guide.button, guide.region];
  }

  function showIntro() {
    detail.replaceChildren(
      el(
        "p",
        { class: "faint", style: "margin:0" },
        "Tap a star to read the piece, or a connector to read why two pieces are linked. Drag a star to send it drifting; drag the sky to pan, and scroll or pinch to zoom."
      ),
      ...chartGuide()
    );
  }
  showIntro();
  const wrap = el("div", { class: "constellation-wrap" }, legendHost, canvas, drawer);
  const loading = el("div", {}, skeletonBlock(4));

  const headline = el("p", { class: "faint mono", style: "margin:0;font-size:12px" });
  outlet.append(
    el("div", { class: "page-head", style: "align-items:baseline" }, el("h1", { style: "margin:0" }, "Constellation"), headline),
    loading
  );

  let graph;
  let loadout = store.loadout;
  try {
    const [graphResult, loadoutResult] = await Promise.all([
      api.constellation({ threshold: 0.25 }),
      loadout ? Promise.resolve(loadout) : api.loadout().catch(() => null),
    ]);
    graph = graphResult;
    loadout = loadoutResult || {};
  } catch (error) {
    loading.replaceChildren(empty(error.detail || "Could not load the constellation."));
    return;
  }

  loading.remove();
  headline.textContent = `${graph.nodes.length} star${graph.nodes.length === 1 ? "" : "s"} · ${graph.links.length} connection${graph.links.length === 1 ? "" : "s"}`;
  outlet.append(wrap, detail);

  if (!graph.nodes.length) {
    wrap.replaceChildren(empty("Add pieces to your repertoire and they will appear here."));
    return;
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const enabled = new Set(graph.link_types);
  const colors = palette();
  const linkColor = (type) => (LINK_STYLES[type] ? colors[LINK_STYLES[type].tone] : colors.lineStrong);

  Object.keys(LINK_STYLES).forEach((type) => {
    if (!graph.link_types.includes(type)) return;
    const { dash } = LINK_STYLES[type];
    const button = el(
      "button",
      {
        type: "button",
        "aria-pressed": "true",
        style: `color:${linkColor(type)}`,
        onclick: () => {
          if (enabled.has(type)) enabled.delete(type);
          else enabled.add(type);
          button.setAttribute("aria-pressed", enabled.has(type) ? "true" : "false");
          draw();
        },
      },
      el("span", {
        class: "swatch",
        style: dash
          ? `background:repeating-linear-gradient(90deg,currentColor 0 ${dash[0]}px,transparent ${dash[0]}px ${dash[0] + dash[1]}px)`
          : null,
      }),
      LINK_LABELS[type]
    );
    legendHost.append(button);
  });

  legendHost.append(
    el(
      "button",
      {
        type: "button",
        class: "legend-reset",
        onclick: () => {
          transform = { x: 0, y: 0, k: 1 };
          draw();
        },
      },
      "recentre"
    )
  );

  const starStyle = (loadout && loadout.star_color && loadout.star_color.payload) || { mode: "era" };
  const glowStyle = (loadout && loadout.glow && loadout.glow.payload) || { scale: 1, core: 0.42 };
  const linkStyle = (loadout && loadout.link_style && loadout.link_style.payload) || {
    width: 1,
    alpha: 1,
    dash: null,
  };
  const nebulaLayers = (loadout && loadout.nebula && loadout.nebula.payload?.layers) || [];

  if (starStyle.mode === "era" || !starStyle.mode) {
    const eras = Object.keys(ERA_STYLE).filter((era) => graph.nodes.some((node) => node.era === era));
    if (eras.length) {
      legendHost.append(
        el(
          "div",
          { class: "era-keys", "aria-label": "Era key" },
          ...eras.map((era) => el("span", { class: "era-key" }, eraGlyph(era), era))
        )
      );
    }
  }

  function starLook(node) {
    const difficulty = node.difficulty ?? 50;
    if (node.is_custom) return { color: colors.bgSunk, halo: colors.starlight, outline: colors.starlight, spiked: false };
    if (starStyle.mode === "fixed" && starStyle.color) return { color: starStyle.color, spiked: false };
    if (starStyle.mode === "difficulty") return { color: colors[difficultyTone(difficulty)], spiked: false };
    const era = ERA_STYLE[node.era];
    if (!era) return { color: colors.text, spiked: false };
    return { color: colors[era.tone], spiked: era.spiked };
  }

  const nodes = graph.nodes.map((node) => {
    const look = starLook(node);
    const dot = starDot(node.difficulty);
    return {
      ...node,
      dot,
      radius: dot * RADIUS_PER_DOT,
      color: look.color,
      halo: look.halo || look.color,
      outline: look.outline || null,
      spiked: look.spiked,
    };
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const links = graph.links
    .map((link) => ({ ...link, source: byId.get(link.source), target: byId.get(link.target) }))
    .filter((link) => link.source && link.target);

  const ctx = canvas.getContext("2d");
  const ripples = createRipples();
  const tracker = createPointerTracker();
  let width = 0;
  let height = 0;
  let transform = { x: 0, y: 0, k: 1 };
  let hovered = null;
  let hoveredLink = null;
  let selectedLink = null;
  let dragging = null;
  let panning = null;
  let activePointer = null;
  let running = true;
  let backdrop = [];
  let clock = 0;

  const drift = forceDrift();
  drift.ambient(!reduceMotion);

  const simulation = forceSimulation(nodes)
    .velocityDecay(0)
    .alphaDecay(0.012)
    .alphaMin(0.0001)
    .alphaTarget(reduceMotion ? 0 : AMBIENT_ALPHA)
    .force("charge", forceManyBody().strength((node) => -340 * node.buoyancy).distanceMax(520))
    .force(
      "link",
      forceLink(links)
        .id((node) => node.id)
        .distance((link) => 165 - link.strength * 55)
        .strength((link) => link.strength * 0.22)
    )
    .force("centre", forceCenter().strength(0.35))
    .force("settleX", forceX(() => width / 2).strength(0.004))
    .force("settleY", forceY(() => height / 2).strength(0.004))
    .force("drift", drift)
    .on("tick", () => {
      clock += 1;
      ripples.step();
      draw();
    });

  let seeded = false;

  function seedPositions() {
    if (seeded) return;
    seeded = true;
    const ring = Math.min(width, height) * 0.36;
    nodes.forEach((node, index) => {
      const angle = (index / nodes.length) * Math.PI * 2;
      const wobble = 0.72 + ((index * 37) % 100) / 300;
      node.x = width / 2 + Math.cos(angle) * ring * wobble;
      node.y = height / 2 + Math.sin(angle) * ring * wobble;
      node.vx = 0;
      node.vy = 0;
    });
  }

  function seedBackdrop() {
    const span = 2.8;
    backdrop = Array.from({ length: BACKDROP_STARS }, (_, index) => {
      const random = (offset) => {
        const value = Math.sin(index * 12.9898 + offset * 78.233) * 43758.5453;
        return value - Math.floor(value);
      };
      return {
        x: (random(1) - 0.5) * width * span + width / 2,
        y: (random(2) - 0.5) * height * span + height / 2,
        size: 0.3 + random(3) * 0.95,
        base: 0.14 + random(4) * 0.4,
        speed: 0.004 + random(5) * 0.016,
        phase: random(6) * Math.PI * 2,
      };
    });
  }

  function size() {
    const rect = wrap.getBoundingClientRect();
    width = Math.max(rect.width, 320);
    height = Math.max(Math.min(window.innerHeight * 0.66, 680), 400);
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.height = `${height}px`;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    drift.bounds({ width, height });
    seedPositions();
    seedBackdrop();
    const centre = simulation.force("centre");
    if (centre) centre.x(width / 2).y(height / 2);
  }

  function toWorld(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left - transform.x) / transform.k,
      y: (event.clientY - rect.top - transform.y) / transform.k,
    };
  }

  function nodeAt(point) {
    let best = null;
    let bestDist = Infinity;
    const slack = 12 / transform.k;
    for (const node of nodes) {
      const dx = node.x - point.x;
      const dy = node.y - point.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= node.dot + slack && dist < bestDist) {
        best = node;
        bestDist = dist;
      }
    }
    return best;
  }

  function linkAt(point) {
    const slack = 7 / transform.k;
    let best = null;
    let bestDist = Infinity;
    for (const link of links) {
      if (!enabled.has(link.link_type)) continue;
      const ax = link.source.x;
      const ay = link.source.y;
      const bx = link.target.x;
      const by = link.target.y;
      const vx = bx - ax;
      const vy = by - ay;
      const lengthSq = vx * vx + vy * vy;
      if (lengthSq === 0) continue;
      let t = ((point.x - ax) * vx + (point.y - ay) * vy) / lengthSq;
      t = Math.max(0, Math.min(1, t));
      const dx = point.x - (ax + t * vx);
      const dy = point.y - (ay + t * vy);
      const dist = Math.hypot(dx, dy);
      if (dist <= slack && dist < bestDist) {
        best = link;
        bestDist = dist;
      }
    }
    return best;
  }

  function drawNebula() {
    if (!nebulaLayers.length) return;
    nebulaLayers.forEach((layer) => {
      const cx = (layer.x / 100) * width;
      const cy = (layer.y / 100) * height;
      const radius = (layer.r / 100) * Math.max(width, height);
      const cloud = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      cloud.addColorStop(0, `rgba(${layer.color},${layer.alpha})`);
      cloud.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = cloud;
      ctx.fillRect(0, 0, width, height);
    });
  }

  function drawBackdrop() {
    ctx.save();
    ctx.translate(transform.x * PARALLAX, transform.y * PARALLAX);
    const zoom = 1 + (transform.k - 1) * PARALLAX;
    ctx.scale(zoom, zoom);
    ctx.fillStyle = colors.starlight;
    backdrop.forEach((star) => {
      const twinkle = reduceMotion ? 1 : 0.7 + 0.3 * Math.sin(clock * star.speed + star.phase);
      ctx.globalAlpha = star.base * twinkle;
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  function drawRipples() {
    ripples.all.forEach((ripple) => {
      const radius = (1 - ripple.life) * 58 * ripple.energy + 4;
      ctx.beginPath();
      ctx.arc(ripple.x, ripple.y, radius, 0, Math.PI * 2);
      ctx.strokeStyle = colors.orange;
      ctx.globalAlpha = ripple.life * 0.22 * ripple.energy;
      ctx.lineWidth = 1 / transform.k;
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  function drawStar(node) {
    const isActive = hovered === node || node.grab;
    const core = node.dot * (isActive ? 1.35 : 1);
    const spread = glowStyle.scale ?? 1;
    const decay = node.decay || 0;
    const frozen = decay >= 0.85;
    const fade = Math.max(1 - decay * 0.65, 0.28);
    const unverified = node.is_verified === false;

    if (unverified) {
      ctx.save();
      ctx.setLineDash([core * 0.6, core * 0.5]);
      ctx.strokeStyle = colors.textDim;
      ctx.lineWidth = Math.max(1.4, core * 0.22) / transform.k;
      ctx.globalAlpha = isActive ? 0.9 : 0.65;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.globalAlpha = 1;
      if (node.is_custom) drawCustomCore(node, core * 0.55, 1);
      return;
    }

    const glow = core * (node.is_top_ten ? 5.4 : 3.8) * spread * fade;

    if (spread > 0) {
      const halo = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glow);
      halo.addColorStop(0, node.halo);
      halo.addColorStop(0.2, node.halo);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = (isActive ? 0.45 : node.is_top_ten ? 0.32 : 0.2) * fade;
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(node.x, node.y, glow, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    if (node.spiked) drawSpikes(node, core, fade);

    if (node.outline) {
      drawCustomCore(node, core, fade);
    } else {
      ctx.globalAlpha = fade;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core, 0, Math.PI * 2);
      ctx.fillStyle = node.color;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    if (node.is_top_ten || isActive) {
      ctx.globalAlpha = fade;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core * (glowStyle.core ?? 0.42), 0, Math.PI * 2);
      ctx.fillStyle = colors.starlight;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    if (frozen) {
      ctx.save();
      ctx.setLineDash([core * 0.35, core * 0.35]);
      ctx.strokeStyle = colors.text;
      ctx.lineWidth = Math.max(1, core * 0.16) / transform.k;
      ctx.globalAlpha = 0.75;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core * 1.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.globalAlpha = 1;
    }
  }

  function drawCustomCore(node, core, fade) {
    ctx.save();
    ctx.globalAlpha = fade;
    ctx.beginPath();
    ctx.arc(node.x, node.y, core, 0, Math.PI * 2);
    ctx.fillStyle = colors.bgSunk;
    ctx.fill();
    ctx.strokeStyle = node.outline || colors.starlight;
    ctx.lineWidth = Math.max(1.2, core * 0.28) / transform.k;
    ctx.stroke();
    ctx.restore();
  }

  function drawSpikes(node, core, fade) {
    const reach = Math.max(core * 2.6, 5 / transform.k);
    ctx.save();
    ctx.globalAlpha = 0.85 * fade;
    ctx.strokeStyle = node.color;
    ctx.lineWidth = Math.max(0.8, core * 0.2) / transform.k;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(node.x - reach, node.y);
    ctx.lineTo(node.x + reach, node.y);
    ctx.moveTo(node.x, node.y - reach);
    ctx.lineTo(node.x, node.y + reach);
    ctx.stroke();
    ctx.restore();
  }

  function draw() {
    ctx.save();
    ctx.clearRect(0, 0, width, height);
    drawNebula();
    drawBackdrop();

    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    links.forEach((link) => {
      if (!enabled.has(link.link_type)) return;
      const lit = link === hoveredLink || link === selectedLink;
      ctx.beginPath();
      ctx.moveTo(link.source.x, link.source.y);
      ctx.lineTo(link.target.x, link.target.y);
      ctx.strokeStyle = linkColor(link.link_type);
      const base = Math.min((0.1 + link.strength * 0.32) * (linkStyle.alpha ?? 1), 1);
      ctx.globalAlpha = lit ? Math.min(base + 0.55, 1) : base;
      ctx.lineWidth = ((0.5 + link.strength * 1.1) * (linkStyle.width ?? 1) * (lit ? 2.6 : 1)) / transform.k;
      // A type's own pattern always wins; the cosmetic dash only restyles solid types.
      const typeDash = LINK_STYLES[link.link_type]?.dash;
      const dash = typeDash || (lit ? null : linkStyle.dash);
      ctx.lineCap = typeDash ? "round" : "butt";
      if (dash) ctx.setLineDash(dash.map((value) => value / transform.k));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.lineCap = "butt";
    });
    ctx.globalAlpha = 1;

    drawRipples();

    nodes.forEach((node) => {
      const speed = Math.hypot(node.vx || 0, node.vy || 0);
      if (node.trail > 0) {
        node.trail = speed > TRAIL_SPEED ? Math.min(node.trail, 1) : node.trail - 0.06;
      }
      if (node.trail > 0 && speed > TRAIL_SPEED) {
        const reach = Math.min((speed - TRAIL_SPEED) * 0.5, 3.2);
        ctx.beginPath();
        ctx.moveTo(node.x - node.vx * reach, node.y - node.vy * reach);
        ctx.lineTo(node.x, node.y);
        ctx.strokeStyle = node.halo;
        ctx.globalAlpha = Math.min((speed - TRAIL_SPEED) / 26, 0.26) * node.trail;
        ctx.lineWidth = node.dot * 0.8;
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      drawStar(node);
    });

    nodes.forEach((node) => {
      const isActive = hovered === node || node.grab;
      if (!isActive && !node.is_top_ten && transform.k <= 1.35) return;
      ctx.font = `${11 / transform.k}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = isActive ? colors.text : colors.textDim;
      ctx.globalAlpha = isActive ? 1 : 0.72;
      ctx.textAlign = "center";
      const label = node.title.length > 30 ? `${node.title.slice(0, 29)}…` : node.title;
      ctx.fillText(label, node.x, node.y + node.dot + 14 / transform.k);
    });
    ctx.globalAlpha = 1;

    ctx.restore();
  }

  function wake(alpha = 0.22) {
    if (simulation.alpha() < alpha) simulation.alpha(alpha);
    simulation.restart();
  }

  function capture(pointerId) {
    activePointer = pointerId;
    try {
      canvas.setPointerCapture(pointerId);
    } catch {
      /* pointer already gone; the interaction still ends on the next pointerdown */
    }
  }

  // Exactly one drag or pan is live at a time, owned by activePointer. Ending it
  // releases that star's grab, so no star can be left pulled toward a stale point.
  function finishInteraction({ open = false } = {}) {
    const pointerId = activePointer;
    activePointer = null;
    if (pointerId !== null && canvas.hasPointerCapture?.(pointerId)) {
      canvas.releasePointerCapture(pointerId);
    }
    panning = null;
    if (dragging) {
      const node = dragging;
      dragging = null;
      const thrown = release(node, tracker.velocity(), DRIFT);
      const energy = Math.min(Math.hypot(thrown.x, thrown.y) / DRIFT.maxThrowSpeed, 1);
      node.trail = energy > 0.08 ? 1 : 0;
      if (energy > 0.08) ripples.spawn(node.x, node.y, energy);
      tracker.reset();
      wake(0.18);
      if (open && node.moved < 3) openDetail(node);
    }
    canvas.style.cursor = hovered ? "pointer" : "grab";
  }

  canvas.addEventListener("pointerdown", (event) => {
    // A second finger, or a new press after a pointerup that never arrived (the
    // mouse always reuses pointerId 1), must not strand the star already held.
    if (dragging || panning) finishInteraction();
    const point = toWorld(event);
    const found = nodeAt(point);
    if (found) {
      capture(event.pointerId);
      dragging = found;
      dragging.moved = 0;
      tracker.reset();
      tracker.push(point);
      grab(found, point);
      canvas.style.cursor = "grabbing";
      wake(0.12);
      return;
    }
    const edge = linkAt(point);
    if (edge) {
      selectedLink = edge;
      draw();
      openLinkDetail(edge);
      return;
    }
    capture(event.pointerId);
    panning = {
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
    };
    canvas.style.cursor = "grabbing";
  });

  canvas.addEventListener("pointermove", (event) => {
    if (activePointer !== null && event.pointerId !== activePointer) return;
    if (panning) {
      transform = {
        ...transform,
        x: panning.originX + (event.clientX - panning.startX),
        y: panning.originY + (event.clientY - panning.startY),
      };
      draw();
      return;
    }

    const point = toWorld(event);
    if (dragging) {
      dragging.moved += Math.hypot(point.x - dragging.grab.x, point.y - dragging.grab.y);
      moveGrab(dragging, point);
      tracker.push(point);
      wake(0.12);
      return;
    }

    const found = nodeAt(point);
    const edge = found ? null : linkAt(point);
    if (found !== hovered || edge !== hoveredLink) {
      hovered = found;
      hoveredLink = edge;
      canvas.style.cursor = found || edge ? "pointer" : "grab";
      draw();
    }
  });

  // Only the pointer that owns the live interaction can end it; a stray up or
  // cancel from another finger leaves the current drag alone.
  function endPointer(event) {
    if (activePointer === null || event.pointerId !== activePointer) return;
    finishInteraction({ open: event.type === "pointerup" });
  }

  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);
  canvas.addEventListener("lostpointercapture", endPointer);

  async function openLinkDetail(link) {
    const sourceId = link.source.id ?? link.source;
    const targetId = link.target.id ?? link.target;
    const sourceTitle = link.source.title ?? "";
    const targetTitle = link.target.title ?? "";
    showDrawer(
      el("div", { class: "stat-label" }, `${link.link_type.replace(/_/g, " / ")} link`),
      el("p", { class: "muted", style: "margin:6px 0 14px" }, `${sourceTitle} — ${targetTitle}`),
      skeletonBlock(3)
    );
    try {
      const summary = await api.linkSummary(sourceId, targetId, link.link_type);
      if (selectedLink !== link) return;
      showDrawer(linkSummaryPanel(summary));
    } catch (error) {
      if (selectedLink !== link) return;
      showDrawer(empty(error.detail || "Could not explain that connection."));
    }
  }

  function openDetail(node) {
    selectedLink = null;
    const statusPills = [
      el("span", { class: "pill mono" }, `difficulty ${Math.round(node.difficulty ?? 50)}`),
      el("span", { class: "pill" }, node.status.replace(/_/g, " ")),
      node.is_top_ten ? el("span", { class: "pill pill-accent" }, "top ten") : null,
      node.is_custom ? el("span", { class: "pill pill-custom" }, "custom") : null,
      node.is_verified === false ? el("span", { class: "pill pill-unverified" }, "needs verification") : null,
      node.decay >= 0.85 ? el("span", { class: "pill pill-frozen" }, "frozen · needs maintenance") : null,
    ];
    const actions = [
      el("a", { class: "btn btn-small", href: `/repertoire/${node.entry_id}`, "data-link": true }, "Open piece"),
    ];
    if (node.decay > 0 && node.is_verified !== false) {
      const runButton = el(
        "button",
        {
          type: "button",
          class: "btn btn-small btn-ghost",
          onclick: async () => {
            runButton.disabled = true;
            try {
              await api.maintenanceRun(node.entry_id);
              node.decay = 0;
              draw();
              openDetail(node);
            } catch {
              runButton.disabled = false;
            }
          },
        },
        "Log maintenance"
      );
      actions.push(runButton);
    }
    showDrawer(
      el("h2", { style: "margin:0 0 4px" }, node.title),
      el(
        "p",
        { class: "muted", style: "margin:0 0 12px" },
        [node.composer, node.era, node.genre].filter(Boolean).join(" · ")
      ),
      el("div", { class: "row" }, ...statusPills),
      el("div", { class: "row", style: "margin-top:14px" }, ...actions)
    );
  }

  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const factor = event.deltaY < 0 ? 1.12 : 0.89;
      const next = Math.min(Math.max(transform.k * factor, 0.3), 6);
      transform = {
        k: next,
        x: px - ((px - transform.x) / transform.k) * next,
        y: py - ((py - transform.y) / transform.k) * next,
      };
      draw();
    },
    { passive: false }
  );

  function recentre() {
    size();
    wake(0.5);
  }

  const onResize = () => recentre();
  window.addEventListener("resize", onResize);

  const onBlur = () => {
    if (dragging || panning) finishInteraction();
  };
  window.addEventListener("blur", onBlur);

  const onVisibility = () => {
    if (document.hidden && running) {
      simulation.stop();
      running = false;
    } else if (!document.hidden && !running) {
      running = true;
      simulation.restart();
    }
  };
  document.addEventListener("visibilitychange", onVisibility);

  canvas.style.cursor = "grab";
  recentre();

  return () => {
    simulation.stop();
    window.removeEventListener("resize", onResize);
    window.removeEventListener("blur", onBlur);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
