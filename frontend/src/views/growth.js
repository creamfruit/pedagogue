import { api } from "../api/client.js";
import { el, empty, sectionBlock, skeletonBlock } from "../lib/dom.js";
import { growthChart } from "../lib/growthChart.js";
import { store } from "../lib/store.js";

export function streakSummary(streak, { compact = false } = {}) {
  if (!streak) return null;
  const flame = el("span", { class: `streak-count mono ${streak.current ? "streak-live" : ""}` }, String(streak.current));
  const status = streak.today_done
    ? `Today counts. Come back tomorrow for day ${streak.current + 1}.`
    : streak.current
      ? `Practise ${Math.max(streak.min_minutes - streak.minutes_today, 1)} more minutes today to keep it and earn +${streak.next_bonus_xp} xp.`
      : `Practise ${streak.min_minutes} minutes today to start a streak (+${streak.next_bonus_xp} xp).`;
  return el(
    "div",
    { class: `streak ${compact ? "streak-compact" : ""}` },
    flame,
    el(
      "div",
      {},
      el("div", { class: "streak-title" }, streak.current === 1 ? "day in a row" : "days in a row"),
      el("div", { class: "streak-status" }, status),
      compact ? null : el("div", { class: "faint mono", style: "font-size:11px;margin-top:4px" }, `longest ${streak.longest} · a day counts from ${streak.min_minutes} logged minutes`)
    )
  );
}

function headline(series) {
  if (series.latest_avg === null) return null;
  const change = series.change;
  return el(
    "div",
    { class: "growth-headline" },
    el("div", { class: "stat" }, series.latest_avg.toFixed(1)),
    el(
      "p",
      { class: "muted", style: "margin:0" },
      change === null
        ? "Average difficulty of what you've practised recently."
        : `Average difficulty of what you practise, ${change >= 0 ? "up" : "down"} ${Math.abs(change).toFixed(1)} from ${series.first_avg.toFixed(1)} over this period.`
    )
  );
}

export async function growthView(outlet) {
  const streakHost = sectionBlock("Practice streak", {}, skeletonBlock(1));
  const chartHost = sectionBlock(
    "Difficulty over time",
    { caption: "Minute-weighted average difficulty of the pieces you practised each week, smoothed over four weeks. Stars mark pieces you learnt." },
    skeletonBlock(3)
  );
  outlet.append(el("div", { class: "growth" }, streakHost, chartHost));

  const [streakResult, historyResult] = await Promise.allSettled([api.streak(), api.difficultyHistory(26)]);
  const streak = streakResult.status === "fulfilled" ? streakResult.value : store.streak;
  streakHost.replaceChildren(streakHost.firstChild, streakSummary(streak) || empty("Could not load your streak."));

  const body = [...chartHost.children].slice(0, 1);
  if (historyResult.status !== "fulfilled") {
    chartHost.replaceChildren(...body, empty(historyResult.reason?.detail || "Could not load your history."));
    return;
  }
  const series = historyResult.value;
  if (!series.weeks.some((week) => week.minutes)) {
    chartHost.replaceChildren(...body, empty("Log a practice session on a piece and your curve starts here."));
    return;
  }
  chartHost.replaceChildren(...body, headline(series), growthChart(series));
}
