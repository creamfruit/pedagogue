import { api } from "../api/client.js";
import { disclosure, el, empty, skeletonBlock } from "../lib/dom.js";
import { renderNotation } from "../lib/notation.js";
import { playNotation } from "../lib/synth.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";
import { store } from "../lib/store.js";

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
  { value: "professional", label: "Professional" },
];

const TIERS = ["S", "A", "B", "C", "D"];
const TIER_LABEL = {
  S: "S · mastered",
  A: "A · strong",
  B: "B · solid",
  C: "C · shaky",
  D: "D · weak spot",
};

const STEPS = ["profile", "tier_quiz", "top_ten", "tastes"];
const SEARCH_DEBOUNCE_MS = 280;

// Saving is shown differently from "not ready yet": aria-busy drives the
// striped busy treatment in styles.css, plain disabled is the dashed one.
function setBusy(button, busy) {
  if (busy) {
    button.dataset.idleLabel = button.textContent;
    button.textContent = "Saving…";
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    return;
  }
  if (button.dataset.idleLabel) button.textContent = button.dataset.idleLabel;
  button.removeAttribute("aria-busy");
  button.disabled = false;
}

// Debounced search that Enter can short-circuit. Enter runs the search at once,
// or picks the first result when results for the current text are already up.
// Responses that arrive after a newer search started are dropped.
function wireSearch(input, results, search) {
  let debounce;
  let sequence = 0;
  let shownTerm = null;

  async function run(term) {
    clearTimeout(debounce);
    const ticket = ++sequence;
    if (term.length < 2) {
      shownTerm = null;
      results.replaceChildren();
      return;
    }
    try {
      const items = await search(term);
      if (ticket !== sequence) return;
      shownTerm = term;
      results.replaceChildren(...items);
    } catch (error) {
      if (ticket !== sequence) return;
      shownTerm = null;
      results.replaceChildren(empty(error.detail || "Search failed."));
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(debounce);
    const term = input.value.trim();
    if (term.length < 2) {
      run(term);
      return;
    }
    debounce = setTimeout(() => run(term), SEARCH_DEBOUNCE_MS);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing) return;
    event.preventDefault();
    const term = input.value.trim();
    const first = results.querySelector(".list-item-link");
    if (first && shownTerm === term) {
      first.click();
      return;
    }
    run(term);
  });
}

function resultItem(onPick, ...children) {
  return el(
    "li",
    {
      class: "list-item list-item-link",
      tabindex: "0",
      role: "button",
      onclick: onPick,
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onPick();
        }
      },
    },
    ...children
  );
}

function completedSteps(status) {
  return new Set(
    [
      status.profile_complete ? "profile" : null,
      status.tier_quiz_complete ? "tier_quiz" : null,
      status.top_ten_logged > 0 ? "top_ten" : null,
      status.genres_chosen > 0 || status.composers_chosen > 0 ? "tastes" : null,
    ].filter(Boolean)
  );
}

function stepper(active, done, onSelect) {
  return el(
    "ol",
    { class: "stepper", "aria-label": "Setup progress" },
    ...STEPS.map((step, index) => {
      const state = step === active ? "current" : done.has(step) ? "done" : "upcoming";
      const content = [
        el("span", { class: "stepper-index mono" }, state === "done" ? "✓" : String(index + 1)),
        el("span", { class: "stepper-label" }, step.replace(/_/g, " ")),
      ];
      return el(
        "li",
        { class: `stepper-step stepper-${state}`, "aria-current": state === "current" ? "step" : null },
        state === "done"
          ? el("button", { type: "button", class: "stepper-edit", title: `Change your ${step.replace(/_/g, " ")}`, onclick: () => onSelect(step) }, ...content)
          : content
      );
    })
  );
}

export function tierFromScore(score) {
  if (score === null || score === undefined) return null;
  const value = Number(score);
  const tiers = [["S", 9.0], ["A", 7.2], ["B", 5.5], ["C", 3.5], ["D", 1.5]];
  return tiers.reduce((best, tier) => (Math.abs(tier[1] - value) < Math.abs(best[1] - value) ? tier : best))[0];
}

export function savedTiers(profiles) {
  return new Map(
    (profiles || [])
      .map((profile) => [profile.technique_id, tierFromScore(profile.proficiency_score)])
      .filter(([, tier]) => tier)
  );
}

export async function onboardingView(outlet) {
  const loading = el("div", {}, skeletonBlock(5));
  outlet.append(loading);

  async function load() {
    const [summary, allTechniques] = await Promise.all([api.onboardingSummary(), api.techniques()]);
    return { summary, allTechniques };
  }

  let override = null;

  async function refresh() {
    override = null;
    try {
      const { summary, allTechniques } = await load();
      await draw(summary, allTechniques);
    } catch (error) {
      outlet.replaceChildren(empty(error.detail || "Could not load onboarding."));
    }
  }

  async function draw(summary, allTechniques) {
    const step = override || summary.status.next_step;
    if (step === "done") {
      await store.refreshOnboarding();
      navigate("/");
      return;
    }
    const select = (next) => {
      override = next;
      draw(summary, allTechniques);
    };

    outlet.replaceChildren(
      el(
        "div",
        { class: "onboarding" },
        el("h1", {}, "Set up your studio"),
        el("p", { class: "muted" }, "A few quick steps so the constellation and difficulty math can personalise to you. Finished steps stay editable: select one to change it."),
        stepper(step, completedSteps(summary.status), select),
        step === "profile"
          ? profileStep(summary, refresh)
          : step === "tier_quiz"
            ? tierQuizStep(allTechniques, refresh, { initial: savedTiers(summary.techniques) })
            : step === "top_ten"
              ? topTenStep(refresh, { initial: (summary.top_ten || []).map((entry) => entry.piece) })
              : tastesStep(summary, refresh)
      )
    );
  }

  try {
    const { summary, allTechniques } = await load();
    loading.remove();
    await draw(summary, allTechniques);
  } catch (error) {
    outlet.replaceChildren(empty(error.detail || "Could not load onboarding."));
  }
}

function profileStep(summary, refresh) {
  const level = el(
    "select",
    {},
    el("option", { value: "" }, "Choose a level"),
    ...LEVELS.map((option) =>
      el("option", { value: option.value, selected: summary.user.self_level === option.value || null }, option.label)
    )
  );
  const years = el("input", {
    type: "number",
    min: "0",
    max: "100",
    placeholder: "Years playing",
    value: summary.user.years_playing ?? "",
  });
  const submit = el(
    "button",
    {
      class: "btn",
      type: "submit",
      onclick: async (event) => {
        event.preventDefault();
        if (!level.value) return notify.error("Pick a self-assessed level");
        setBusy(submit, true);
        try {
          await api.updateProfile({
            self_level: level.value,
            years_playing: years.value ? Number(years.value) : null,
          });
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your profile");
          setBusy(submit, false);
        }
      },
    },
    "Continue"
  );

  return el(
    "form",
    { class: "panel panel-accent stack" },
    el("div", { class: "field" }, el("label", {}, "Self-assessed level"), level),
    el("div", { class: "field" }, el("label", {}, "Years playing"), years),
    submit
  );
}

const EXAMPLE_EVENT_BUDGET = 16;

function excerptOf(notation) {
  const measures = [];
  let events = 0;
  for (const measure of notation.measures) {
    if (measures.length && events + measure.notes.length > EXAMPLE_EVENT_BUDGET) break;
    measures.push(measure);
    events += measure.notes.length;
    if (measures.length === 2) break;
  }
  return { ...notation, measures };
}

function techniqueExampleSource() {
  let pending = null;
  return () => {
    if (!pending) {
      pending = api
        .techniqueExamples()
        .then((list) => new Map(list.map((example) => [example.technique_id, example])))
        .catch((error) => {
          pending = null;
          throw error;
        });
    }
    return pending;
  };
}

async function fillTechniqueExample(region, technique, loadExamples) {
  region.replaceChildren(el("p", { class: "faint tier-example-note" }, "Finding a passage that uses this technique…"));
  try {
    const example = (await loadExamples()).get(technique.id);
    if (!example) {
      region.replaceChildren(
        el("p", { class: "faint tier-example-note" }, "No marked passage in the catalogue uses this technique yet.")
      );
      return;
    }
    const notation = await api.passageSightReading(example.passage_id, technique.id);
    const excerpt = excerptOf(notation);
    let playback = null;
    const play = el(
      "button",
      {
        type: "button",
        class: "btn btn-small btn-ghost",
        onclick: () => {
          if (playback) {
            playback.stop();
            playback = null;
            play.textContent = "Play";
            return;
          }
          play.textContent = "Stop";
          playback = playNotation(excerpt, {
            onDone: () => {
              playback = null;
              play.textContent = "Play";
            },
          });
        },
      },
      "Play"
    );
    region.replaceChildren(
      el(
        "div",
        { class: "tier-example-head" },
        el(
          "div",
          {},
          el("strong", { class: "tier-example-piece" }, example.piece_title),
          el(
            "div",
            { class: "faint mono tier-example-meta" },
            [example.composer, example.measure_span, example.label].filter(Boolean).join(" · ")
          )
        ),
        play
      ),
      example.description ? el("p", { class: "tier-example-text" }, example.description) : null,
      el("div", { class: "notation-host tier-example-notation" }, renderNotation(excerpt, { width: 460 })),
      el(
        "p",
        { class: "faint tier-example-note" },
        `Practice pattern built from this passage's ${technique.name.toLowerCase()} · ${notation.key} · ${notation.tempo_bpm} bpm. Not an engraving of the printed score.`
      )
    );
  } catch (error) {
    region.replaceChildren(el("p", { class: "faint tier-example-note" }, error.detail || "Could not load an example right now."));
  }
}

export function tierQuizStep(allTechniques, refresh, { initial = new Map(), submitLabel = "Continue" } = {}) {
  const loadExamples = techniqueExampleSource();
  const assignments = new Map([...initial].filter(([id]) => allTechniques.some((technique) => technique.id === id)));
  const groups = new Map();
  allTechniques.forEach((technique) => {
    if (!groups.has(technique.category)) groups.set(technique.category, []);
    groups.get(technique.category).push(technique);
  });

  const submit = el(
    "button",
    {
      class: "btn",
      type: "submit",
      disabled: true,
      onclick: async (event) => {
        event.preventDefault();
        setBusy(submit, true);
        try {
          const tiers = Array.from(assignments, ([technique_id, tier]) => ({ technique_id, tier }));
          await api.updateTierList(tiers);
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your tier list");
          setBusy(submit, false);
        }
      },
    },
    "Continue"
  );

  function updateProgress() {
    submit.disabled = assignments.size < allTechniques.length;
    submit.textContent = submit.disabled
      ? `Rank every technique (${assignments.size}/${allTechniques.length})`
      : submitLabel;
  }

  const rows = [];
  groups.forEach((techniques, category) => {
    rows.push(el("div", { class: "tier-category" }, el("h3", { style: "margin:0" }, category.replace(/_/g, " "))));
    techniques.forEach((technique) => {
      const buttons = TIERS.map((tier) =>
        el(
          "button",
          {
            type: "button",
            class: "btn btn-small btn-ghost tier-btn",
            "aria-pressed": "false",
            "aria-label": `${technique.name}: ${TIER_LABEL[tier]}`,
            onclick: () => {
              assignments.set(technique.id, tier);
              buttons.forEach((button) => {
                button.classList.remove("tier-btn-active");
                button.setAttribute("aria-pressed", "false");
              });
              buttons[TIERS.indexOf(tier)].classList.add("tier-btn-active");
              buttons[TIERS.indexOf(tier)].setAttribute("aria-pressed", "true");
              updateProgress();
            },
          },
          tier
        )
      );
      const saved = assignments.get(technique.id);
      if (saved) {
        buttons[TIERS.indexOf(saved)].classList.add("tier-btn-active");
        buttons[TIERS.indexOf(saved)].setAttribute("aria-pressed", "true");
      }
      let playbackRegion = null;
      const example = disclosure("?", {
        label: `How ${technique.name} is played, with an example`,
        buttonClass: "tier-help",
        regionClass: "tier-example",
        onFirstOpen: (region) => {
          playbackRegion = region;
          const exampleHost = el("div");
          if (technique.mechanic) region.append(el("p", { class: "tier-example-mechanic" }, technique.mechanic));
          region.append(exampleHost);
          fillTechniqueExample(exampleHost, technique, loadExamples);
        },
        onClose: () => {
          const playing = playbackRegion?.querySelector(".tier-example-head button");
          if (playing && playing.textContent === "Stop") playing.click();
        },
      });
      rows.push(
        el(
          "div",
          { class: "tier-row" },
          el(
            "div",
            { class: "list-item" },
            el(
              "div",
              { class: "tier-name" },
              el("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, el("span", { style: "font-weight:500" }, technique.name), example.button)
            ),
            el("div", { class: "row tier-buttons" }, ...buttons)
          ),
          example.region
        )
      );
    });
  });
  updateProgress();

  return el(
    "div",
    { class: "panel panel-accent stack tier-quiz" },
    el(
      "div",
      {},
      el("p", { class: "muted", style: "margin:0 0 6px" }, "Rank every technique against the tier list. This colours requirements on every piece and drives your sight-reading forge."),
      el(
        "p",
        { class: "tier-legend mono" },
        TIERS.map((tier) => TIER_LABEL[tier]).join("   ·   ")
      ),
      el("p", { class: "faint", style: "margin:0;font-size:12.5px" }, "Tap ? beside a technique to see how it's played and hear an example.")
    ),
    el("div", { class: "stack tier-rows" }, ...rows),
    el("div", { class: "sticky-actions" }, submit)
  );
}

function topTenStep(refresh, { initial = [] } = {}) {
  const search = el("input", { type: "search", placeholder: "Search the catalog, e.g. Chopin etude" });
  const results = el("ul", { class: "list" });
  const chosen = initial.filter(Boolean).slice(0, 10);
  const chosenList = el("ul", { class: "list" });

  function renderChosen() {
    chosenList.replaceChildren(
      ...chosen.map((piece, index) =>
        el(
          "li",
          { class: "list-item" },
          el("div", {}, `${index + 1}. ${piece.title}`, el("div", { class: "faint", style: "font-size:12px" }, piece.composer?.name || "unknown")),
          el(
            "button",
            {
              type: "button",
              class: "btn btn-small btn-ghost",
              onclick: () => {
                chosen.splice(index, 1);
                renderChosen();
              },
            },
            "Remove"
          )
        )
      )
    );
    submit.disabled = chosen.length === 0;
  }

  const submit = el(
    "button",
    {
      class: "btn",
      type: "submit",
      disabled: true,
      onclick: async (event) => {
        event.preventDefault();
        setBusy(submit, true);
        try {
          const pieces = chosen.map((piece, index) => ({ rank: index + 1, piece_id: piece.id }));
          await api.updateTopTen(pieces);
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your top ten");
          setBusy(submit, false);
        }
      },
    },
    "Continue"
  );

  wireSearch(search, results, async (term) => {
    const pieces = await api.searchPieces(term, 10);
    return pieces
      .filter((piece) => !chosen.some((item) => item.id === piece.id))
      .map((piece) =>
        resultItem(
          () => {
            if (chosen.length >= 10) return notify.error("That is ten already");
            chosen.push(piece);
            renderChosen();
            results.replaceChildren();
            search.value = "";
            search.focus();
          },
          el("div", {}, piece.title, el("div", { class: "faint", style: "font-size:12px" }, piece.composer?.name || "unknown"))
        )
      );
  });

  renderChosen();

  return el(
    "div",
    { class: "panel panel-accent stack" },
    el("p", { class: "muted", style: "margin:0" }, "List up to ten pieces you already know or love. These seed your first constellation."),
    el("div", { class: "field" }, el("label", {}, "Find a piece"), search),
    results,
    el("h3", {}, "Your top ten"),
    chosenList,
    submit
  );
}

function tastesStep(summary, refresh) {
  const genreChips = [];
  const chosenGenres = new Set((summary.genres || []).map((g) => g.id));
  const composerSearch = el("input", { type: "search", placeholder: "Search composers" });
  const composerResults = el("ul", { class: "list" });
  const chosenComposers = [...(summary.composers || [])];
  const chosenComposerList = el("ul", { class: "list" });

  function renderComposers() {
    chosenComposerList.replaceChildren(
      ...chosenComposers.map((composer, index) =>
        el(
          "li",
          { class: "list-item" },
          el("div", {}, composer.name),
          el(
            "button",
            {
              type: "button",
              class: "btn btn-small btn-ghost",
              onclick: () => {
                chosenComposers.splice(index, 1);
                renderComposers();
              },
            },
            "Remove"
          )
        )
      )
    );
  }
  renderComposers();

  wireSearch(composerSearch, composerResults, async (term) => {
    const composers = await api.searchComposers(term);
    return composers
      .filter((composer) => !chosenComposers.some((item) => item.id === composer.id))
      .map((composer) =>
        resultItem(() => {
          chosenComposers.push(composer);
          renderComposers();
          composerResults.replaceChildren();
          composerSearch.value = "";
          composerSearch.focus();
        }, composer.name)
      );
  });

  const finish = el(
    "button",
    {
      class: "btn",
      type: "submit",
      onclick: async (event) => {
        event.preventDefault();
        setBusy(finish, true);
        try {
          await Promise.all([
            api.updateGenres(Array.from(chosenGenres)),
            api.updateComposers(chosenComposers.map((composer, index) => ({ composer_id: composer.id, rank: index + 1 }))),
          ]);
          notify.success("Studio is set up");
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your tastes");
          setBusy(finish, false);
        }
      },
    },
    "Finish setup"
  );

  const genreHost = el("div", { class: "row" }, el("span", { class: "faint" }, "Loading genres…"));
  api
    .genres()
    .then((genres) => {
      genreHost.replaceChildren(
        ...genres.map((genre) => {
          const chip = el(
            "button",
            {
              type: "button",
              class: `pill pill-toggle${chosenGenres.has(genre.id) ? " pill-accent" : ""}`,
              "aria-pressed": chosenGenres.has(genre.id) ? "true" : "false",
              onclick: () => {
                if (chosenGenres.has(genre.id)) chosenGenres.delete(genre.id);
                else chosenGenres.add(genre.id);
                chip.classList.toggle("pill-accent", chosenGenres.has(genre.id));
                chip.setAttribute("aria-pressed", chosenGenres.has(genre.id) ? "true" : "false");
              },
            },
            genre.name
          );
          genreChips.push(chip);
          return chip;
        })
      );
    })
    .catch(() => genreHost.replaceChildren(empty("Could not load genres.")));

  return el(
    "div",
    { class: "panel panel-accent stack" },
    el("p", { class: "muted", style: "margin:0" }, "Optional, but it sharpens recommendations. Pick the genres and composers you gravitate to."),
    el("h3", {}, "Genres"),
    genreHost,
    el("h3", {}, "Favorite composers"),
    el("div", { class: "field" }, composerSearch),
    composerResults,
    chosenComposerList,
    finish
  );
}
