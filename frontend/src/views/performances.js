import { api } from "../api/client.js";
import { el, empty, formatDuration, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";

function verdictTone(verdict) {
  if (!verdict) return "pill";
  if (verdict.includes("stage ready")) return "pill pill-ok";
  if (verdict.includes("nearly")) return "pill pill-warn";
  if (verdict.includes("not ready")) return "pill pill-bad";
  return "pill";
}

export async function performancesView(outlet, { embedded = false } = {}) {
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
          class: "btn btn-small",
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
                readiness ? el("span", { class: verdictTone(readiness.verdict) }, readiness.verdict) : null
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
              : el("p", { class: "faint", style: "margin-top:10px" }, "No programme set yet.")
          );
        })
      );
      listHost.replaceChildren(...cards);
    } catch (error) {
      listHost.replaceChildren(empty(error.detail || "Could not load performances."));
    }
  }

  outlet.append(...[embedded ? null : el("h1", {}, "Performances"), createPanel, listHost].filter(Boolean));
  await render();
}
