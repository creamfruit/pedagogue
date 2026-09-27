import { api } from "../api/client.js";
import { el, empty, reveal, sectionBlock, skeletonBlock } from "../lib/dom.js";
import { STATUS_LABEL } from "../lib/entries.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const ROW = 26;
const TOP = 34;
const LEFT = 18;
const LABEL_ROOM = 250;
const MIN_WIDTH = 760;
const TITLE_LIMIT = 34;

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  });
  children.filter(Boolean).forEach((child) => node.append(child));
  return node;
}

function surname(name) {
  return name ? name.split(" ").pop() : "";
}

function shortTitle(title) {
  return title.length > TITLE_LIMIT ? `${title.slice(0, TITLE_LIMIT - 1)}…` : title;
}

function yearLabel(node) {
  return node.year_estimated ? `c. ${node.year}` : String(node.year);
}

export function layoutTree(nodes) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map(nodes.map((node) => [node.id, []]));
  const roots = [];
  nodes.forEach((node) => {
    const parent = node.link?.parent;
    if (parent && children.has(parent)) children.get(parent).push(node);
    else roots.push(node);
  });
  const byYear = (a, b) => a.year - b.year || a.title.localeCompare(b.title);
  const order = [];
  const depth = new Map();
  const visit = (node, level) => {
    depth.set(node.id, level);
    order.push(node);
    children.get(node.id).sort(byYear).forEach((child) => visit(child, level + 1));
  };
  roots.sort(byYear).forEach((root) => visit(root, 0));
  return { byId, children, roots, order, row: new Map(order.map((node, index) => [node.id, index])), depth };
}

export function lineageOf(id, layout) {
  const ids = new Set([id]);
  let cursor = layout.byId.get(id);
  while (cursor?.link?.parent && layout.byId.has(cursor.link.parent)) {
    ids.add(cursor.link.parent);
    cursor = layout.byId.get(cursor.link.parent);
  }
  const stack = [...(layout.children.get(id) || [])];
  while (stack.length) {
    const node = stack.pop();
    ids.add(node.id);
    stack.push(...(layout.children.get(node.id) || []));
  }
  return ids;
}

function ancestry(id, layout) {
  const line = [];
  let cursor = layout.byId.get(id);
  while (cursor) {
    line.unshift(cursor);
    cursor = cursor.link?.parent ? layout.byId.get(cursor.link.parent) : null;
  }
  return line;
}

function why(link) {
  const bits = [];
  if (link.shared_techniques.length) bits.push(`shares ${link.shared_techniques.map((name) => name.toLowerCase()).join(", ")}`);
  if (link.reasons.length) bits.push(link.reasons.join(" · "));
  return bits.join("; ");
}

function listView(layout, onPick) {
  const branch = (node) =>
    el(
      "li",
      {},
      el(
        "button",
        { type: "button", class: `tree-list-item${node.in_repertoire ? " is-yours" : ""}`, onclick: () => onPick(node.id) },
        node.title,
        el("span", { class: "faint" }, ` · ${surname(node.composer)}, ${yearLabel(node)}`)
      ),
      layout.children.get(node.id).length ? el("ul", {}, ...layout.children.get(node.id).map(branch)) : null
    );
  return el("ul", { class: "tree-list" }, ...layout.roots.map(branch));
}

export async function familyTreeView(outlet) {
  const host = el("div", {}, skeletonBlock(6));
  outlet.append(host);
  let tree;
  try {
    tree = await api.familyTree();
  } catch (error) {
    host.replaceChildren(empty(error.detail || "Could not load the family tree."));
    return;
  }
  if (!tree.nodes.length) {
    host.replaceChildren(empty("The catalogue has no dated pieces with technique data yet."));
    return;
  }

  const layout = layoutTree(tree.nodes);
  const years = tree.nodes.map((node) => node.year);
  const low = Math.floor((Math.min(...years) - 5) / 25) * 25;
  const high = Math.ceil((Math.max(...years) + 5) / 25) * 25;
  const scroller = el("div", { class: "tree-scroll" });
  const tooltip = el("div", { class: "chart-tooltip", hidden: true, role: "presentation" });
  const plot = el("div", { class: "tree-plot" }, scroller, tooltip);
  const panel = el("div", { class: "tree-detail", "aria-live": "polite" });
  const yours = tree.nodes.filter((node) => node.in_repertoire).sort((a, b) => b.year - a.year);
  let focus = yours[0]?.id ?? null;

  function draw() {
    const width = Math.max(MIN_WIDTH, scroller.clientWidth || MIN_WIDTH);
    const height = TOP + layout.order.length * ROW + 10;
    const span = width - LEFT - LABEL_ROOM;
    const x = (year) => LEFT + ((year - low) / (high - low)) * span;
    const y = (id) => TOP + layout.row.get(id) * ROW + ROW / 2;
    const lit = focus ? lineageOf(focus, layout) : null;

    const grid = svg("g", { class: "tree-grid", "aria-hidden": "true" });
    for (let year = low; year <= high; year += 25) {
      const major = year % 50 === 0;
      grid.append(svg("line", { x1: x(year), x2: x(year), y1: TOP - 8, y2: height, class: major ? "tree-grid-major" : "tree-grid-minor" }));
      if (major) grid.append(svg("text", { x: x(year), y: 14, "text-anchor": "middle", class: "chart-axis" }, document.createTextNode(String(year))));
    }

    const edges = svg("g", { class: "tree-edges", "aria-hidden": "true" });
    layout.order.forEach((node) => {
      if (!node.link || !layout.byId.has(node.link.parent)) return;
      const parent = layout.byId.get(node.link.parent);
      const px = x(parent.year);
      const py = y(parent.id);
      const cx = x(node.year);
      const cy = y(node.id);
      const bend = Math.min(6, Math.abs(cx - px));
      const d = bend > 0 ? `M${px},${py} V${cy - bend} Q${px},${cy} ${px + bend},${cy} H${cx}` : `M${px},${py} V${cy} H${cx}`;
      const on = lit && lit.has(node.id) && lit.has(parent.id);
      edges.append(svg("path", { d, class: `tree-edge${on ? " is-lit" : ""}${lit && !on ? " is-dim" : ""}` }));
    });

    const marks = svg("g", { class: "tree-nodes" });
    layout.order.forEach((node) => {
      const cx = x(node.year);
      const cy = y(node.id);
      const dim = lit && !lit.has(node.id);
      const label = `${node.title}, ${node.composer || "unknown composer"}, ${yearLabel(node)}${node.in_repertoire ? ", in your repertoire" : ""}`;
      const group = svg(
        "g",
        {
          class: `tree-node${node.in_repertoire ? " is-yours" : ""}${node.id === focus ? " is-focus" : ""}${dim ? " is-dim" : ""}`,
          tabindex: "0",
          role: "button",
          "aria-label": label,
          "aria-pressed": node.id === focus ? "true" : "false",
        },
        svg("rect", { x: cx - 10, y: cy - ROW / 2, width: LABEL_ROOM, height: ROW, class: "tree-hit" }),
        node.id === focus ? svg("circle", { cx, cy, r: 9, class: "tree-ring" }) : null,
        svg("circle", { cx, cy, r: 4.5, class: "tree-dot" }),
        svg(
          "text",
          { x: cx + 10, y: cy + 4, class: "tree-label" },
          document.createTextNode(shortTitle(node.title)),
          svg("tspan", { class: "tree-label-meta" }, document.createTextNode(`  ${surname(node.composer)}`))
        )
      );
      group.addEventListener("click", () => pick(node.id === focus ? null : node.id));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          pick(node.id === focus ? null : node.id);
        }
      });
      group.addEventListener("pointerenter", () => showTip(node, cx, cy));
      group.addEventListener("pointerleave", () => (tooltip.hidden = true));
      group.addEventListener("focus", () => showTip(node, cx, cy));
      group.addEventListener("blur", () => (tooltip.hidden = true));
      marks.append(group);
    });

    scroller.replaceChildren(
      svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "Family tree of pieces, earliest on the left" }, grid, edges, marks)
    );
  }

  function showTip(node, cx, cy) {
    const parent = node.link ? layout.byId.get(node.link.parent) : null;
    tooltip.replaceChildren(
      el("div", { style: "font-weight:500" }, node.title),
      el("div", { class: "faint" }, `${node.composer || "Unknown"} · ${yearLabel(node)}`),
      el("div", { class: "muted" }, parent ? `From ${shortTitle(parent.title)} · ${Math.round(node.link.affinity * 100)}% alike` : "Starts a line")
    );
    tooltip.hidden = false;
    const left = Math.min(cx + 14 - scroller.scrollLeft, scroller.clientWidth - 230);
    tooltip.style.left = `${Math.max(4, left)}px`;
    tooltip.style.top = `${cy + 14}px`;
  }

  function jump(id) {
    return el(
      "button",
      { type: "button", class: "link-btn", onclick: () => pick(id, { scroll: true }) },
      layout.byId.get(id).title
    );
  }

  function describe() {
    if (!focus) {
      panel.replaceChildren(el("p", { class: "faint", style: "margin:0" }, "Pick a piece to trace its line back to the start and forward to what came after."));
      return;
    }
    const node = layout.byId.get(focus);
    const line = ancestry(focus, layout);
    const kids = layout.children.get(focus);
    panel.replaceChildren(
      el("h3", { class: "section-title", style: "margin:0" }, node.title),
      el(
        "p",
        { class: "faint", style: "margin:4px 0 var(--space-3);font-size:13px" },
        [node.composer, yearLabel(node), node.era, node.genre].filter(Boolean).join(" · "),
        node.in_repertoire ? el("span", { class: "tree-yours-tag" }, ` · yours, ${STATUS_LABEL[node.status] || node.status}`) : null
      ),
      node.link
        ? el(
            "p",
            { style: "margin:0 0 var(--space-3)" },
            "Descends from ",
            jump(node.link.parent),
            el("span", { class: "muted" }, ` (${Math.round(node.link.affinity * 100)}% alike: ${why(node.link)}).`)
          )
        : el("p", { class: "muted", style: "margin:0 0 var(--space-3)" }, "Starts its own line: nothing earlier in the catalogue is close enough."),
      line.length > 2
        ? el(
            "p",
            { class: "faint", style: "margin:0 0 var(--space-3);font-size:12.5px" },
            "Line: ",
            ...line.flatMap((step, index) => [index ? " → " : "", step.id === focus ? el("strong", { style: "font-weight:500" }, shortTitle(step.title)) : jump(step.id)])
          )
        : null,
      kids.length
        ? el("div", {}, el("div", { class: "stat-label" }, "Led to"), el("ul", { class: "flat-list" }, ...kids.map((child) => el("li", { class: "flat-row" }, jump(child.id), el("span", { class: "faint mono", style: "font-size:12px" }, `${Math.round(child.link.affinity * 100)}%`)))))
        : el("p", { class: "faint", style: "margin:0;font-size:12.5px" }, "Nothing later in the catalogue descends from it yet.")
    );
  }

  function pick(id, { scroll = false } = {}) {
    focus = id;
    draw();
    describe();
    if (scroll && id) {
      const target = scroller.querySelector(".tree-node.is-focus");
      target?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    }
  }

  const list = reveal("Read the tree as a list", () => listView(layout, (id) => pick(id, { scroll: true })));
  host.replaceChildren(
    el(
      "p",
      { class: "muted", style: "margin:0 0 var(--space-3);font-size:13.5px;max-width:72ch" },
      `Every dated piece in the catalogue, earliest on the left. Each one hangs from the earlier piece it most resembles: ${Math.round(tree.weights.technique * 100)}% shared technique (the same measure the constellation's technique lines use), ${Math.round(tree.weights.era_genre * 100)}% era and genre. It's a map of resemblance, not documented influence.`
    ),
    el(
      "div",
      { class: "chart-legend", "aria-hidden": "true" },
      el("span", { class: "chart-key" }, el("span", { class: "tree-key tree-key-yours" }), "in your repertoire"),
      el("span", { class: "chart-key" }, el("span", { class: "tree-key" }), "rest of the catalogue"),
      el("span", { class: "chart-key" }, el("span", { class: "chart-key-line tree-key-lit" }), "selected line")
    ),
    plot,
    sectionBlock("Selected piece", {}, panel),
    list.button,
    list.region
  );
  draw();
  describe();
  const onResize = () => draw();
  window.addEventListener("resize", onResize);
  if (focus) scroller.querySelector(".tree-node.is-focus")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  return () => window.removeEventListener("resize", onResize);
}
