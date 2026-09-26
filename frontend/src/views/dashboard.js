import { api } from "../api/client.js";
import { el, empty, skeletonBlock, toneForSeverity } from "../lib/dom.js";
import { store } from "../lib/store.js";

export async function dashboardView(outlet) {
  const heading = el(
    "div",
    { class: "page-head" },
    el("div", {}, el("h1", { style: "margin:0" }, `Good to see you, ${store.user?.display_name || "pianist"}`), el("p", { class: "muted", style: "margin:4px 0 0" }, "Here is where your hands are this week.")),
    el("a", { class: "btn", href: "/practice", "data-link": true }, "Start practising")
  );

  const statsRow = el("section", { class: "panel summary-bar summary-bar-numbers", "aria-label": "Repertoire at a glance" }, skeletonBlock(2));
  const loadTitle = () => el("div", { class: "section-head" }, el("h2", { class: "section-title" }, "Load guard"));
  const activeTitle = () => el("div", { class: "section-head" }, el("h2", { class: "section-title" }, "In progress"));
  const loadPanel = el("section", { class: "panel" }, loadTitle(), skeletonBlock(2));
  const activePanel = el("section", { class: "panel" }, activeTitle(), skeletonBlock(3));

  outlet.append(heading, statsRow, el("div", { class: "grid", style: "margin-top:var(--space-5)" }, loadPanel, activePanel));

  const [stats, load, active] = await Promise.allSettled([
    api.repertoireStats(),
    api.load(),
    api.repertoire({ status: "learning", limit: 5 }),
  ]);

  statsRow.replaceChildren();
  if (stats.status === "fulfilled") {
    const s = stats.value;
    const cell = (label, value) =>
      el("div", { class: "summary-cell" }, el("div", { class: "stat-label" }, label), el("div", { class: "stat" }, value));
    const average = s.average_difficulty != null && Number.isFinite(Number(s.average_difficulty))
      ? (Math.round(Number(s.average_difficulty) * 10) / 10).toFixed(1)
      : "--";
    statsRow.append(
      cell("Pieces", s.total),
      cell("Active", s.active),
      cell("Average difficulty", average),
      cell("Submissions", s.submissions)
    );
  } else {
    statsRow.append(empty("Could not load your stats."));
  }

  loadPanel.replaceChildren(loadTitle());
  if (load.status === "fulfilled") {
    const l = load.value;
    const pct = l.threshold ? Math.min((l.load_total / l.threshold) * 100, 100) : 0;
    loadPanel.append(
      el(
        "div",
        { class: "row", style: "justify-content:space-between" },
        el("span", { class: "stat", style: "font-size:24px" }, Math.round(l.load_total)),
        el("span", { class: `pill ${toneForSeverity(l.severity)}` }, l.severity)
      ),
      el("div", { class: "bar", style: "margin:12px 0 0" }, el("span", { style: `width:${pct}%` })),
      el(
        "div",
        { class: "bar-ticks", style: "margin-bottom:10px" },
        el("span", {}, "0"),
        el("span", {}, Math.round(l.threshold / 2)),
        el("span", {}, Math.round(l.threshold))
      ),
      el("p", { class: "muted", style: "margin:0" }, l.message || ""),
      el("p", { class: "faint mono", style: "margin:8px 0 0;font-size:12px" }, `${l.minutes_this_week} minutes logged this week`)
    );
    if (l.stretch_warnings?.length) {
      loadPanel.append(
        el("h3", { style: "margin-top:18px" }, "Hand span"),
        el(
          "ul",
          { class: "list" },
          ...l.stretch_warnings.map((w) =>
            el("li", { class: "list-item" }, el("span", {}, w.title), el("span", { class: "pill pill-warn" }, `${w.required_cm}cm`))
          )
        )
      );
    }
  } else {
    loadPanel.append(empty("No load data yet. Log a practice session."));
  }

  activePanel.replaceChildren(activeTitle());
  if (active.status === "fulfilled" && active.value.items.length) {
    activePanel.append(
      el(
        "ul",
        { class: "flat-list" },
        ...active.value.items.map((entry) => {
          const progress = entry.current_tempo_bpm && entry.target_tempo_bpm
            ? Math.round((entry.current_tempo_bpm / entry.target_tempo_bpm) * 100)
            : null;
          return el(
            "li",
            { class: "flat-row" },
            el(
              "div",
              {},
              el("a", { href: `/repertoire/${entry.id}`, "data-link": true, style: "color:inherit;font-weight:500" }, entry.piece.title),
              entry.piece.composer?.name ? el("div", { class: "faint", style: "font-size:12.5px" }, entry.piece.composer.name) : null
            ),
            el(
              "span",
              { class: progress != null ? "mono" : "entry-status", title: progress != null ? "Current tempo as a share of the target" : null },
              progress != null ? `${progress}% of tempo` : entry.status.replace(/_/g, " ")
            )
          );
        })
      )
    );
  } else {
    activePanel.append(empty("Nothing in progress.", el("a", { class: "btn", href: "/repertoire", "data-link": true }, "Add a piece")));
  }
}
