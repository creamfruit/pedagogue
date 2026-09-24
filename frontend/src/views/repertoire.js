import { api, pollSubmission } from "../api/client.js";
import { pieceCoreStats, pieceOverview } from "../components/overview.js";
import { el, empty, openModal, optionCard, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";
import { store } from "../lib/store.js";
import { FROZEN } from "../lib/palette.js";

const PRACTICE_MODES = [
  { mode: "free", icon: "\u{1F3B9}", title: "Free practice", description: "Open-ended time at the keys, logged minutes and load only." },
  { mode: "live_listening", icon: "\u{1F3A7}", title: "Live listening coach", description: "Real-time cues on tempo drift and tension while you play." },
  { mode: "forge_drill", icon: "\u{1F528}", title: "Forge a drill", description: "Targeted repetitions built from your weakest passages." },
  { mode: "sight_reading", icon: "\u{1F3BC}", title: "Sight-reading forge", description: "A freshly generated 8-bar exercise, never the same twice." },
  { mode: "polyrhythm", icon: "\u{1F300}", title: "Polyrhythm trainer", description: "Cross-rhythm practice timed against a click." },
];

function openPracticeModal() {
  const cards = el(
    "div",
    { class: "option-grid" },
    ...PRACTICE_MODES.map((option) =>
      optionCard({
        icon: option.icon,
        title: option.title,
        description: option.description,
        onSelect: async () => {
          try {
            await api.startSession({ mode: option.mode });
            modal.close();
            navigate("/practice");
          } catch (error) {
            notify.error(error.detail || "Could not start that session");
          }
        },
      })
    )
  );
  const modal = openModal(cards, { title: "How do you want to practice?" });
}

const STATUSES = ["wishlist", "learning", "polishing", "performance_ready", "retired"];

export async function repertoireView(outlet, context) {
  const query = context.query.q || "";
  const statusFilter = context.query.status || "";
  const genreFilter = context.query.genre_id || "";
  const composerFilter = context.query.composer_id || "";
  const composerName = context.query.composer_name || "";
  const minDifficulty = context.query.min_difficulty || "";
  const maxDifficulty = context.query.max_difficulty || "";

  const search = el("input", { type: "search", placeholder: "Search your pieces", value: query, style: "max-width:260px" });
  const select = el(
    "select",
    { style: "max-width:180px" },
    el("option", { value: "" }, "All statuses"),
    ...STATUSES.map((s) => el("option", { value: s, selected: s === statusFilter || null }, s.replace(/_/g, " ")))
  );
  const genreSelect = el("select", { style: "max-width:170px" }, el("option", { value: "" }, "All genres"));
  const minInput = el("input", { type: "number", min: "0", max: "100", placeholder: "Min diff.", value: minDifficulty, style: "max-width:110px" });
  const maxInput = el("input", { type: "number", min: "0", max: "100", placeholder: "Max diff.", value: maxDifficulty, style: "max-width:110px" });
  const composerSearch = el("input", { type: "search", placeholder: "Composer", value: composerName, style: "max-width:170px" });
  const composerResults = el("ul", { class: "list", style: "position:absolute;z-index:5;max-width:260px" });
  let selectedComposerId = composerFilter || "";

  api
    .genres()
    .then((genres) => {
      genreSelect.append(
        ...genres.map((genre) => el("option", { value: genre.id, selected: String(genre.id) === genreFilter || null }, genre.name))
      );
    })
    .catch(() => {});

  const listHost = el("div", {}, skeletonBlock(4));

  function applyFilters() {
    const params = new URLSearchParams();
    if (search.value.trim()) params.set("q", search.value.trim());
    if (select.value) params.set("status", select.value);
    if (genreSelect.value) params.set("genre_id", genreSelect.value);
    if (selectedComposerId) {
      params.set("composer_id", selectedComposerId);
      params.set("composer_name", composerSearch.value.trim());
    }
    if (minInput.value) params.set("min_difficulty", minInput.value);
    if (maxInput.value) params.set("max_difficulty", maxInput.value);
    const qs = params.toString();
    navigate(qs ? `/repertoire?${qs}` : "/repertoire", { replace: true });
  }

  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(applyFilters, 320);
  });
  select.addEventListener("change", applyFilters);
  genreSelect.addEventListener("change", applyFilters);
  minInput.addEventListener("change", applyFilters);
  maxInput.addEventListener("change", applyFilters);

  let composerDebounce;
  composerSearch.addEventListener("input", () => {
    clearTimeout(composerDebounce);
    selectedComposerId = "";
    const term = composerSearch.value.trim();
    if (term.length < 2) {
      composerResults.replaceChildren();
      return;
    }
    composerDebounce = setTimeout(async () => {
      try {
        const composers = await api.searchComposers(term);
        composerResults.replaceChildren(
          ...composers.map((composer) =>
            el(
              "li",
              {
                class: "list-item",
                style: "cursor:pointer",
                onclick: () => {
                  selectedComposerId = composer.id;
                  composerSearch.value = composer.name;
                  composerResults.replaceChildren();
                  applyFilters();
                },
              },
              composer.name
            )
          )
        );
      } catch {
        composerResults.replaceChildren();
      }
    }, 280);
  });

  outlet.append(
    el(
      "div",
      { class: "row", style: "justify-content:space-between;margin-bottom:18px" },
      el("h1", { style: "margin:0" }, "Repertoire"),
      el("a", { class: "btn btn-solid", href: "/repertoire/new", "data-link": true }, "Add a piece")
    ),
    el(
      "div",
      { class: "row", style: "margin-bottom:16px;position:relative" },
      search,
      select,
      genreSelect,
      el("div", { style: "position:relative" }, composerSearch, composerResults),
      minInput,
      maxInput
    ),
    listHost
  );

  try {
    const page = await api.repertoire({
      q: query || undefined,
      status: statusFilter || undefined,
      genre_id: genreFilter || undefined,
      composer_id: selectedComposerId || undefined,
      min_difficulty: minDifficulty || undefined,
      max_difficulty: maxDifficulty || undefined,
      limit: 50,
    });
    listHost.replaceChildren();
    if (!page.items.length) {
      listHost.append(empty("No pieces match.", el("a", { class: "btn", href: "/repertoire/new", "data-link": true }, "Add one")));
      return;
    }
    listHost.append(
      el("p", { class: "faint mono", style: "font-size:12px" }, `${page.meta.total} piece(s)`),
      el(
        "ul",
        { class: "list" },
        ...page.items.map((entry) =>
          el(
            "li",
            {
              class: "list-item list-item-link",
              tabindex: "0",
              role: "link",
              onclick: () => navigate(`/repertoire/${entry.id}`),
              onkeydown: (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  navigate(`/repertoire/${entry.id}`);
                }
              },
            },
            el(
              "div",
              {},
              el("div", { style: "font-weight:500" }, entry.piece.title),
              el("div", { class: "faint", style: "font-size:12.5px" }, entry.piece.composer?.name || "unknown composer")
            ),
            el(
              "div",
              { class: "row" },
              entry.is_top_ten ? el("span", { class: "pill pill-accent" }, "top ten") : null,
              entry.needs_verification ? el("span", { class: "pill pill-warn" }, "unverified") : null,
              entry.decay_level >= 0.85 ? el("span", { class: "pill", style: `color:${FROZEN}` }, "frozen") : null,
              el("span", { class: "pill" }, entry.status.replace(/_/g, " ")),
              entry.piece.difficulty_score ? el("span", { class: "pill mono" }, entry.piece.difficulty_score) : null
            )
          )
        )
      )
    );
  } catch (error) {
    listHost.replaceChildren(empty(error.detail || "Could not load your repertoire."));
  }
}

function catalogSearchPanel(statusSelect) {
  const search = el("input", { type: "search", placeholder: "Search the catalog, e.g. Chopin etude" });
  const results = el("ul", { class: "list" });

  let selected = null;
  const confirm = el(
    "button",
    {
      class: "btn btn-solid",
      disabled: true,
      onclick: async () => {
        if (!selected) return;
        confirm.disabled = true;
        try {
          const entry = await api.createEntry({ piece_id: selected.id, status: statusSelect.value });
          notify.success(`${entry.piece.title} added`);
          navigate(`/repertoire/${entry.id}`);
        } catch (error) {
          notify.error(error.detail || "Could not add that piece");
          confirm.disabled = false;
        }
      },
    },
    "Add to repertoire"
  );

  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    const term = search.value.trim();
    if (term.length < 2) {
      results.replaceChildren();
      return;
    }
    debounce = setTimeout(async () => {
      try {
        const pieces = await api.searchPieces(term, 12);
        results.replaceChildren(
          ...pieces.map((piece) =>
            el(
              "li",
              {
                class: "list-item",
                style: "cursor:pointer",
                onclick: () => {
                  selected = piece;
                  confirm.disabled = false;
                  results.querySelectorAll(".list-item").forEach((n) => n.classList.remove("panel-accent"));
                  results.querySelector(`[data-piece="${piece.id}"]`)?.classList.add("panel-accent");
                },
                dataset: { piece: piece.id },
              },
              el("div", {}, el("div", {}, piece.title), el("div", { class: "faint", style: "font-size:12.5px" }, piece.composer?.name || "unknown")),
              piece.difficulty_score ? el("span", { class: "pill mono" }, piece.difficulty_score) : null
            )
          )
        );
        if (!pieces.length) results.replaceChildren(empty("Nothing found in the catalog."));
      } catch (error) {
        results.replaceChildren(empty(error.detail || "Search failed."));
      }
    }, 300);
  });

  const panel = el(
    "div",
    { class: "stack" },
    el("div", { class: "field" }, el("label", {}, "Find it in the local catalog"), search),
    results,
    confirm
  );
  panel.focusInput = () => search.focus();
  return panel;
}

function externalSearchPanel(statusSelect) {
  const search = el("input", { type: "search", placeholder: "Search a composer, e.g. Rachmaninoff" });
  const results = el("ul", { class: "list" });

  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    const term = search.value.trim();
    if (term.length < 2) {
      results.replaceChildren();
      return;
    }
    debounce = setTimeout(async () => {
      results.replaceChildren(empty("Searching the wider catalog…"));
      try {
        const candidates = await api.searchExternalCatalog(term, 15);
        if (!candidates.length) {
          results.replaceChildren(empty("Nothing found out there."));
          return;
        }
        results.replaceChildren(
          ...candidates.map((candidate) => {
            const importButton = el(
              "button",
              {
                type: "button",
                class: "btn btn-small",
                onclick: async () => {
                  importButton.disabled = true;
                  importButton.textContent = "Generating metadata…";
                  try {
                    const piece = await api.importExternalPiece({
                      external_ref: candidate.external_ref,
                      title: candidate.title,
                      composer_name: candidate.composer_name,
                    });
                    const entry = await api.createEntry({ piece_id: piece.id, status: statusSelect.value });
                    notify.success(`${entry.piece.title} imported and added`);
                    navigate(`/repertoire/${entry.id}`);
                  } catch (error) {
                    notify.error(error.detail || "Could not import that piece");
                    importButton.disabled = false;
                    importButton.textContent = "Import";
                  }
                },
              },
              "Import"
            );
            return el(
              "li",
              { class: "list-item" },
              el(
                "div",
                {},
                el("div", {}, candidate.title, candidate.subtitle ? el("span", { class: "faint" }, ` · ${candidate.subtitle}`) : null),
                el("div", { class: "faint", style: "font-size:12.5px" }, `${candidate.composer_name}${candidate.epoch ? ` · ${candidate.epoch}` : ""}`)
              ),
              importButton
            );
          })
        );
      } catch (error) {
        results.replaceChildren(empty(error.detail || "The external catalog is unreachable right now."));
      }
    }, 350);
  });

  const panel = el(
    "div",
    { class: "stack" },
    el("p", { class: "faint", style: "margin:0;font-size:12.5px" }, "Pulls from the open OpenOpus classical database. Importing generates techniques, difficulty and pedagogical notes on the spot."),
    el("div", { class: "field" }, el("label", {}, "Search by composer"), search),
    results
  );
  panel.focusInput = () => search.focus();
  return panel;
}

function customPiecePanel(statusSelect) {
  const title = el("input", { type: "text", placeholder: "Piece title", maxlength: "200" });
  const composerName = el("input", { type: "text", placeholder: "Composer or artist (optional)", maxlength: "120" });
  const genreSelect = el("select", {}, el("option", { value: "" }, "No genre"));
  const styleTag = el("input", { type: "text", placeholder: "e.g. jazz standard, film score, video game OST", maxlength: "80" });
  const duration = el("input", { type: "number", min: "0", placeholder: "Duration in seconds (optional)" });
  const techniqueHost = el("div", { class: "stack" }, el("span", { class: "faint" }, "Loading techniques…"));
  const weights = new Map();

  api
    .genres()
    .then((genres) => {
      genreSelect.append(...genres.map((genre) => el("option", { value: genre.id }, genre.name)));
    })
    .catch(() => {});

  api
    .techniques()
    .then((techniques) => {
      techniqueHost.replaceChildren(
        ...techniques.map((technique) => {
          const slider = el("input", { type: "range", min: "0", max: "100", value: "0", style: "flex:1" });
          const readout = el("span", { class: "faint mono", style: "font-size:11.5px;width:34px;text-align:right" }, "0%");
          slider.addEventListener("input", () => {
            const value = Number(slider.value);
            readout.textContent = `${value}%`;
            if (value > 0) weights.set(technique.id, value / 100);
            else weights.delete(technique.id);
          });
          return el(
            "div",
            { class: "list-item" },
            el("div", { style: "min-width:150px" }, technique.name),
            slider,
            readout
          );
        })
      );
    })
    .catch(() => techniqueHost.replaceChildren(empty("Could not load techniques.")));

  const submit = el(
    "button",
    {
      class: "btn btn-solid",
      type: "submit",
      onclick: async (event) => {
        event.preventDefault();
        if (!title.value.trim()) return notify.error("Give the piece a title");
        submit.disabled = true;
        try {
          const piece = await api.createPiece({
            title: title.value.trim(),
            composer_name: composerName.value.trim() || null,
            genre_id: genreSelect.value ? Number(genreSelect.value) : null,
            duration_sec: duration.value ? Number(duration.value) : null,
            techniques: Array.from(weights, ([technique_id, weight]) => ({ technique_id, weight })),
            custom_style: styleTag.value.trim() ? { tag: styleTag.value.trim() } : null,
          });
          const entry = await api.createEntry({ piece_id: piece.id, status: statusSelect.value });
          notify.success(`${entry.piece.title} added as a custom piece`);
          navigate(`/repertoire/${entry.id}`);
        } catch (error) {
          notify.error(error.detail || "Could not create that piece");
          submit.disabled = false;
        }
      },
    },
    "Create and add"
  );

  const panel = el(
    "div",
    { class: "stack" },
    el("p", { class: "faint", style: "margin:0;font-size:12.5px" }, "For jazz, film scores, game soundtracks or anything outside the classical catalog. It spawns as a custom planet in your constellation."),
    el("div", { class: "field" }, el("label", {}, "Title"), title),
    el("div", { class: "field" }, el("label", {}, "Composer / artist"), composerName),
    el("div", { class: "field" }, el("label", {}, "Genre"), genreSelect),
    el("div", { class: "field" }, el("label", {}, "Style tag"), styleTag),
    el("div", { class: "field" }, el("label", {}, "Duration"), duration),
    el("div", { class: "field" }, el("label", {}, "Techniques involved"), techniqueHost),
    submit
  );
  panel.focusInput = () => title.focus();
  return panel;
}

export async function newEntryView(outlet) {
  const statusSelect = el("select", {}, ...STATUSES.map((s) => el("option", { value: s, selected: s === "learning" || null }, s.replace(/_/g, " "))));
  const TABS = [
    { id: "catalog", label: "Search catalog", build: catalogSearchPanel },
    { id: "external", label: "Search the wider world", build: externalSearchPanel },
    { id: "custom", label: "Create a custom piece", build: customPiecePanel },
  ];

  const body = el("div", {});
  const tabButtons = new Map();

  function activate(id) {
    tabButtons.forEach((button, key) => button.classList.toggle("panel-accent", key === id));
    const tab = TABS.find((t) => t.id === id);
    const panel = tab.build(statusSelect);
    body.replaceChildren(panel);
    panel.focusInput?.();
  }

  const tabRow = el(
    "div",
    { class: "row", style: "margin-bottom:14px" },
    ...TABS.map((tab) => {
      const button = el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: () => activate(tab.id) }, tab.label);
      tabButtons.set(tab.id, button);
      return button;
    })
  );

  outlet.append(
    el("h1", {}, "Add a piece"),
    el(
      "div",
      { class: "panel stack" },
      tabRow,
      el("div", { class: "field" }, el("label", {}, "Status once added"), statusSelect),
      body
    )
  );
  activate("catalog");
}

const STATUS_FLOW = ["wishlist", "learning", "polishing", "performance_ready", "retired"];

function tapTempoWidget() {
  let taps = [];
  const status = el("span", { class: "faint mono", style: "font-size:11px" }, "no taps yet");
  const node = el(
    "div",
    { class: "row" },
    el(
      "button",
      {
        type: "button",
        class: "btn btn-small btn-ghost",
        onclick: () => {
          taps.push(performance.now());
          status.textContent = `${taps.length} tap(s) captured`;
        },
      },
      "Tap along with the tempo"
    ),
    el(
      "button",
      {
        type: "button",
        class: "btn btn-small btn-ghost",
        onclick: () => {
          taps = [];
          status.textContent = "no taps yet";
        },
      },
      "Reset"
    ),
    status
  );
  return {
    node,
    curve() {
      if (taps.length < 3) return null;
      const points = [];
      let elapsed = 0;
      for (let i = 1; i < taps.length; i += 1) {
        const intervalMs = taps[i] - taps[i - 1];
        elapsed += intervalMs / 1000;
        points.push({ t: Math.round(elapsed * 10) / 10, bpm: Math.round(60000 / intervalMs) });
      }
      return { points };
    },
  };
}

function verificationBanner(entry) {
  if (!entry.needs_verification) return null;
  return el(
    "div",
    { class: "locked-banner" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el("strong", { style: "font-weight:500" }, "Verification required"),
      el("span", { class: "pill pill-warn" }, "hollow star")
    ),
    el(
      "p",
      { class: "muted", style: "margin:8px 0 0;font-size:13.5px" },
      "This piece is difficulty 70 or above. It shows as a hollow, dotted star in your constellation until you record a verification take in the submissions panel below."
    )
  );
}

function decayBanner(entry, onMaintained) {
  if (!(entry.decay_level > 0.35)) return null;
  const button = el(
    "button",
    {
      class: "btn btn-small",
      onclick: async () => {
        button.disabled = true;
        try {
          await api.maintenanceRun(entry.id);
          notify.success("Maintenance logged");
          await onMaintained();
        } catch (error) {
          notify.error(error.detail || "Could not log maintenance");
          button.disabled = false;
        }
      },
    },
    "Log maintenance"
  );
  return el(
    "div",
    { class: "locked-banner" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el("strong", { style: "font-weight:500" }, entry.is_frozen ? "Frozen · orbital decay" : "Drifting · orbital decay"),
      el("span", { class: "pill", style: `color:${FROZEN}` }, `${Math.round(entry.decay_level * 100)}%`)
    ),
    el(
      "p",
      { class: "muted", style: "margin:8px 0 12px;font-size:13.5px" },
      entry.is_frozen
        ? "This piece has gone unplayed long enough to freeze in your constellation. Log a maintenance pass to thaw it."
        : "This piece hasn't been touched in a while and is starting to drift. A short maintenance pass resets the clock."
    ),
    button
  );
}

function planPanel(entryId, plan, onBuild, onAdvance) {
  if (!plan) {
    return el(
      "section",
      { class: "panel", style: "margin-top:16px" },
      el("h3", {}, "Guided learning path"),
      el(
        "p",
        { class: "muted", style: "margin:0 0 12px" },
        "Get a step-by-step plan for this piece, ordered from its gentlest movement or its hardest passages."
      ),
      el("button", { class: "btn btn-small", onclick: onBuild }, "Build a plan")
    );
  }
  return el(
    "section",
    { class: "panel", style: "margin-top:16px" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el("h3", { style: "margin:0" }, "Guided learning path"),
      el("span", { class: "pill mono" }, `${Math.round(plan.progress * 100)}%`)
    ),
    plan.rationale ? el("p", { class: "muted", style: "font-size:13px" }, plan.rationale) : null,
    el(
      "ol",
      { class: "section-list" },
      ...plan.steps.map((step) =>
        el(
          "li",
          { class: "list-item", style: step.status === "done" ? "opacity:0.55" : "" },
          el(
            "div",
            {},
            el("div", {}, step.instruction),
            el("div", { class: "faint mono", style: "font-size:11px" }, `${step.scope_label} · ~${step.est_days}d`)
          ),
          step.status === "active"
            ? el("button", { class: "btn btn-small btn-ghost", onclick: () => onAdvance(step.id) }, "Mark done")
            : el("span", { class: `pill ${step.status === "done" ? "pill-ok" : ""}` }, step.status)
        )
      )
    )
  );
}

function submissionCard(submission) {
  const tone = { done: "pill-ok", failed: "pill-bad", processing: "pill-warn", queued: "pill" };
  const rows = [
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el("strong", { style: "text-transform:capitalize" }, submission.submission_type),
      el("span", { class: `pill ${tone[submission.processing_status] || ""}` }, submission.processing_status)
    ),
  ];
  if (submission.submission_type === "audio") {
    rows.push(
      el(
        "div",
        { class: "row", style: "margin-top:6px" },
        submission.is_verification ? el("span", { class: "pill pill-accent" }, "verification") : null,
        submission.is_full_run_through ? el("span", { class: "pill" }, "full run-through") : null,
        submission.duration_sec ? el("span", { class: "faint mono", style: "font-size:11px" }, `${submission.duration_sec}s`) : null
      )
    );
  }
  if (submission.body) {
    rows.push(el("p", { class: "faint", style: "font-size:12.5px;margin:6px 0 0" }, submission.body.slice(0, 220)));
  }
  const interp = submission.interpretation;
  if (interp && interp.available) {
    rows.push(
      el(
        "div",
        { class: "panel", style: "margin-top:8px;background:var(--bg-sunk)" },
        el("div", { class: "stat-label" }, "Interpretation match vs. an idealized reference curve"),
        el(
          "div",
          { class: "row", style: "justify-content:space-between" },
          el("span", { class: "stat", style: "font-size:20px" }, interp.match_score),
          el(
            "span",
            { class: "faint mono", style: "font-size:11px" },
            `avg ${interp.mean_absolute_deviation_bpm} bpm off · rubato variance ${interp.rubato_variance}`
          )
        )
      )
    );
  } else if (interp && !interp.available) {
    rows.push(el("p", { class: "faint", style: "font-size:11.5px;margin-top:6px" }, interp.reason));
  }
  if (submission.analyses && submission.analyses.length) {
    rows.push(
      el(
        "p",
        { class: "faint", style: "font-size:12px;margin-top:6px" },
        submission.analyses[submission.analyses.length - 1].summary
      )
    );
  }
  return el("li", { class: "list-item", style: "flex-direction:column;align-items:stretch" }, ...rows);
}

function submissionFormContent(entry, onSubmitted) {
  const textBody = el("textarea", { rows: "3", placeholder: "Notes from this practice session…" });
  const textSubmit = el(
    "button",
    {
      class: "btn btn-small",
      onclick: async () => {
        if (!textBody.value.trim()) return;
        textSubmit.disabled = true;
        try {
          await api.submitText(entry.id, textBody.value.trim());
          textBody.value = "";
          notify.success("Notes submitted");
          await onSubmitted();
        } catch (error) {
          notify.error(error.detail || "Could not submit those notes");
        } finally {
          textSubmit.disabled = false;
        }
      },
    },
    "Submit notes"
  );

  const pdfInput = el("input", { type: "file", accept: "application/pdf" });
  const pdfSubmit = el(
    "button",
    {
      class: "btn btn-small",
      onclick: async () => {
        const file = pdfInput.files[0];
        if (!file) return notify.error("Choose a PDF first");
        pdfSubmit.disabled = true;
        try {
          await api.submitPdf(entry.id, file);
          notify.success("Score submitted");
          pdfInput.value = "";
          await onSubmitted();
        } catch (error) {
          notify.error(error.detail || "Could not submit that PDF");
        } finally {
          pdfSubmit.disabled = false;
        }
      },
    },
    "Submit score"
  );

  const audioInput = el("input", { type: "file", accept: "audio/*" });
  const fullRun = el("input", { type: "checkbox" });
  const asVerification = el("input", { type: "checkbox", checked: entry.needs_verification || null, disabled: entry.needs_verification || null });
  const tap = tapTempoWidget();
  const audioSubmit = el(
    "button",
    {
      class: "btn btn-small",
      onclick: async () => {
        const file = audioInput.files[0];
        if (!file) return notify.error("Choose a recording first");
        audioSubmit.disabled = true;
        try {
          const submission = await api.submitAudio(entry.id, file, {
            isFullRunThrough: fullRun.checked,
            isVerification: asVerification.checked,
          });
          notify.success("Recording submitted, analysis queued");
          audioInput.value = "";
          await pollSubmission(submission.submission.id).catch(() => null);
          await onSubmitted();
        } catch (error) {
          notify.error(error.detail || "Could not submit that recording");
        } finally {
          audioSubmit.disabled = false;
        }
      },
    },
    "Submit recording"
  );

  return el(
    "div",
    { class: "stack" },
    el("div", { class: "field" }, el("label", {}, "Practice notes"), textBody, textSubmit),
    el("div", { class: "field" }, el("label", {}, "Scanned score (PDF)"), el("div", { class: "row" }, pdfInput, pdfSubmit)),
    el(
      "div",
      { class: "field" },
      el("label", {}, "Recording"),
      el("div", { class: "row", style: "margin-bottom:8px" }, audioInput),
      el(
        "div",
        { class: "row", style: "margin-bottom:8px" },
        el("label", { style: "display:inline-flex;align-items:center;gap:6px;text-transform:none;font-size:13px;margin:0" }, fullRun, "Full run-through"),
        el("label", { style: "display:inline-flex;align-items:center;gap:6px;text-transform:none;font-size:13px;margin:0" }, asVerification, "Verification take")
      ),
      tap.node,
      audioSubmit
    )
  );
}

function submissionsSection(entry, submissions, onChange) {
  const list = el(
    "ul",
    { class: "list" },
    ...(submissions.length ? submissions.map(submissionCard) : [empty("No submissions yet.")])
  );

  const openButton = el(
    "button",
    {
      type: "button",
      class: "btn btn-small btn-solid",
      onclick: () => {
        const content = submissionFormContent(entry, async () => {
          modal.close();
          await onChange();
        });
        const modal = openModal(content, { title: "New submission" });
      },
    },
    "New submission"
  );

  return el(
    "section",
    { class: "panel", style: "margin-top:16px" },
    el("div", { class: "submissions-trigger" }, el("h3", { style: "margin:0" }, "Submissions"), openButton),
    list
  );
}

export async function entryDetailView(outlet, context) {
  const host = el("div", {}, skeletonBlock(5));
  outlet.append(host);

  async function render() {
    const entry = await api.entry(context.params.id);
    const [gate, overview, plans, submissions] = await Promise.all([
      api.gate(context.params.id).catch(() => null),
      api.pieceOverview(entry.piece_id).catch(() => null),
      api.plans(context.params.id).catch(() => []),
      api.submissions(context.params.id).catch(() => []),
    ]);

    const statusSelect = el(
      "select",
      { style: "max-width:190px" },
      ...STATUS_FLOW.map((value) =>
        el("option", { value, selected: value === entry.status || null }, value.replace(/_/g, " "))
      )
    );

    const banner =
      gate && gate.requires_grading && !gate.unlocked
        ? el(
            "div",
            { class: "locked-banner" },
            el("div", { class: "row", style: "justify-content:space-between" },
              el("strong", { style: "font-weight:500" }, "Graded piece"),
              el("span", { class: "pill pill-warn" }, `needs ${gate.pass_score}`)
            ),
            el(
              "p",
              { class: "muted", style: "margin:8px 0 0;font-size:13.5px" },
              `Anything at difficulty ${gate.threshold} or above can only be marked learnt by recording a full run-through and scoring ${gate.pass_score} or higher. ` +
                (gate.best_score != null
                  ? `Your best so far is ${gate.best_score}.`
                  : "You have not submitted a graded run yet.")
            )
          )
        : gate && gate.requires_grading
          ? el(
              "div",
              { class: "locked-banner" },
              el("div", { class: "row", style: "justify-content:space-between" },
                el("strong", { style: "font-weight:500" }, "Graded and cleared"),
                el("span", { class: "pill pill-ok" }, `${gate.best_score}`)
              )
            )
          : null;

    const rawBase = overview?.difficulty_score ?? entry.piece.difficulty_score ?? null;
    const rawYou = overview?.personalized_difficulty ?? null;
    const baseDifficulty = rawBase != null ? Math.round(rawBase) : null;
    const youDifficulty = rawYou != null && Math.round(rawYou) !== baseDifficulty ? Math.round(rawYou) : null;

    host.replaceChildren(
      el(
        "div",
        { class: "row", style: "justify-content:space-between;margin-bottom:18px" },
        el("div", {}, el("h1", { style: "margin:0" }, entry.piece.title), el("p", { class: "muted", style: "margin:4px 0 0" }, entry.piece.composer?.name || "unknown composer")),
        el(
          "div",
          { class: "row" },
          el("button", { type: "button", class: "btn btn-small btn-solid", onclick: () => openPracticeModal() }, "Practice this piece"),
          el("a", { class: "btn btn-ghost btn-small", href: "/repertoire", "data-link": true }, "Back")
        )
      ),
      overview ? pieceCoreStats(overview) : null,
      banner,
      verificationBanner(entry),
      decayBanner(entry, render),
      el(
        "div",
        { class: "grid" },
        el("div", { class: "panel" }, el("div", { class: "stat-label" }, "Status"), el("div", { class: "stat", style: "font-size:20px" }, entry.status.replace(/_/g, " "))),
        el("div", { class: "panel" }, el("div", { class: "stat-label" }, "Tempo"), el("div", { class: "stat", style: "font-size:20px" }, `${entry.current_tempo_bpm ?? "--"} / ${entry.target_tempo_bpm ?? "--"}`)),
        el(
          "div",
          { class: "panel" },
          el("div", { class: "stat-label" }, "Difficulty"),
          el(
            "div",
            { class: "difficulty-dual" },
            youDifficulty != null
              ? el(
                  "div",
                  {},
                  el("div", { class: "stat difficulty-you" }, youDifficulty),
                  el("span", { class: "difficulty-tag" }, "for you")
                )
              : null,
            youDifficulty != null && baseDifficulty != null ? el("span", { class: "difficulty-sep" }, "/") : null,
            baseDifficulty != null
              ? el(
                  "div",
                  {},
                  el("div", { class: "stat difficulty-base" }, baseDifficulty),
                  el("span", { class: "difficulty-tag" }, "baseline")
                )
              : el("div", { class: "stat difficulty-base" }, "--")
          )
        )
      ),
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, "Change status"),
        el(
          "div",
          { class: "row" },
          statusSelect,
          el(
            "button",
            {
              class: "btn btn-small btn-solid",
              onclick: async (event) => {
                event.target.disabled = true;
                try {
                  await api.updateEntry(entry.id, { status: statusSelect.value });
                  notify.success("Status updated");
                  await store.refreshProfile();
                  await render();
                } catch (error) {
                  if (error.status === 423) notify.error(error.detail);
                  else notify.error(error.detail || "Could not update the status");
                  event.target.disabled = false;
                }
              },
            },
            "Save"
          )
        )
      ),
      planPanel(
        entry.id,
        plans[0] || null,
        async () => {
          try {
            await api.buildPlan(entry.id);
            notify.success("Plan built");
            await render();
          } catch (error) {
            notify.error(error.detail || "Could not build a plan");
          }
        },
        async (stepId) => {
          try {
            await api.advanceStep(plans[0].id, stepId);
            await render();
          } catch (error) {
            notify.error(error.detail || "Could not advance that step");
          }
        }
      ),
      submissionsSection(entry, submissions, render),
      overview ? pieceOverview(overview, { heading: false }) : null
    );
  }

  try {
    await render();
  } catch (error) {
    host.replaceChildren(empty(error.detail || "Could not load that entry."));
  }
}
