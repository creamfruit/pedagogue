import { api } from "../api/client.js";
import { linkSummaryPanel } from "../components/overview.js";
import { el, empty, skeletonBlock } from "../lib/dom.js";
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

const LINK_COLORS = {
  composer: "#f0a13c",
  technique: "#e8734a",
  era_genre: "#e05a78",
};

const LINK_LABELS = {
  composer: "composer",
  technique: "technique",
  era_genre: "era / genre",
};

const ERA_COLORS = {
  Baroque: "#ffe3b0",
  Classical: "#ffd08a",
  Romantic: "#f0a13c",
  Impressionist: "#e8865a",
  Modern: "#e0687e",
  Contemporary: "#d9718f",
};

const STAR_DEFAULT = "#cdd3dc";
const CUSTOM_COLOR = "#b48af0";
const UNVERIFIED_COLOR = "#8a8f99";
const AMBIENT_ALPHA = 0.015;
const BACKDROP_STARS = 240;
const PARALLAX = 0.3;
const TRAIL_SPEED = 2.4;

export async function constellationView(outlet) {
  const legendHost = el("div", { class: "legend" });
  const canvas = el("canvas");
  const detail = el(
    "div",
    { class: "panel", style: "margin-top:16px" },
    el("p", { class: "faint", style: "margin:0" }, "Tap a star to read the piece, or tap a connector to read why the two are linked. Drag a star to send it drifting.")
  );
  const wrap = el("div", { class: "constellation-wrap" }, legendHost, canvas);
  const loading = el("div", {}, skeletonBlock(4));

  outlet.append(
    el(
      "div",
      { class: "row", style: "justify-content:space-between;margin-bottom:16px" },
      el("h1", { style: "margin:0" }, "Constellation"),
      el(
        "span",
        { class: "faint mono", style: "font-size:12px" },
        "drag the sky to pan · scroll to zoom · tap a connector to read it"
      )
    ),
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
  outlet.append(wrap, detail);

  if (!graph.nodes.length) {
    wrap.replaceChildren(empty("Add pieces to your repertoire and they will appear here."));
    return;
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const enabled = new Set(graph.link_types);

  Object.keys(LINK_COLORS).forEach((type) => {
    if (!graph.link_types.includes(type)) return;
    const button = el(
      "button",
      {
        type: "button",
        "aria-pressed": "true",
        style: `color:${LINK_COLORS[type]}`,
        onclick: () => {
          if (enabled.has(type)) enabled.delete(type);
          else enabled.add(type);
          button.setAttribute("aria-pressed", enabled.has(type) ? "true" : "false");
          draw();
        },
      },
      el("span", { class: "swatch" }),
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

  function starColor(node) {
    const difficulty = node.difficulty ?? 50;
    if (node.is_custom) return CUSTOM_COLOR;
    if (starStyle.mode === "fixed" && starStyle.color) return starStyle.color;
    if (starStyle.mode === "difficulty") {
      if (difficulty >= 90) return "#ffffff";
      if (difficulty >= 75) return "#ffe3b0";
      if (difficulty >= 55) return "#f0a13c";
      return "#9fd4f0";
    }
    return ERA_COLORS[node.era] || STAR_DEFAULT;
  }

  const nodes = graph.nodes.map((node) => {
    const difficulty = (node.difficulty ?? 50) / 10;
    return {
      ...node,
      dot: 1.3 + difficulty * 0.56,
      radius: 7 + difficulty * 1.1,
      color: starColor(node),
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
    ctx.fillStyle = "#dfe4ec";
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
      ctx.strokeStyle = "rgba(240,161,60,1)";
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
      ctx.strokeStyle = UNVERIFIED_COLOR;
      ctx.lineWidth = Math.max(1.4, core * 0.22) / transform.k;
      ctx.globalAlpha = isActive ? 0.9 : 0.65;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.globalAlpha = 1;
      if (node.is_custom) drawCustomRing(node, core);
      return;
    }

    const glow = core * (node.is_top_ten ? 5.4 : 3.8) * spread * fade;

    if (spread > 0) {
      const halo = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glow);
      halo.addColorStop(0, node.color);
      halo.addColorStop(0.2, node.color);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = (isActive ? 0.45 : node.is_top_ten ? 0.32 : 0.2) * fade;
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(node.x, node.y, glow, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    ctx.globalAlpha = fade;
    ctx.beginPath();
    ctx.arc(node.x, node.y, core, 0, Math.PI * 2);
    ctx.fillStyle = node.color;
    ctx.fill();
    ctx.globalAlpha = 1;

    if (node.is_top_ten || isActive) {
      ctx.globalAlpha = fade;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core * (glowStyle.core ?? 0.42), 0, Math.PI * 2);
      ctx.fillStyle = "#fff6e6";
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    if (frozen) {
      ctx.save();
      ctx.setLineDash([core * 0.35, core * 0.35]);
      ctx.strokeStyle = "#9fd4f0";
      ctx.lineWidth = Math.max(1, core * 0.16) / transform.k;
      ctx.globalAlpha = 0.75;
      ctx.beginPath();
      ctx.arc(node.x, node.y, core * 1.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.globalAlpha = 1;
    }

    if (node.is_custom) drawCustomRing(node, core);
  }

  function drawCustomRing(node, core) {
    ctx.save();
    ctx.setLineDash([core * 0.3, core * 0.4]);
    ctx.strokeStyle = CUSTOM_COLOR;
    ctx.lineWidth = Math.max(1, core * 0.14) / transform.k;
    ctx.globalAlpha = 0.8;
    ctx.beginPath();
    ctx.arc(node.x, node.y, core * 1.85, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    ctx.globalAlpha = 1;
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
      ctx.strokeStyle = LINK_COLORS[link.link_type] || "#2b2e33";
      const base = Math.min((0.1 + link.strength * 0.32) * (linkStyle.alpha ?? 1), 1);
      ctx.globalAlpha = lit ? Math.min(base + 0.55, 1) : base;
      ctx.lineWidth = ((0.5 + link.strength * 1.1) * (linkStyle.width ?? 1) * (lit ? 2.6 : 1)) / transform.k;
      if (linkStyle.dash && !lit) ctx.setLineDash(linkStyle.dash.map((value) => value / transform.k));
      ctx.stroke();
      ctx.setLineDash([]);
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
        ctx.strokeStyle = node.color;
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
      ctx.fillStyle = isActive ? "#e8e4dd" : "rgba(160,156,148,0.72)";
      ctx.textAlign = "center";
      const label = node.title.length > 30 ? `${node.title.slice(0, 29)}…` : node.title;
      ctx.fillText(label, node.x, node.y + node.dot + 14 / transform.k);
    });

    ctx.restore();
  }

  function wake(alpha = 0.22) {
    if (simulation.alpha() < alpha) simulation.alpha(alpha);
    simulation.restart();
  }

  canvas.addEventListener("pointerdown", (event) => {
    const point = toWorld(event);
    const found = nodeAt(point);
    canvas.setPointerCapture(event.pointerId);
    if (found) {
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
      canvas.releasePointerCapture(event.pointerId);
      selectedLink = edge;
      draw();
      openLinkDetail(edge);
      return;
    }
    panning = {
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
    };
    canvas.style.cursor = "grabbing";
  });

  canvas.addEventListener("pointermove", (event) => {
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

  function endPointer(event) {
    if (event && canvas.hasPointerCapture?.(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }

    if (panning) {
      panning = null;
      canvas.style.cursor = hovered ? "pointer" : "grab";
      return;
    }

    if (!dragging) return;
    const node = dragging;
    const thrown = release(node, tracker.velocity(), DRIFT);
    const energy = Math.min(Math.hypot(thrown.x, thrown.y) / DRIFT.maxThrowSpeed, 1);
    node.trail = energy > 0.08 ? 1 : 0;
    if (energy > 0.08) ripples.spawn(node.x, node.y, energy);
    dragging = null;
    tracker.reset();
    canvas.style.cursor = hovered ? "pointer" : "grab";
    wake(0.18);
    if (node.moved < 3) openDetail(node);
  }

  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);

  async function openLinkDetail(link) {
    const sourceId = link.source.id ?? link.source;
    const targetId = link.target.id ?? link.target;
    const sourceTitle = link.source.title ?? "";
    const targetTitle = link.target.title ?? "";
    detail.replaceChildren(
      el("div", { class: "stat-label" }, `${link.link_type.replace(/_/g, " / ")} link`),
      el("p", { class: "muted", style: "margin:6px 0 14px" }, `${sourceTitle} — ${targetTitle}`),
      skeletonBlock(3)
    );
    try {
      const summary = await api.linkSummary(sourceId, targetId, link.link_type);
      if (selectedLink !== link) return;
      detail.replaceChildren(linkSummaryPanel(summary));
      detail.scrollIntoView({ behavior: "smooth", block: "end" });
    } catch (error) {
      if (selectedLink !== link) return;
      detail.replaceChildren(empty(error.detail || "Could not explain that connection."));
    }
  }

  function openDetail(node) {
    selectedLink = null;
    const statusPills = [
      el("span", { class: "pill mono" }, `difficulty ${Math.round(node.difficulty ?? 50)}`),
      el("span", { class: "pill" }, node.status.replace(/_/g, " ")),
      node.is_top_ten ? el("span", { class: "pill pill-accent" }, "top ten") : null,
      node.is_custom ? el("span", { class: "pill", style: `color:${CUSTOM_COLOR}` }, "custom") : null,
      node.is_verified === false ? el("span", { class: "pill", style: `color:${UNVERIFIED_COLOR}` }, "needs verification") : null,
      node.decay >= 0.85 ? el("span", { class: "pill", style: "color:#9fd4f0" }, "frozen · needs maintenance") : null,
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
    detail.replaceChildren(
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
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
