import { api } from "../api/client.js";
import { el, empty, skeletonBlock, toneForSeverity } from "../lib/dom.js";
import { notify } from "../lib/toast.js";
import { renderNotation } from "../lib/notation.js";
import { playNotation } from "../lib/synth.js";

function sightReadingForge() {
  const host = el("section", { class: "panel" }, el("h3", {}, "Sight-reading forge"), skeletonBlock(2));
  const techniqueSelect = el("select", {}, el("option", { value: "" }, "Any technique"));
  const generateButton = el("button", { class: "btn btn-small" }, "Generate exercise");
  const stage = el("div", { class: "stack" });

  api
    .techniques()
    .then((techniques) => {
      techniqueSelect.append(...techniques.map((t) => el("option", { value: t.id }, t.name)));
    })
    .catch(() => {});

  let activePlayback = null;

  function renderExercise(exercise) {
    stage.replaceChildren();
    if (activePlayback) {
      activePlayback.stop();
      activePlayback = null;
    }
    if (!exercise.notation) {
      stage.append(empty("No notation for this exercise."));
      return;
    }
    const staff = el("div", { class: "notation-host" }, renderNotation(exercise.notation));
    const playButton = el(
      "button",
      {
        type: "button",
        class: "btn btn-small btn-ghost",
        onclick: () => {
          if (activePlayback) {
            activePlayback.stop();
            activePlayback = null;
            playButton.textContent = "Play";
            return;
          }
          playButton.textContent = "Stop";
          activePlayback = playNotation(exercise.notation, {
            onDone: () => {
              playButton.textContent = "Play";
              activePlayback = null;
            },
          });
        },
      },
      "Play"
    );
    const scoreRow = exercise.attempted_at
      ? el("span", { class: "pill pill-accent" }, `scored ${exercise.self_score} / 5`)
      : el(
          "div",
          { class: "row" },
          ...[1, 2, 3, 4, 5].map((score) =>
            el(
              "button",
              {
                type: "button",
                class: "btn btn-small btn-ghost",
                onclick: async (event) => {
                  event.target.parentElement.querySelectorAll("button").forEach((b) => (b.disabled = true));
                  try {
                    const updated = await api.scoreSightReading(exercise.id, score);
                    notify.success(score >= 4 ? "Nice reading. That technique is a step closer to green." : "Logged");
                    renderExercise(updated);
                  } catch (error) {
                    notify.error(error.detail || "Could not save that score");
                  }
                },
              },
              String(score)
            )
          )
        );
    stage.append(
      el(
        "div",
        { class: "row", style: "justify-content:space-between;margin-bottom:8px" },
        el("span", { class: "faint mono", style: "font-size:11.5px" }, `${exercise.notation.key} major · ${exercise.notation.tempo_bpm} bpm · difficulty ${exercise.difficulty}`),
        playButton
      ),
      staff,
      el("div", { class: "row", style: "margin-top:10px" }, el("span", { class: "faint", style: "font-size:12px" }, "How did that go?"), scoreRow)
    );
  }

  generateButton.addEventListener("click", async () => {
    generateButton.disabled = true;
    stage.replaceChildren(skeletonBlock(2));
    try {
      const exercise = await api.generateSightReading({
        technique_id: techniqueSelect.value ? Number(techniqueSelect.value) : null,
      });
      renderExercise(exercise);
    } catch (error) {
      stage.replaceChildren(empty(error.detail || "Could not forge an exercise."));
    } finally {
      generateButton.disabled = false;
    }
  });

  host.replaceChildren(
    el("h3", {}, "Sight-reading forge"),
    el("p", { class: "faint", style: "margin:-4px 0 12px;font-size:12px" }, "Generates an infinite 8-bar exercise for a technique. Score 4 or 5 to prove mastery and turn it green."),
    el("div", { class: "row", style: "margin-bottom:12px" }, techniqueSelect, generateButton),
    stage
  );
  return host;
}

export async function practiceView(outlet) {
  const sessionHost = el("section", { class: "panel panel-accent" }, skeletonBlock(2));
  const loadHost = el("section", { class: "panel" }, el("h3", {}, "This week"), skeletonBlock(2));
  const historyHost = el("section", { class: "panel" }, el("h3", {}, "Recent sessions"), skeletonBlock(3));

  outlet.append(
    el("h1", {}, "Practice"),
    el("div", { class: "stack" }, sessionHost, sightReadingForge(), el("div", { class: "grid" }, loadHost, historyHost))
  );

  async function renderSession() {
    sessionHost.replaceChildren(skeletonBlock(2));
    let open = null;
    try {
      open = await api.openSession();
    } catch {
      open = null;
    }

    if (!open) {
      const modeSelect = el(
        "select",
        { style: "max-width:200px" },
        ...["free", "live_listening", "forge_drill", "sight_reading", "polyrhythm"].map((mode) =>
          el("option", { value: mode }, mode.replace(/_/g, " "))
        )
      );
      sessionHost.replaceChildren(
        el("h3", {}, "No session running"),
        el("p", { class: "muted" }, "Start one and the load guard will track what it costs your hands."),
        el(
          "div",
          { class: "row" },
          modeSelect,
          el(
            "button",
            {
              class: "btn",
              onclick: async (event) => {
                event.target.disabled = true;
                try {
                  await api.startSession({ mode: modeSelect.value });
                  notify.success("Session started");
                  await renderSession();
                } catch (error) {
                  notify.error(error.detail || "Could not start a session");
                  event.target.disabled = false;
                }
              },
            },
            "Start session"
          )
        )
      );
      return;
    }

    const minutes = el("input", { type: "number", min: "1", max: "600", value: "20", style: "max-width:110px" });
    const entrySelect = el("select", { style: "max-width:260px" }, el("option", { value: "" }, "General practice"));
    try {
      const page = await api.repertoire({ limit: 50 });
      page.items.forEach((entry) => entrySelect.append(el("option", { value: entry.id }, entry.piece.title)));
    } catch {
      /* repertoire unavailable, keep general option */
    }

    sessionHost.replaceChildren(
      el("div", { class: "row", style: "justify-content:space-between" }, el("h3", { style: "margin:0" }, `Session running · ${open.mode.replace(/_/g, " ")}`), el("span", { class: "pill pill-accent" }, `${open.logged_minutes} min`)),
      el("p", { class: "muted" }, `Load so far: ${open.total_load}`),
      el(
        "div",
        { class: "row", style: "margin-bottom:12px" },
        minutes,
        entrySelect,
        el(
          "button",
          {
            class: "btn btn-small",
            onclick: async (event) => {
              const value = Number(minutes.value);
              if (!value || value < 1) return notify.error("Enter the minutes you practised");
              event.target.disabled = true;
              try {
                await api.addSessionItem(open.id, {
                  minutes: value,
                  repertoire_entry_id: entrySelect.value || null,
                });
                notify.success("Logged");
                await renderSession();
                await renderLoad();
              } catch (error) {
                notify.error(error.detail || "Could not log that");
                event.target.disabled = false;
              }
            },
          },
          "Log block"
        )
      ),
      open.items.length
        ? el("ul", { class: "list" }, ...open.items.map((item) => el("li", { class: "list-item" }, el("span", {}, item.target_label), el("span", { class: "pill mono" }, `${item.minutes} min · ${item.load_units}`))))
        : el("p", { class: "faint", style: "margin:0" }, "Nothing logged yet."),
      el(
        "div",
        { class: "row", style: "margin-top:14px" },
        el(
          "button",
          {
            class: "btn btn-ghost btn-small",
            onclick: async (event) => {
              event.target.disabled = true;
              try {
                await api.closeSession(open.id, {});
                notify.success("Session closed");
                await renderSession();
                await renderLoad();
              } catch (error) {
                notify.error(error.detail || "Could not close the session");
                event.target.disabled = false;
              }
            },
          },
          "Close session"
        )
      )
    );
  }

  async function renderLoad() {
    loadHost.replaceChildren(el("h3", {}, "This week"));
    try {
      const l = await api.load();
      const pct = l.threshold ? Math.min((l.load_total / l.threshold) * 100, 100) : 0;
      loadHost.append(
        el("div", { class: "row", style: "justify-content:space-between" }, el("span", { class: "stat", style: "font-size:24px" }, Math.round(l.load_total)), el("span", { class: `pill ${toneForSeverity(l.severity)}` }, l.severity)),
        el("div", { class: "bar", style: "margin:12px 0 0" }, el("span", { style: `width:${pct}%` })),
        el(
          "div",
          { class: "bar-ticks", style: "margin-bottom:10px" },
          el("span", {}, "0"),
          el("span", {}, Math.round(l.threshold / 2)),
          el("span", {}, Math.round(l.threshold))
        ),
        el("p", { class: "muted", style: "margin:0" }, l.message || "")
      );
    } catch (error) {
      loadHost.append(empty(error.detail || "No load data yet."));
    }
  }

  await Promise.all([renderSession(), renderLoad()]);

  try {
    const page = await api.sessions({ limit: 8 });
    historyHost.replaceChildren(el("h3", {}, "Recent sessions"));
    if (!page.items.length) {
      historyHost.append(empty("No sessions yet."));
    } else {
      historyHost.append(
        el(
          "ul",
          { class: "list" },
          ...page.items.map((s) =>
            el(
              "li",
              { class: "list-item" },
              el("span", {}, new Date(s.started_at).toLocaleDateString()),
              el("span", { class: "pill mono" }, `${s.logged_minutes} min · ${s.total_load}`)
            )
          )
        )
      );
    }
  } catch (error) {
    historyHost.replaceChildren(el("h3", {}, "Recent sessions"), empty(error.detail || "Could not load sessions."));
  }
}
