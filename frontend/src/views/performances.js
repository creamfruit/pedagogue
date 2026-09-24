import { api } from "../api/client.js";
import { el, empty, formatDuration, openModal, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";

const MAX_TIMETABLE_DAYS = 21;
const UNSCORED_BASELINE = 35;

function verdictTone(verdict) {
  if (!verdict) return "pill";
  if (verdict.includes("stage ready")) return "pill pill-ok";
  if (verdict.includes("nearly")) return "pill pill-warn";
  if (verdict.includes("not ready")) return "pill pill-bad";
  return "pill";
}

function distributeSchedule(pieces, totalDays) {
  const totalWeight = pieces.reduce((sum, piece) => sum + piece.weight, 0) || 1;
  const withCounts = pieces.map((piece) => ({ ...piece, exact: (piece.weight / totalWeight) * totalDays, count: 0 }));
  withCounts.forEach((piece) => {
    piece.count = Math.floor(piece.exact);
  });
  let allocated = withCounts.reduce((sum, piece) => sum + piece.count, 0);
  const byRemainder = withCounts
    .map((piece, index) => ({ index, frac: piece.exact - piece.count }))
    .sort((a, b) => b.frac - a.frac);
  let cursor = 0;
  while (allocated < totalDays && byRemainder.length) {
    withCounts[byRemainder[cursor % byRemainder.length].index].count += 1;
    allocated += 1;
    cursor += 1;
  }
  if (allocated < totalDays && withCounts.length) {
    withCounts[0].count += totalDays - allocated;
  }

  const slots = new Array(totalDays).fill(null);
  withCounts.forEach((piece) => {
    if (piece.count <= 0) return;
    const step = totalDays / piece.count;
    for (let k = 0; k < piece.count; k += 1) {
      let pos = Math.round(k * step + step / 2 - 0.5);
      pos = Math.min(Math.max(pos, 0), totalDays - 1);
      let attempts = 0;
      while (slots[pos] && attempts < totalDays) {
        pos = (pos + 1) % totalDays;
        attempts += 1;
      }
      slots[pos] = piece;
    }
  });
  return slots;
}

function buildTimetable(program, readiness, daysUntil) {
  if (!program.length || daysUntil == null || daysUntil <= 0) return null;
  const totalDays = Math.min(daysUntil, MAX_TIMETABLE_DAYS);

  const pieces = program.map((item) => {
    const piece = item.repertoire_entry.piece;
    const scored = readiness?.program?.find((p) => p.repertoire_entry_id === item.repertoire_entry_id);
    const difficulty = piece.difficulty_score ?? 50;
    const score = scored?.overall_score ?? null;
    const gap = 100 - (score ?? UNSCORED_BASELINE);
    const weight = Math.max((difficulty / 100) * 0.5 + (gap / 100) * 0.5, 0.05);
    return {
      title: piece.title,
      entryId: item.repertoire_entry_id,
      difficulty: Math.round(difficulty),
      score,
      weight,
      urgent: score == null || score < 70,
    };
  });

  const slots = distributeSchedule(pieces, totalDays);
  const today = new Date();
  return slots.map((piece, index) => {
    const date = new Date(today);
    date.setDate(date.getDate() + index + 1);
    return {
      date,
      piece,
      truncated: index === totalDays - 1 && daysUntil > MAX_TIMETABLE_DAYS,
    };
  });
}

function timetablePanel(performance, readiness) {
  const rows = buildTimetable(performance.program, readiness, performance.days_until);
  if (!performance.program.length) {
    return el("p", { class: "faint", style: "margin-top:10px" }, "Link pieces to the programme to generate a practice timetable.");
  }
  if (!rows) {
    return el("p", { class: "faint", style: "margin-top:10px" }, "Set an upcoming date to generate a practice timetable.");
  }
  return el(
    "section",
    { style: "margin-top:14px" },
    el("h3", {}, "Practice timetable"),
    el(
      "ul",
      { class: "timetable" },
      ...rows.map((row) =>
        el(
          "li",
          { class: "timetable-row", dataset: { urgent: String(row.piece.urgent) } },
          el(
            "span",
            { class: "timetable-date mono" },
            row.date.toLocaleDateString(undefined, { month: "short", day: "numeric" })
          ),
          el(
            "div",
            { class: "timetable-body" },
            el("div", { class: "timetable-piece" }, row.piece.title),
            el(
              "div",
              { class: "timetable-reason" },
              `difficulty ${row.piece.difficulty} · ${row.piece.score != null ? `readiness ${row.piece.score}` : "not yet scored"}`
            )
          )
        )
      )
    ),
    rows.some((row) => row.truncated)
      ? el("p", { class: "faint mono", style: "font-size:11px;margin-top:6px" }, `Showing the next ${MAX_TIMETABLE_DAYS} days.`)
      : null
  );
}

function programModalContent(performance, allEntries, onSaved) {
  const selected = new Set(performance.program.map((item) => item.repertoire_entry_id));
  const list = el(
    "ul",
    { class: "list" },
    ...(allEntries.length ? [] : [empty("Add pieces to your repertoire first.")])
  );

  allEntries.forEach((entry) => {
    const checkbox = el("input", { type: "checkbox", checked: selected.has(entry.id) || null });
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(entry.id);
      else selected.delete(entry.id);
    });
    list.append(
      el(
        "li",
        { class: "list-item program-item" },
        checkbox,
        el(
          "div",
          { style: "flex:1" },
          el("div", {}, entry.piece.title),
          el("div", { class: "faint", style: "font-size:12px" }, entry.piece.composer?.name || "unknown")
        ),
        entry.piece.difficulty_score ? el("span", { class: "pill mono" }, entry.piece.difficulty_score) : null
      )
    );
  });

  const save = el(
    "button",
    {
      class: "btn btn-solid",
      style: "margin-top:14px",
      onclick: async () => {
        if (!selected.size) return notify.error("Pick at least one piece");
        save.disabled = true;
        try {
          await api.setProgram(performance.id, Array.from(selected));
          notify.success("Programme updated");
          await onSaved();
        } catch (error) {
          notify.error(error.detail || "Could not update the programme");
        } finally {
          save.disabled = false;
        }
      },
    },
    "Save programme"
  );

  return el("div", { class: "stack" }, list, save);
}

export async function performancesView(outlet) {
  const listHost = el("div", {}, skeletonBlock(3));
  const title = el("input", { type: "text", placeholder: "Year-end recital", style: "max-width:260px" });
  const date = el("input", { type: "date", style: "max-width:180px" });
  const venue = el("input", { type: "text", placeholder: "Venue", style: "max-width:220px" });

  const createPanel = el(
    "section",
    { class: "panel", style: "margin-bottom:18px" },
    el("h3", {}, "New performance"),
    el(
      "div",
      { class: "row" },
      title,
      date,
      venue,
      el(
        "button",
        {
          class: "btn btn-small btn-solid",
          onclick: async (event) => {
            if (!title.value.trim()) return notify.error("Give the performance a title");
            event.target.disabled = true;
            try {
              await api.createPerformance({
                title: title.value.trim(),
                event_date: date.value || null,
                venue: venue.value.trim() || null,
              });
              title.value = "";
              venue.value = "";
              notify.success("Performance created");
              await render();
            } catch (error) {
              notify.error(error.detail || "Could not create that");
            } finally {
              event.target.disabled = false;
            }
          },
        },
        "Create"
      )
    )
  );

  async function openProgramModal(performance) {
    const body = el("div", {}, skeletonBlock(3));
    const modal = openModal(body, { title: `Programme · ${performance.title}` });
    try {
      const page = await api.repertoire({ limit: 100 });
      body.replaceChildren(
        programModalContent(performance, page.items, async () => {
          modal.close();
          await render();
        })
      );
    } catch (error) {
      body.replaceChildren(empty(error.detail || "Could not load your repertoire."));
    }
  }

  async function render() {
    listHost.replaceChildren(skeletonBlock(3));
    try {
      const performances = await api.performances();
      if (!performances.length) {
        listHost.replaceChildren(empty("No performances scheduled."));
        return;
      }
      const cards = await Promise.all(
        performances.map(async (performance) => {
          let readiness = null;
          try {
            readiness = await api.performanceReadiness(performance.id);
          } catch {
            readiness = null;
          }
          return el(
            "section",
            { class: "panel", style: "margin-bottom:14px" },
            el(
              "div",
              { class: "row", style: "justify-content:space-between" },
              el("div", {}, el("h2", { style: "margin:0" }, performance.title), el("p", { class: "muted", style: "margin:2px 0 0" }, [performance.venue, performance.event_date].filter(Boolean).join(" · "))),
              el(
                "div",
                { class: "row" },
                performance.days_until != null ? el("span", { class: "pill mono" }, `${performance.days_until} days`) : null,
                readiness ? el("span", { class: verdictTone(readiness.verdict) }, readiness.verdict) : null,
                el(
                  "button",
                  { type: "button", class: "btn btn-small btn-ghost", onclick: () => openProgramModal(performance) },
                  "Manage programme"
                )
              )
            ),
            el("p", { class: "faint mono", style: "font-size:12px;margin:10px 0 0" }, `Programme ${formatDuration(performance.total_duration_sec)}`),
            performance.program.length
              ? el(
                  "ul",
                  { class: "list", style: "margin-top:12px" },
                  ...performance.program.map((item) => {
                    const scored = readiness?.program.find((p) => p.repertoire_entry_id === item.repertoire_entry_id);
                    return el(
                      "li",
                      { class: "list-item" },
                      el("span", {}, `${item.program_order}. ${item.repertoire_entry.piece.title}`),
                      el("span", { class: "pill mono" }, scored?.overall_score != null ? scored.overall_score : "unscored")
                    );
                  })
                )
              : el("p", { class: "faint", style: "margin-top:10px" }, "No programme set yet."),
            timetablePanel(performance, readiness)
          );
        })
      );
      listHost.replaceChildren(...cards);
    } catch (error) {
      listHost.replaceChildren(empty(error.detail || "Could not load performances."));
    }
  }

  outlet.append(el("h1", {}, "Performances"), createPanel, listHost);
  await render();
}
