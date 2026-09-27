import { api } from "../api/client.js";
import { el, empty, sectionBlock, skeletonBlock, tabs } from "../lib/dom.js";

export function standingsTable(standings, { unit, detail } = {}) {
  const rows = standings.rows || [];
  const you = standings.you;
  const list = rows.length
    ? el(
        "ol",
        { class: "standings" },
        ...rows.map((row) =>
          el(
            "li",
            { class: `standing ${row.is_you ? "standing-you" : ""}` },
            el("span", { class: "standing-rank mono" }, `#${row.rank}`),
            el("span", { class: "standing-name" }, row.is_you ? `${row.name} (you)` : row.name),
            detail ? el("span", { class: "faint mono standing-detail" }, detail(row)) : null,
            el("span", { class: "standing-score mono" }, `${Math.round(row.score).toLocaleString()}${unit ? ` ${unit}` : ""}`)
          )
        )
      )
    : empty("Nobody has opted in here yet.");
  const privateNote =
    you && !you.listed
      ? el(
          "p",
          { class: "faint", style: "margin:var(--space-3) 0 0;font-size:12.5px" },
          `You'd be #${you.rank} with ${Math.round(you.score).toLocaleString()}${unit ? ` ${unit}` : ""}. Only you can see this: turn on "Show me on leaderboards" in Settings to appear.`
        )
      : null;
  return el("div", {}, list, privateNote);
}

export function scopeSwitch(active, onChange) {
  return tabs(
    [
      { id: "friends", label: "Friends" },
      { id: "global", label: "Everyone" },
    ],
    active,
    onChange,
    { label: "Leaderboard scope" }
  );
}

function boardSection(title, caption, load, options) {
  let scope = options.scope;
  const body = el("div", {}, skeletonBlock(3));
  const host = sectionBlock(title, { caption, action: options.action }, el("div", { class: "scope-host" }), body);
  const scopeHost = host.querySelector(".scope-host");

  async function render() {
    scopeHost.replaceChildren(
      scopeSwitch(scope, (next) => {
        scope = next;
        render();
      })
    );
    body.replaceChildren(skeletonBlock(3));
    try {
      body.replaceChildren(standingsTable(await load(scope), options));
    } catch (error) {
      body.replaceChildren(empty(error.detail || "Could not load this leaderboard."));
    }
  }
  render();
  return host;
}

export async function leaderboardsView(outlet) {
  const roulette = boardSection(
    "Today's sight-reading roulette",
    "One snippet a day, the same for everyone. Name the ringed note in each bar: 100 points a note, plus a speed bonus.",
    (scope) => api.rouletteStandings(scope),
    {
      scope: "global",
      detail: (row) => `${row.detail.correct}/${row.detail.total} in ${Math.round(row.detail.seconds)}s`,
      action: el("a", { class: "btn btn-small", href: "/roulette", "data-link": true }, "Play today's"),
    }
  );
  const week = boardSection(
    "Practice this week",
    "Minutes logged this week (Monday to Sunday, your time).",
    (scope) => api.practiceWeekStandings(scope),
    { scope: "friends", unit: "min", detail: (row) => (row.detail.streak ? `${row.detail.streak}-day streak` : "") }
  );
  outlet.append(
    el("div", { class: "growth" }, roulette, week),
    el(
      "p",
      { class: "faint", style: "margin-top:var(--space-4);font-size:12.5px" },
      "Leaderboards are opt-in. Add friends and choose whether you appear in ",
      el("a", { href: "/settings", "data-link": true }, "Settings"),
      "."
    )
  );
}
