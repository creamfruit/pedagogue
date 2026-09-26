import { api, pollSubmission } from "../api/client.js";
import { difficultyPair, pieceOverview } from "../components/overview.js";
import { el, empty, openModal, optionCard, reveal, sectionBlock, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";
import { STATUS_LABEL, STATUS_ORDER, lastPractisedLabel, tempoBar } from "../lib/entries.js";
import { navigate } from "../router.js";
import { store } from "../lib/store.js";

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

  const search = el("input", { type: "search", placeholder: "Search your pieces", value: query, "aria-label": "Search your pieces" });
  const select = el(
    "select",
    { "aria-label": "Status" },
    el("option", { value: "" }, "All statuses"),
    ...STATUSES.map((s) => el("option", { value: s, selected: s === statusFilter || null }, s.replace(/_/g, " ")))
  );
  const genreSelect = el("select", { "aria-label": "Genre" }, el("option", { value: "" }, "All genres"));
  const minInput = el("input", { type: "number", min: "0", max: "100", placeholder: "Min", value: minDifficulty, "aria-label": "Minimum difficulty" });
  const maxInput = el("input", { type: "number", min: "0", max: "100", placeholder: "Max", value: maxDifficulty, "aria-label": "Maximum difficulty" });
  const composerSearch = el("input", { type: "search", placeholder: "Composer", value: composerName, "aria-label": "Composer" });
  const composerResults = el("ul", { class: "list composer-results" });
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

  const advancedActive = [genreFilter, composerFilter, minDifficulty, maxDifficulty].filter(Boolean).length;
  const anyActive = advancedActive + [query, statusFilter].filter(Boolean).length;
  const moreFilters = reveal(
    advancedActive ? `More filters (${advancedActive} active)` : "More filters",
    el(
      "div",
      { class: "filter-extra" },
      el("div", { class: "field" }, el("label", {}, "Genre"), genreSelect),
      el("div", { class: "field composer-field" }, el("label", {}, "Composer"), composerSearch, composerResults),
      el(
        "div",
        { class: "field" },
        el("label", {}, "Difficulty (0–100)"),
        el("div", { class: "row", style: "flex-wrap:nowrap;gap:8px" }, minInput, el("span", { class: "faint" }, "to"), maxInput)
      )
    ),
    { open: advancedActive > 0 }
  );

  outlet.append(
    el(
      "div",
      { class: "page-head" },
      el("h1", { style: "margin:0" }, "Repertoire"),
      el("a", { class: "btn", href: "/repertoire/new", "data-link": true }, "Add a piece")
    ),
    el(
      "div",
      { class: "filter-bar" },
      el("div", { class: "filter-main" }, search, select),
      el(
        "div",
        { class: "row", style: "gap:18px" },
        moreFilters.button,
        anyActive
          ? el("a", { class: "reveal-link", href: "/repertoire", "data-link": true }, "Clear filters")
          : null
      ),
      moreFilters.region
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
    const groups = STATUS_ORDER.map((status) => ({ status, items: page.items.filter((entry) => entry.status === status) })).filter(
      (group) => group.items.length
    );
    listHost.append(
      el("p", { class: "faint mono", style: "font-size:12px" }, `${page.meta.total} piece${page.meta.total === 1 ? "" : "s"}`),
      el("div", { class: "status-groups" }, ...groups.map((group) => statusGroup(group, { collapsed: !statusFilter && COLLAPSED_GROUPS.has(group.status) })))
    );
  } catch (error) {
    listHost.replaceChildren(empty(error.detail || "Could not load your repertoire."));
  }
}

const COLLAPSED_GROUPS = new Set(["wishlist", "retired"]);
const ACTIVE_GROUPS = new Set(["learning", "polishing"]);

function entryListItem(entry) {
  const active = ACTIVE_GROUPS.has(entry.status);
  return el(
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
      { style: "min-width:0;flex:1" },
      el("div", { style: "font-weight:500" }, entry.piece.title),
      el(
        "div",
        { class: "faint", style: "font-size:12.5px" },
        [entry.piece.composer?.name || "unknown composer", active ? lastPractisedLabel(entry.last_practiced_at) : null].filter(Boolean).join(" · ")
      ),
      active ? tempoBar(entry) : null
    ),
    el(
      "div",
      { class: "row entry-meta" },
      entry.is_top_ten ? el("span", { class: "pill pill-accent" }, "top ten") : null,
      entry.needs_verification ? el("span", { class: "pill pill-warn" }, "unverified") : null,
      entry.decay_level >= 0.85 ? el("span", { class: "pill pill-frozen" }, "frozen") : null,
      entry.piece.difficulty_score
        ? el("span", { class: "entry-difficulty mono", title: "Catalogue difficulty (0–100)" }, entry.piece.difficulty_score)
        : null
    )
  );
}

function statusGroup(group, { collapsed }) {
  const list = el("ul", { class: "list" }, ...group.items.map(entryListItem));
  const topTen = group.items.filter((entry) => entry.is_top_ten).length;
  const title = [STATUS_LABEL[group.status], group.items.length, topTen ? `${topTen} in your top ten` : null].filter(Boolean).join(" · ");
  if (!collapsed) {
    return el("section", { class: "status-group", "aria-label": STATUS_LABEL[group.status] }, el("h2", { class: "status-group-title" }, title), list);
  }
  const control = reveal(title, list);
  control.button.classList.add("status-group-toggle");
  return el("section", { class: "status-group", "aria-label": STATUS_LABEL[group.status] }, control.button, control.region);
}

function catalogSearchPanel(statusSelect) {
  const search = el("input", { type: "search", placeholder: "Search the catalog, e.g. Chopin etude" });
  const results = el("ul", { class: "list" });

  let selected = null;
  const confirm = el(
    "button",
    {
      class: "btn",
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

const SOURCE_LABELS = { openopus: "OpenOpus", musicbrainz: "MusicBrainz" };

function externalSearchPanel(statusSelect) {
  const search = el("input", { type: "search", placeholder: "Composer, work or both, e.g. Rachmaninoff prelude" });
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
                  importButton.textContent = "Importing…";
                  try {
                    const piece = await api.importExternalPiece({
                      external_ref: candidate.external_ref,
                      title: candidate.title,
                      composer_name: candidate.composer_name,
                    });
                    const entry = await api.createEntry({ piece_id: piece.id, status: statusSelect.value });
                    notify.success(`${entry.piece.title} added. Its techniques and notes are being written in the background.`);
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
                el(
                  "div",
                  { class: "row", style: "gap:8px;margin-top:2px" },
                  el("span", { class: "faint", style: "font-size:12.5px" }, [candidate.composer_name, candidate.epoch].filter(Boolean).join(" · ")),
                  ...(candidate.sources?.length ? candidate.sources : [candidate.source]).map((source) =>
                    el("span", { class: "source-tag mono" }, SOURCE_LABELS[source] || source)
                  )
                )
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
    el(
      "p",
      { class: "faint", style: "margin:0;font-size:12.5px" },
      "Searches two open classical databases, OpenOpus and MusicBrainz, as one list. Importing adds the piece straight away; its techniques, difficulty and notes are written in the background, once per piece."
    ),
    el("div", { class: "field" }, el("label", {}, "Search the open catalogues"), search),
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
      class: "btn",
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

function openRecordingForm() {
  const toggle = document.querySelector("#practice-recordings .reveal-btn");
  if (!toggle) return;
  if (toggle.getAttribute("aria-expanded") !== "true") toggle.click();
  toggle.scrollIntoView({ behavior: "smooth", block: "center" });
  document.querySelector("#practice-recordings input[type=file]")?.focus({ preventScroll: true });
}

function requirementsChecklist(entry, gate) {
  const items = [];
  if (gate && gate.requires_grading) {
    const best = gate.best_score != null ? ` Your best so far is ${gate.best_score}.` : " No graded run yet.";
    items.push({
      done: gate.unlocked,
      title: gate.unlocked ? `Graded run cleared (${gate.best_score})` : `Score ${gate.pass_score}+ on a graded full run-through`,
      detail: gate.unlocked
        ? "You can mark this piece learnt."
        : `Pieces at difficulty ${gate.threshold} or above count as learnt only after a graded run.${best}`,
    });
  }
  if (entry.needs_verification || (entry.is_verified && entry.piece.difficulty_score >= 70)) {
    items.push({
      done: !entry.needs_verification,
      title: entry.needs_verification ? "Submit a verification take" : "Verification take submitted",
      detail: entry.needs_verification
        ? "Until then this piece is a hollow, dashed star in your constellation."
        : "Your star is lit in the constellation.",
    });
  }
  if (!items.length) return null;
  const remaining = items.filter((item) => !item.done).length;
  return el(
    "section",
    { class: `requirements ${remaining ? "requirements-open" : "requirements-done"}`, "aria-label": "Before this counts as learnt" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el("strong", { style: "font-weight:500" }, remaining ? "Before this counts as learnt" : "Requirements met"),
      el("span", { class: `pill ${remaining ? "pill-warn" : "pill-ok"}` }, `${items.length - remaining} of ${items.length} done`)
    ),
    el(
      "ul",
      { class: "requirement-list" },
      ...items.map((item) =>
        el(
          "li",
          { class: `requirement ${item.done ? "requirement-done" : ""}` },
          el("span", { class: "requirement-mark", "aria-hidden": "true" }, item.done ? "✓" : ""),
          el("div", {}, el("div", { class: "requirement-title" }, item.title), el("div", { class: "requirement-detail" }, item.detail))
        )
      )
    ),
    remaining
      ? el("button", { type: "button", class: "btn btn-small", style: "margin-top:var(--space-3)", onclick: openRecordingForm }, "Add a recording")
      : null
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
      el("span", { class: "pill pill-frozen" }, `${Math.round(entry.decay_level * 100)}%`)
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

function planStepRow(step, onAdvance) {
  return el(
    "li",
    { class: "flat-row", style: step.status === "done" ? "opacity:0.55" : "" },
    el(
      "div",
      {},
      el("div", {}, step.instruction),
      el(
        "div",
        { class: "faint mono", style: "font-size:11px" },
        [step.scope_label, step.est_days != null ? `~${step.est_days}d` : null].filter(Boolean).join(" · ")
      )
    ),
    step.status === "active"
      ? el("button", { class: "btn btn-small btn-ghost", onclick: () => onAdvance(step.id) }, "Mark done")
      : el("span", { class: `pill ${step.status === "done" ? "pill-ok" : ""}` }, step.status)
  );
}

const PLAN_PREVIEW_STEPS = 3;

function planPanel(entryId, plan, onBuild, onAdvance) {
  if (!plan) {
    return sectionBlock(
      "Guided learning path",
      { caption: "A step-by-step plan for this piece, ordered from its gentlest movement or its hardest passages." },
      el("button", { class: "btn btn-small", onclick: onBuild }, "Build a plan")
    );
  }
  const active = plan.steps.findIndex((step) => step.status !== "done");
  const from = Math.max(0, active === -1 ? plan.steps.length - PLAN_PREVIEW_STEPS : active);
  const preview = plan.steps.slice(from, from + PLAN_PREVIEW_STEPS);
  const hidden = plan.steps.length - preview.length;
  return sectionBlock(
    "Guided learning path",
    {
      caption: plan.rationale || null,
      action: el("span", { class: "pill mono" }, `${Math.round(plan.progress * 100)}%`),
    },
    el("ol", { class: "flat-list" }, ...preview.map((step) => planStepRow(step, onAdvance))),
    hidden > 0
      ? (() => {
          const control = reveal(`All ${plan.steps.length} steps`, () =>
            el("ol", { class: "flat-list" }, ...plan.steps.map((step) => planStepRow(step, onAdvance)))
          );
          return [control.button, control.region];
        })()
      : null
  );
}

const SUBMISSION_LABELS = { audio: "Recording", text: "Practice notes", pdf: "Scanned score" };

function submissionDate(submission) {
  if (!submission.created_at) return null;
  const date = new Date(submission.created_at);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const COACH_POLL_MS = 3000;
const COACH_POLL_LIMIT = 10;
const COACH_STALE_MS = 2 * 60 * 1000;

function coachNotesBody(feedback) {
  const details = [
    ...(feedback.focus || []).map((item) =>
      el(
        "div",
        { class: "coach-focus" },
        el("strong", { class: "coach-focus-passage" }, item.passage),
        item.why ? el("p", { class: "coach-text" }, item.why) : null,
        el("p", { class: "section-cue", style: "margin-top:6px;padding-top:6px" }, el("span", { class: "cue-tag" }, "Drill"), item.drill)
      )
    ),
    feedback.next_session
      ? el("p", { class: "coach-text" }, el("span", { class: "cue-tag" }, "Next session"), feedback.next_session)
      : null,
  ].filter(Boolean);
  const more = details.length ? reveal(`${(feedback.focus || []).length} focus passage${(feedback.focus || []).length === 1 ? "" : "s"} and next session`, details) : null;
  return [
    el("p", { class: "coach-summary" }, feedback.summary),
    more ? more.button : null,
    more ? more.region : null,
    el(
      "p",
      { class: "faint", style: "font-size:11px;margin:8px 0 0" },
      "Written from your technique tiers, this piece's marked passages and your practice notes. The audio itself isn't analysed yet."
    ),
  ];
}

function coachNotes(submission) {
  const host = el("div", { class: "coach-notes" }, el("div", { class: "stat-label" }, "Coach notes"));
  const body = el("div");
  host.append(body);
  let polls = 0;

  function draw(current) {
    const feedback = current.coach_feedback;
    if (current.processing_status !== "done") {
      body.replaceChildren(el("p", { class: "faint coach-text" }, "Coach notes appear once the recording has been processed."));
      return false;
    }
    const age = Date.now() - new Date(current.created_at).getTime();
    if (!feedback && age > COACH_STALE_MS) {
      body.replaceChildren(el("p", { class: "faint coach-text" }, "No coach notes were written for this take."));
      return false;
    }
    if (!feedback || feedback.status === "running") {
      body.replaceChildren(el("p", { class: "faint coach-text" }, "Your coach notes are being written…"));
      return true;
    }
    if (feedback.status !== "done") {
      body.replaceChildren(el("p", { class: "faint coach-text" }, "Coach notes couldn't be written for this take."));
      return false;
    }
    body.replaceChildren(...coachNotesBody(feedback).filter(Boolean));
    return false;
  }

  async function poll() {
    if (!host.isConnected || polls >= COACH_POLL_LIMIT) return;
    polls += 1;
    try {
      const current = await api.submission(submission.id);
      if (draw(current)) setTimeout(poll, COACH_POLL_MS);
    } catch {
      setTimeout(poll, COACH_POLL_MS);
    }
  }

  if (draw(submission)) setTimeout(poll, COACH_POLL_MS);
  return host;
}

function submissionCard(submission) {
  const tone = { done: "pill-ok", failed: "pill-bad", processing: "pill-warn", queued: "pill" };
  const date = submissionDate(submission);
  const rows = [
    el(
      "div",
      { class: "row", style: "justify-content:space-between" },
      el(
        "span",
        { class: "row", style: "gap:10px" },
        el("strong", {}, SUBMISSION_LABELS[submission.submission_type] || submission.submission_type),
        date ? el("span", { class: "faint mono", style: "font-size:11px" }, date) : null
      ),
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
    rows.push(coachNotes(submission));
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
          el("span", { class: "stat", style: "font-size:20px" }, interp.match_score ?? "--"),
          el(
            "span",
            { class: "faint mono", style: "font-size:11px" },
            [
              interp.mean_absolute_deviation_bpm != null ? `avg ${interp.mean_absolute_deviation_bpm} bpm off` : null,
              interp.rubato_variance != null ? `rubato variance ${interp.rubato_variance}` : null,
            ]
              .filter(Boolean)
              .join(" · ")
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
  return el("li", { class: "flat-row flat-row-stack" }, ...rows);
}

function submissionList(items, emptyText) {
  return el("ul", { class: "flat-list" }, ...(items.length ? items.map(submissionCard) : [el("li", { class: "faint", style: "font-size:13px" }, emptyText)]));
}

function recordingPanel(entry, recordings, onChange, { openForm = false } = {}) {
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
          await onChange();
        } catch (error) {
          notify.error(error.detail || "Could not submit that recording");
        } finally {
          audioSubmit.disabled = false;
        }
      },
    },
    "Submit recording"
  );

  const form = reveal(
    "Add a recording",
    el(
      "div",
      { class: "submission-form" },
      el("label", {}, "Recording file"),
      el("div", { class: "row", style: "margin-bottom:8px" }, audioInput),
      el(
        "div",
        { class: "row", style: "margin-bottom:8px" },
        el("label", { class: "check-label" }, fullRun, "Full run-through"),
        el("label", { class: "check-label" }, asVerification, "Verification take")
      ),
      tap.node,
      el("div", { style: "margin-top:12px" }, audioSubmit)
    ),
    { open: openForm }
  );

  return sectionBlock(
    "Practice recordings",
    {
      caption: "Audio takes, scored for tempo and interpretation. Verification takes and graded run-throughs go here.",
      className: "submission-panel submission-panel-recording",
      id: "practice-recordings",
    },
    submissionList(recordings, "No recordings yet."),
    form.button,
    form.region
  );
}

function writtenSubmissionPanel(entry, written, onChange) {
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
          await onChange();
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
          await onChange();
        } catch (error) {
          notify.error(error.detail || "Could not submit that PDF");
        } finally {
          pdfSubmit.disabled = false;
        }
      },
    },
    "Upload score"
  );

  const form = reveal(
    "Add notes or a score",
    el(
      "div",
      { class: "submission-form" },
      el("div", { class: "field" }, el("label", {}, "Practice notes"), textBody, el("div", { style: "margin-top:8px" }, textSubmit)),
      el("div", { class: "field", style: "margin-bottom:0" }, el("label", {}, "Scanned score (PDF)"), el("div", { class: "row" }, pdfInput, pdfSubmit))
    )
  );

  return sectionBlock(
    "Notes & scores",
    {
      caption: "Written practice notes and scanned sheet music, read for bar numbers and techniques.",
      className: "submission-panel",
    },
    submissionList(written, "No notes or scores yet."),
    form.button,
    form.region
  );
}

function submissionSections(entry, submissions, onChange, { recordingFirst = false } = {}) {
  const recordings = submissions.filter((submission) => submission.submission_type === "audio");
  const written = submissions.filter((submission) => submission.submission_type !== "audio");
  return [
    recordingPanel(entry, recordings, onChange, { openForm: recordingFirst && recordings.length === 0 }),
    writtenSubmissionPanel(entry, written, onChange),
  ];
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
      { class: "select-compact" },
      ...STATUS_FLOW.map((value) =>
        el("option", { value, selected: value === entry.status || null }, value.replace(/_/g, " "))
      )
    );

    const statusSave = el(
      "button",
      {
        class: "btn btn-small",
        disabled: true,
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
    );
    statusSelect.setAttribute("aria-label", "Status");
    statusSelect.addEventListener("change", () => {
      statusSave.disabled = statusSelect.value === entry.status;
    });

    const byline = [
      entry.piece.composer?.name || "unknown composer",
      overview?.catalog_number,
      overview?.key_signature,
    ].filter(Boolean).join(" · ");

    const notices = [requirementsChecklist(entry, gate), decayBanner(entry, render)].filter(Boolean);
    const needsTake = Boolean(entry.needs_verification || (gate && gate.requires_grading && !gate.unlocked));

    const summary = el(
      "section",
      { class: "panel summary-bar", "aria-label": "Where this piece stands" },
      el(
        "div",
        { class: "summary-cell" },
        el("div", { class: "stat-label" }, "Status"),
        el("div", { class: "row summary-status" }, statusSelect, statusSave)
      ),
      el(
        "div",
        { class: "summary-cell" },
        el("div", { class: "stat-label" }, "Tempo · current / target"),
        el("div", { class: "stat", style: "font-size:20px" }, `${entry.current_tempo_bpm ?? "--"} / ${entry.target_tempo_bpm ?? "--"}`)
      ),
      el(
        "div",
        { class: "summary-cell" },
        el("div", { class: "stat-label" }, "Difficulty"),
        difficultyPair(overview?.personalized_difficulty, overview?.difficulty_score ?? entry.piece.difficulty_score, {
          band: overview?.difficulty_band,
        }) || el("div", { class: "stat", style: "font-size:20px" }, "--")
      )
    );

    const plan = planPanel(
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
    );

    const sections = [
      el(
        "div",
        { class: "page-head" },
        el("div", {}, el("h1", { style: "margin:0" }, entry.piece.title), el("p", { class: "muted", style: "margin:4px 0 0" }, byline)),
        el(
          "div",
          { class: "row" },
          el("button", { type: "button", class: "btn btn-small", onclick: () => openPracticeModal() }, "Practice this piece"),
          el("a", { class: "btn btn-ghost btn-small", href: "/repertoire", "data-link": true }, "Back")
        )
      ),
      summary,
      notices.length ? el("div", { class: "notice-stack" }, ...notices) : null,
      el(
        "div",
        { class: "detail-layout" },
        el("div", { class: "detail-aside" }, plan, ...submissionSections(entry, submissions, render, { recordingFirst: needsTake })),
        el("div", { class: "detail-main" }, overview ? pieceOverview(overview, { heading: false, difficulty: false }) : null)
      ),
    ];
    host.replaceChildren(...sections.filter(Boolean));
  }

  try {
    await render();
  } catch (error) {
    host.replaceChildren(empty(error.detail || "Could not load that entry."));
  }
}
