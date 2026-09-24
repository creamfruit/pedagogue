import { api } from "../api/client.js";
import { el, empty, optionCard, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";
import { store } from "../lib/store.js";
import { techniqueGlyph } from "../lib/notation.js";

const SEED_TERMS = ["Chopin", "Bach", "Debussy", "Beethoven", "Rachmaninoff", "Mozart", "Joplin", "Ravel", "Liszt", "Satie"];

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

function stepper(active) {
  return el(
    "div",
    { class: "row", style: "margin-bottom:22px" },
    ...STEPS.map((step, index) =>
      el(
        "span",
        { class: `pill${step === active ? " pill-accent" : ""}` },
        `${index + 1}. ${step.replace(/_/g, " ")}`
      )
    )
  );
}

export async function onboardingView(outlet) {
  const loading = el("div", {}, skeletonBlock(5));
  outlet.append(loading);
  
  async function load() {
    const [summary, allTechniques] = await Promise.all([api.onboardingSummary(), api.techniques()]);
    return { summary, allTechniques };
  }
  
  async function refresh() {
    try {
      const { summary, allTechniques } = await load();
      await draw(summary, allTechniques);
    } catch (error) {
      outlet.replaceChildren(empty(error.detail || "Could not load onboarding."));
    }
  }
  
  async function draw(summary, allTechniques) {
    const step = summary.status.next_step;
    if (step === "done") {
      await store.refreshOnboarding();
      navigate("/");
      return;
    }
    
    outlet.replaceChildren(
      el("h1", {}, "Set up your studio"),
      el("p", { class: "muted" }, "A few quick steps so the constellation and difficulty math can personalize to you."),
      stepper(step),
      step === "profile"
        ? profileStep(summary, refresh)
        : step === "tier_quiz"
          ? tierQuizStep(allTechniques, refresh)
          : step === "top_ten"
            ? topTenStep(refresh)
            : tastesStep(summary, refresh)
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
      class: "btn btn-solid",
      type: "submit",
      onclick: async (event) => {
        event.preventDefault();
        if (!level.value) return notify.error("Pick a self-assessed level");
        submit.disabled = true;
        try {
          await api.updateProfile({
            self_level: level.value,
            years_playing: years.value ? Number(years.value) : null,
          });
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your profile");
          submit.disabled = false;
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

function tierQuizStep(allTechniques, refresh) {
  const assignments = new Map();
  const groups = new Map();
  allTechniques.forEach((technique) => {
    if (!groups.has(technique.category)) groups.set(technique.category, []);
    groups.get(technique.category).push(technique);
  });

  const submit = el(
    "button",
    {
      class: "btn btn-solid",
      type: "submit",
      disabled: true,
      onclick: async (event) => {
        event.preventDefault();
        submit.disabled = true;
        try {
          const tiers = Array.from(assignments, ([technique_id, tier]) => ({ technique_id, tier }));
          await api.updateTierList(tiers);
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your tier list");
          submit.disabled = false;
        }
      },
    },
    "Continue"
  );

  function updateProgress() {
    submit.disabled = assignments.size < allTechniques.length;
    submit.textContent = submit.disabled
      ? `Rank every technique (${assignments.size}/${allTechniques.length})`
      : "Continue";
  }

  const rows = [];
  groups.forEach((techniques, category) => {
    rows.push(el("h3", {}, category.replace(/_/g, " ")));
    techniques.forEach((technique) => {
      const buttons = TIERS.map((tier) =>
        el(
          "button",
          {
            type: "button",
            class: "btn btn-small btn-ghost tier-btn",
            onclick: () => {
              assignments.set(technique.id, tier);
              buttons.forEach((button) => button.classList.remove("tier-btn-active"));
              buttons[TIERS.indexOf(tier)].classList.add("tier-btn-active");
              updateProgress();
            },
          },
          tier
        )
      );
      rows.push(
        el(
          "div",
          { class: "list-item" },
          el(
            "div",
            { class: "technique-row-head" },
            techniqueGlyph(technique.category),
            el(
              "div",
              {},
              el("div", { style: "font-weight:500" }, technique.name),
              technique.mechanic ? el("div", { class: "faint", style: "font-size:12px" }, technique.mechanic) : null
            )
          ),
          el("div", { class: "row tier-buttons" }, ...buttons)
        )
      );
    });
  });

  return el(
    "div",
    { class: "panel panel-accent stack" },
    el("p", { class: "muted", style: "margin:0" }, "Rank every technique against the tier list. This colors requirements on every piece and drives your sight-reading forge."),
    el("div", { class: "row", style: "font-size:11px" }, ...TIERS.map((tier) => el("span", { class: "pill" }, TIER_LABEL[tier]))),
    el("div", { class: "stack", style: "max-height:520px;overflow:auto" }, ...rows),
    submit
  );
}

function topTenStep(refresh) {
  const search = el("input", { type: "search", placeholder: "Search the catalog, e.g. Chopin etude" });
  const results = el("ul", { class: "list" });
  const seedHost = el("div", { class: "option-grid" }, el("span", { class: "faint" }, "Loading suggestions…"));
  const chosen = [];
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
      class: "btn btn-solid",
      type: "submit",
      disabled: true,
      onclick: async (event) => {
        event.preventDefault();
        submit.disabled = true;
        try {
          const pieces = chosen.map((piece, index) => ({ rank: index + 1, piece_id: piece.id }));
          await api.updateTopTen(pieces);
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your top ten");
          submit.disabled = false;
        }
      },
    },
    "Continue"
  );

  function pickPiece(piece) {
    if (chosen.some((item) => item.id === piece.id)) return;
    if (chosen.length >= 10) return notify.error("That is ten already");
    chosen.push(piece);
    renderChosen();
    renderSeedPool();
  }

  async function renderSeedPool() {
    try {
      const batches = await Promise.all(
        SEED_TERMS.map((term) => api.searchPieces(term, 3).catch(() => []))
      );
      const seen = new Set(chosen.map((item) => item.id));
      const pool = [];
      batches.flat().forEach((piece) => {
        if (seen.has(piece.id)) return;
        seen.add(piece.id);
        pool.push(piece);
      });
      if (!pool.length) {
        seedHost.replaceChildren(empty("No suggestions available right now."));
        return;
      }
      seedHost.replaceChildren(
        ...pool.slice(0, 12).map((piece) =>
          optionCard({
            icon: "\u{1F3B9}",
            title: piece.title,
            description: piece.composer?.name || "unknown composer",
            onSelect: () => pickPiece(piece),
          })
        )
      );
    } catch {
      seedHost.replaceChildren(empty("Could not load suggestions."));
    }
  }

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
        const pieces = await api.searchPieces(term, 10);
        results.replaceChildren(
          ...pieces
            .filter((piece) => !chosen.some((item) => item.id === piece.id))
            .map((piece) =>
              el(
                "li",
                {
                  class: "list-item",
                  style: "cursor:pointer",
                  onclick: () => {
                    pickPiece(piece);
                    results.replaceChildren();
                    search.value = "";
                  },
                },
                el("div", {}, piece.title, el("div", { class: "faint", style: "font-size:12px" }, piece.composer?.name || "unknown"))
              )
            )
        );
      } catch (error) {
        results.replaceChildren(empty(error.detail || "Search failed."));
      }
    }, 280);
  });

  renderChosen();
  renderSeedPool();

  return el(
    "div",
    { class: "panel panel-accent stack" },
    el("p", { class: "muted", style: "margin:0" }, "Pick up to ten pieces you know or love. These seed your first constellation."),
    el("h3", {}, "Suggestions"),
    seedHost,
    el("div", { class: "field" }, el("label", {}, "Or search directly"), search),
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

  let liveComposerResults = [];

  function chooseComposer(composer) {
    chosenComposers.push(composer);
    renderComposers();
    composerResults.replaceChildren();
    liveComposerResults = [];
    composerSearch.value = "";
  }

  composerSearch.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (liveComposerResults.length) chooseComposer(liveComposerResults[0]);
  });

  let debounce;
  composerSearch.addEventListener("input", () => {
    clearTimeout(debounce);
    const term = composerSearch.value.trim();
    if (term.length < 2) {
      composerResults.replaceChildren();
      liveComposerResults = [];
      return;
    }
    debounce = setTimeout(async () => {
      try {
        const composers = await api.searchComposers(term);
        const candidates = composers.filter((composer) => !chosenComposers.some((item) => item.id === composer.id));
        liveComposerResults = candidates;
        composerResults.replaceChildren(
          ...candidates.map((composer) =>
            el(
              "li",
              {
                class: "list-item",
                style: "cursor:pointer",
                onclick: () => chooseComposer(composer),
              },
              composer.name
            )
          )
        );
      } catch (error) {
        liveComposerResults = [];
        composerResults.replaceChildren(empty(error.detail || "Search failed."));
      }
    }, 280);
  });

  const finish = el(
    "button",
    {
      class: "btn btn-solid",
      type: "submit",
      onclick: async (event) => {
        event.preventDefault();
        finish.disabled = true;
        try {
          await Promise.all([
            api.updateGenres(Array.from(chosenGenres)),
            api.updateComposers(chosenComposers.map((composer, index) => ({ composer_id: composer.id, rank: index + 1 }))),
          ]);
          notify.success("Studio is set up");
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your tastes");
          finish.disabled = false;
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
              class: `pill${chosenGenres.has(genre.id) ? " pill-accent" : ""}`,
              style: "cursor:pointer",
              onclick: () => {
                if (chosenGenres.has(genre.id)) chosenGenres.delete(genre.id);
                else chosenGenres.add(genre.id);
                chip.classList.toggle("pill-accent");
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
