import { api } from "../api/client.js";
import { el, empty, sectionBlock, skeletonBlock, toneForSeverity } from "../lib/dom.js";
import { daysSince, lastPractisedLabel, tempoBar } from "../lib/entries.js";
import { store } from "../lib/store.js";
import { streakSummary } from "./growth.js";

const ACTIVE = new Set(["learning", "polishing"]);
export function pickNextUp(entries) {
  const active = entries.filter((entry) => ACTIVE.has(entry.status));
  if (!active.length) return null;
  return [...active].sort((a, b) => {
    const da = daysSince(a.last_practiced_at);
    const db = daysSince(b.last_practiced_at);
    if (da === null && db !== null) return -1;
    if (db === null && da !== null) return 1;
    if (da !== db) return (db ?? 0) - (da ?? 0);
    return Number(a.piece.difficulty_score ?? 0) - Number(b.piece.difficulty_score ?? 0);
  })[0];
}

function nextUpCard(entry) {
  if (!entry) {
    return sectionBlock(
      "Next up",
      { caption: "Nothing is in progress yet." },
      el("a", { class: "btn", href: "/repertoire/new", "data-link": true }, "Add a piece to learn")
    );
  }
  const reasons = [lastPractisedLabel(entry.last_practiced_at)];
  if (entry.decay_level > 0.35) reasons.push(entry.is_frozen ? "frozen in your sky" : "starting to drift");
  return el(
    "section",
    { class: "panel panel-accent next-up" },
    el("div", { class: "stat-label" }, "Next up"),
    el("h2", { class: "next-up-title" }, el("a", { href: `/repertoire/${entry.id}`, "data-link": true }, entry.piece.title)),
    el("p", { class: "muted", style: "margin:0" }, [entry.piece.composer?.name, entry.status.replace(/_/g, " ")].filter(Boolean).join(" · ")),
    el("p", { class: "next-up-reason" }, reasons.join(", ") + "."),
    tempoBar(entry),
    el(
      "div",
      { class: "row", style: "margin-top:var(--space-4)" },
      el("a", { class: "btn", href: `/repertoire/${entry.id}`, "data-link": true }, "Open piece"),
      el("a", { class: "btn btn-ghost", href: "/practice", "data-link": true }, "Start a session")
    )
  );
}

function weekCard(load) {
  const streak = streakSummary(store.streak, { compact: true });
  if (!load) return sectionBlock("This week", {}, streak, empty("No load data yet. Log a practice session."));
  const pct = load.threshold ? Math.min((load.load_total / load.threshold) * 100, 100) : 0;
  return sectionBlock(
    "This week",
    { caption: `${load.minutes_this_week} minutes logged`, action: el("span", { class: `pill ${toneForSeverity(load.severity)}` }, load.severity) },
    streak,
    el("div", { class: "stat-label" }, "Load guard"),
    el(
      "div",
      { class: "row", style: "gap:var(--space-3);flex-wrap:nowrap" },
      el("span", { class: "stat", style: "font-size:24px" }, Math.round(load.load_total)),
      el("span", { class: "faint mono", style: "font-size:12px" }, `of ${Math.round(load.threshold)}`)
    ),
    el("div", { class: "bar", style: "margin:8px 0 6px" }, el("span", { style: `width:${pct}%` })),
    el("p", { class: "muted", style: "margin:0;font-size:13px" }, load.message || ""),
    load.stretch_warnings?.length
      ? el(
          "ul",
          { class: "flat-list", style: "margin-top:var(--space-3)" },
          ...load.stretch_warnings.map((w) =>
            el("li", { class: "flat-row" }, el("span", {}, w.title), el("span", { class: "pill pill-warn" }, `needs ${w.required_cm}cm`))
          )
        )
      : null
  );
}

function entryRow(entry) {
  return el(
    "li",
    { class: "flat-row today-row" },
    el(
      "div",
      { style: "min-width:0;flex:1" },
      el("a", { href: `/repertoire/${entry.id}`, "data-link": true, class: "today-row-title" }, entry.piece.title),
      el("div", { class: "faint", style: "font-size:12.5px" }, [entry.piece.composer?.name, lastPractisedLabel(entry.last_practiced_at)].filter(Boolean).join(" · ")),
      tempoBar(entry)
    ),
    el("span", { class: "entry-status" }, entry.status.replace(/_/g, " "))
  );
}

function attentionRow(entry) {
  const reason = entry.is_frozen
    ? "Frozen: log a maintenance pass to thaw it"
    : entry.decay_level > 0.35
      ? "Drifting: a short maintenance pass resets it"
      : "Needs a verification take before it lights up";
  return el(
    "li",
    { class: "flat-row" },
    el(
      "div",
      {},
      el("a", { href: `/repertoire/${entry.id}`, "data-link": true, class: "today-row-title" }, entry.piece.title),
      el("div", { class: "faint", style: "font-size:12.5px" }, reason)
    ),
    el("span", { class: `pill ${entry.is_frozen || entry.decay_level > 0.35 ? "pill-frozen" : "pill-warn"}` }, entry.is_frozen ? "frozen" : entry.decay_level > 0.35 ? "drifting" : "unverified")
  );
}

function statsStrip(stats) {
  const cell = (label, value) => el("div", { class: "summary-cell" }, el("div", { class: "stat-label" }, label), el("div", { class: "stat" }, value));
  const average =
    stats.average_difficulty != null && Number.isFinite(Number(stats.average_difficulty))
      ? (Math.round(Number(stats.average_difficulty) * 10) / 10).toFixed(1)
      : "--";
  return el(
    "section",
    { class: "panel summary-bar summary-bar-numbers", "aria-label": "Repertoire at a glance" },
    cell("Pieces", stats.total),
    cell("Active", stats.active),
    cell("Average difficulty", average),
    cell("Submissions", stats.submissions)
  );
}

export async function dashboardView(outlet) {
  const heading = el(
    "div",
    { class: "page-head" },
    el(
      "div",
      {},
      el("h1", { style: "margin:0" }, `Good to see you, ${store.user?.display_name || "pianist"}`),
      el("p", { class: "muted", style: "margin:4px 0 0" }, "Here is where your hands are this week.")
    ),
    el("a", { class: "btn", href: "/practice", "data-link": true }, "Start practising")
  );
  const body = el("div", { class: "today" }, skeletonBlock(4));
  outlet.append(heading, body);

  const [statsResult, loadResult, entriesResult] = await Promise.allSettled([
    api.repertoireStats(),
    api.load(),
    api.repertoire({ limit: 100 }),
    store.refreshProfile(),
  ]);
  const entries = entriesResult.status === "fulfilled" ? entriesResult.value.items : [];
  const active = entries.filter((entry) => ACTIVE.has(entry.status));
  const next = pickNextUp(entries);
  const attention = entries.filter((entry) => entry.decay_level > 0.35 || entry.needs_verification);

  const inProgress = sectionBlock(
    "In progress",
    {
      caption: active.length ? `${active.length} piece${active.length === 1 ? "" : "s"} you're working on` : null,
      action: el("a", { class: "reveal-link", href: "/repertoire", "data-link": true }, "All repertoire"),
    },
    active.length
      ? el("ul", { class: "flat-list" }, ...active.filter((entry) => entry !== next).slice(0, 6).map(entryRow))
      : empty("Nothing in progress.", el("a", { class: "btn", href: "/repertoire/new", "data-link": true }, "Add a piece"))
  );

  body.replaceChildren(
    el("div", { class: "today-hero" }, nextUpCard(next), weekCard(loadResult.status === "fulfilled" ? loadResult.value : null)),
    el(
      "div",
      { class: "today-lists" },
      inProgress,
      attention.length
        ? sectionBlock("Needs attention", { caption: "Pieces fading from your sky or waiting on a verification take." }, el("ul", { class: "flat-list" }, ...attention.slice(0, 6).map(attentionRow)))
        : null
    ),
    statsResult.status === "fulfilled" ? statsStrip(statsResult.value) : empty("Could not load your stats.")
  );
}
