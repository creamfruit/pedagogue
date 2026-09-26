import { el, reveal } from "./dom.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const LINE_COLOR = "rgba(var(--orange-rgb), 0.8)";
const MARGIN = { top: 16, right: 44, bottom: 28, left: 34 };

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function starPath(cx, cy, outer) {
  const inner = outer * 0.45;
  const points = [];
  for (let i = 0; i < 10; i += 1) {
    const radius = i % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    points.push(`${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`);
  }
  return `M${points.join("L")}Z`;
}

function shortDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function domain(values) {
  const present = values.filter((value) => value !== null && value !== undefined);
  if (!present.length) return [0, 100];
  const low = Math.max(0, Math.floor((Math.min(...present) - 8) / 10) * 10);
  const high = Math.min(100, Math.ceil((Math.max(...present) + 6) / 10) * 10);
  return high - low < 20 ? [Math.max(0, high - 20), high] : [low, high];
}

function legend() {
  const key = (swatch, label) => el("span", { class: "chart-key" }, swatch, label);
  return el(
    "div",
    { class: "chart-legend", "aria-hidden": "true" },
    key(el("span", { class: "chart-key-line" }), "4-week average"),
    key(el("span", { class: "chart-key-dot" }), "weekly average"),
    key(el("span", { class: "chart-key-star" }, "✦"), "piece learnt")
  );
}

function table(series) {
  return el(
    "table",
    { class: "chart-table" },
    el(
      "thead",
      {},
      el("tr", {}, ...["Week of", "Weekly average", "4-week average", "Minutes", "Learnt"].map((label) => el("th", { scope: "col" }, label)))
    ),
    el(
      "tbody",
      {},
      ...series.weeks
        .filter((week) => week.minutes || week.learned.length)
        .map((week) =>
          el(
            "tr",
            {},
            el("td", {}, shortDate(week.start)),
            el("td", { class: "mono" }, week.practised_avg ?? "—"),
            el("td", { class: "mono" }, week.rolling_avg ?? "—"),
            el("td", { class: "mono" }, week.minutes),
            el("td", {}, week.learned.map((item) => `${item.title} (${item.difficulty})`).join(", ") || "—")
          )
        )
    )
  );
}

export function growthChart(series, { height = 240 } = {}) {
  const weeks = series.weeks;
  const host = el("div", { class: "growth-chart" });
  const plot = el("div", { class: "chart-plot" });
  const tooltip = el("div", { class: "chart-tooltip", role: "status", hidden: true });
  const control = reveal("Show as a table", () => table(series));
  host.append(legend(), plot, control.button, control.region);
  plot.append(tooltip);

  const values = weeks.flatMap((week) => [week.practised_avg, week.rolling_avg, ...week.learned.map((item) => item.difficulty)]);
  const [low, high] = domain(values);

  function render() {
    const width = Math.max(plot.clientWidth || 640, 280);
    const innerWidth = width - MARGIN.left - MARGIN.right;
    const innerHeight = height - MARGIN.top - MARGIN.bottom;
    const x = (index) => MARGIN.left + (weeks.length === 1 ? innerWidth / 2 : (index / (weeks.length - 1)) * innerWidth);
    const y = (value) => MARGIN.top + innerHeight - ((value - low) / (high - low)) * innerHeight;
    const root = svg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      width,
      height,
      role: "img",
      "aria-label": `Average difficulty practised per week over the last ${weeks.length} weeks`,
    });

    for (let tick = low; tick <= high; tick += (high - low) / 4) {
      const ty = y(tick);
      root.append(
        svg("line", { x1: MARGIN.left, x2: width - MARGIN.right, y1: ty, y2: ty, stroke: "var(--line)", "stroke-width": 1 }),
        Object.assign(svg("text", { x: MARGIN.left - 8, y: ty + 4, "text-anchor": "end", class: "chart-axis" }), { textContent: Math.round(tick) })
      );
    }
    const labelEvery = Math.ceil(weeks.length / 6);
    weeks.forEach((week, index) => {
      if (index % labelEvery !== 0 && index !== weeks.length - 1) return;
      const label = svg("text", { x: x(index), y: height - 8, "text-anchor": "middle", class: "chart-axis" });
      label.textContent = shortDate(week.start);
      root.append(label);
    });

    const crosshair = svg("line", { y1: MARGIN.top, y2: MARGIN.top + innerHeight, stroke: "var(--line-bright)", "stroke-width": 1, visibility: "hidden" });
    root.append(crosshair);

    let path = "";
    let pen = false;
    weeks.forEach((week, index) => {
      if (week.rolling_avg === null) {
        pen = false;
        return;
      }
      path += `${pen ? "L" : "M"}${x(index).toFixed(1)},${y(week.rolling_avg).toFixed(1)}`;
      pen = true;
    });
    if (path) {
      root.append(svg("path", { d: path, fill: "none", stroke: LINE_COLOR, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }

    weeks.forEach((week, index) => {
      if (week.practised_avg === null) return;
      root.append(svg("circle", { cx: x(index), cy: y(week.practised_avg), r: 4, fill: "var(--text-faint)", stroke: "var(--bg-panel)", "stroke-width": 2 }));
    });
    weeks.forEach((week, index) => {
      week.learned.forEach((item, offset) => {
        root.append(
          svg("path", { d: starPath(x(index) + offset * 6, y(item.difficulty), 7), fill: "var(--starlight)", stroke: "var(--bg-panel)", "stroke-width": 2 })
        );
      });
    });

    let lastIndex = -1;
    weeks.forEach((week, index) => {
      if (week.rolling_avg !== null) lastIndex = index;
    });
    if (lastIndex >= 0) {
      const end = svg("text", { x: x(lastIndex) + 8, y: y(weeks[lastIndex].rolling_avg) + 4, class: "chart-end-label" });
      end.textContent = Math.round(weeks[lastIndex].rolling_avg);
      root.append(end);
    }

    const hit = svg("rect", { x: MARGIN.left, y: MARGIN.top, width: innerWidth, height: innerHeight, fill: "transparent" });
    root.append(hit);
    function show(clientX) {
      const bounds = root.getBoundingClientRect();
      const relative = ((clientX - bounds.left) / bounds.width) * width;
      const index = Math.max(0, Math.min(weeks.length - 1, Math.round(((relative - MARGIN.left) / innerWidth) * (weeks.length - 1))));
      const week = weeks[index];
      crosshair.setAttribute("x1", x(index));
      crosshair.setAttribute("x2", x(index));
      crosshair.setAttribute("visibility", "visible");
      tooltip.hidden = false;
      tooltip.replaceChildren(
        el("strong", {}, `Week of ${shortDate(week.start)}`),
        el("div", {}, `4-week average: ${week.rolling_avg ?? "—"}`),
        el("div", {}, `Weekly average: ${week.practised_avg ?? "no practice"}`),
        el("div", { class: "faint" }, `${week.minutes} minutes`),
        ...week.learned.map((item) => el("div", {}, `✦ ${item.title} (${item.difficulty})`))
      );
      const left = (x(index) / width) * bounds.width;
      tooltip.style.left = `${Math.min(Math.max(left + 12, 0), bounds.width - 200)}px`;
    }
    hit.addEventListener("pointermove", (event) => show(event.clientX));
    hit.addEventListener("pointerleave", () => {
      crosshair.setAttribute("visibility", "hidden");
      tooltip.hidden = true;
    });
    plot.querySelector("svg")?.remove();
    plot.prepend(root);
  }

  requestAnimationFrame(render);
  const observer = new ResizeObserver(() => {
    if (!host.isConnected) {
      observer.disconnect();
      return;
    }
    render();
  });
  observer.observe(plot);
  return host;
}
