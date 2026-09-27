import { api } from "../api/client.js";
import { el, reveal, sectionBlock } from "../lib/dom.js";
import { renderNotation } from "../lib/notation.js";
import { playNotation } from "../lib/synth.js";

const CATEGORY_LABELS = {
  double_notes: "double notes",
  octaves: "octaves",
  leaps: "leaps",
  chords: "chords",
  dexterity: "dexterity",
  repeated_notes: "repeated notes",
  trills: "trills",
  stretches: "stretches",
  polyrhythm: "polyrhythm",
  voicing: "voicing",
  pedaling: "pedalling",
  endurance: "endurance",
};

// Strings made only of null/None/undefined (e.g. "nullnullnull") are data junk
// that slipped past the API. Hide them, but say which field so it can be traced.
const PLACEHOLDER_JUNK = /^(?:\s|null|none|undefined)+$/i;

function isJunk(label, value) {
  if (typeof value !== "string" || !PLACEHOLDER_JUNK.test(value)) return false;
  console.warn(`[piece overview] "${label}" arrived as placeholder text ${JSON.stringify(value)}; hiding it.`);
  return true;
}

function metaRow(label, value, { wide = false } = {}) {
  if (value === null || value === undefined || value === "" || value === "unknown") return null;
  if (isJunk(label, value)) return null;
  return el(
    "div",
    { class: wide ? "meta-row meta-row-wide" : "meta-row" },
    el("span", { class: "meta-key" }, label),
    el("span", { class: "meta-value mono" }, value instanceof Node ? value : String(value))
  );
}

function formatScore(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return String(Math.round(number * 10) / 10);
}

// Personalised ("for you") difficulty in the pink accent beside the neutral
// catalogue baseline. Both are always shown; "--" stands in for a missing value.
export function difficultyPair(personalized, baseline, { band } = {}) {
  const forYou = formatScore(personalized);
  const base = formatScore(baseline);
  if (forYou === null && base === null) return null;
  const delta = forYou !== null && base !== null ? Math.round((Number(forYou) - Number(base)) * 10) / 10 : 0;
  return el(
    "span",
    {
      class: "difficulty-pair",
      title:
        delta === 0
          ? "Your difficulty matches the catalogue baseline"
          : `${Math.abs(delta)} ${delta > 0 ? "harder" : "easier"} for you than the catalogue baseline`,
    },
    el(
      "span",
      { class: "difficulty-half difficulty-for-you" },
      el("span", { class: "difficulty-value" }, forYou ?? "--"),
      el("span", { class: "difficulty-caption" }, "for you")
    ),
    el(
      "span",
      { class: "difficulty-half difficulty-base" },
      el("span", { class: "difficulty-value" }, base ?? "--"),
      el("span", { class: "difficulty-caption" }, band ? `baseline · ${band}` : "baseline")
    )
  );
}

function prose(title, body) {
  if (!body || isJunk(title, body)) return null;
  return el(
    "div",
    { class: "lore-block" },
    el("div", { class: "stat-label" }, title),
    el("p", { class: "lore-text" }, body)
  );
}

function sectionCard(section, index) {
  const stage = el("div", { style: "display:none" });
  let activePlayback = null;
  let loaded = false;

  const barButton = el(
    "button",
    { type: "button", class: "section-bars mono", style: "background:none;border:none;padding:10px 0;margin:-10px 0;cursor:pointer;color:inherit;text-decoration:underline dotted;min-height:24px" },
    section.measure_span
  );

  async function toggle() {
    const isOpen = stage.style.display !== "none";
    if (isOpen) {
      stage.style.display = "none";
      if (activePlayback) {
        activePlayback.stop();
        activePlayback = null;
      }
      return;
    }
    stage.style.display = "";
    if (loaded) return;
    loaded = true;
    stage.replaceChildren(el("p", { class: "faint", style: "font-size:12px;margin:8px 0" }, "Forging a practice pattern for this passage…"));
    try {
      const notation = await api.passageSightReading(section.id);
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
            activePlayback = playNotation(notation, {
              onDone: () => {
                playButton.textContent = "Play";
                activePlayback = null;
              },
            });
          },
        },
        "Play"
      );
      stage.replaceChildren(
        el(
          "div",
          { class: "row", style: "justify-content:space-between;margin:10px 0 6px" },
          el("span", { class: "faint mono", style: "font-size:11px" }, `representative pattern · ${notation.key} · ${notation.tempo_bpm} bpm`),
          playButton
        ),
        el("div", { class: "notation-host" }, renderNotation(notation))
      );
    } catch (error) {
      stage.replaceChildren(el("p", { class: "faint", style: "font-size:12px" }, error.detail || "Could not forge a pattern for this passage."));
    }
  }

  barButton.addEventListener("click", toggle);

  return el(
    "li",
    { class: index === 0 ? "section-card section-card-top" : "section-card", dataset: { rank: String(index + 1) } },
    el(
      "div",
      { class: "row", style: "justify-content:space-between;align-items:flex-start;gap:12px" },
      el(
        "div",
        {},
        barButton,
        el("strong", { class: "section-label" }, section.label || "Marked passage")
      ),
      section.difficulty_score != null
        ? el("span", { class: "pill pill-accent mono" }, section.difficulty_score)
        : null
    ),
    section.description ? el("p", { class: "section-text" }, section.description) : null,
    section.practice_cue
      ? el(
          "p",
          { class: "section-cue" },
          el("span", { class: "cue-tag" }, "Approach"),
          section.practice_cue
        )
      : null,
    section.techniques.length
      ? el(
          "div",
          { class: "row", style: "gap:6px;flex-wrap:wrap;margin-top:10px" },
          ...section.techniques.map((name) => el("span", { class: "pill" }, name))
        )
      : null,
    stage
  );
}

const MASTERY_TONE = {
  green: "pill-ok",
  red: "pill-bad",
  amber: "pill-warn",
  unranked: "",
};

function techniqueRow(technique) {
  const share = Math.round(Number(technique.weight) * 100);
  const masteryTone = MASTERY_TONE[technique.mastery_color] || "";
  const notes = [
    technique.mechanic ? el("p", { class: "technique-text" }, technique.mechanic) : null,
    technique.common_fault
      ? el("p", { class: "technique-fault" }, el("span", { class: "cue-tag cue-warn" }, "Usual fault"), technique.common_fault)
      : null,
  ].filter(Boolean);
  return el(
    "li",
    { class: "technique-row" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between;align-items:baseline" },
      el(
        "div",
        { class: "row", style: "gap:8px" },
        technique.mastery_tier ? el("span", { class: `pill ${masteryTone}` }, technique.mastery_tier) : null,
        el("strong", { style: "font-weight:500" }, technique.name),
        el("span", { class: "faint mono", style: "font-size:11px" }, CATEGORY_LABELS[technique.category] || technique.category)
      ),
      el("span", { class: "faint mono", style: "font-size:11.5px" }, `${share}% · load ${technique.load_factor}`)
    ),
    el("div", { class: "bar", style: "margin:7px 0 0" }, el("span", { style: `width:${share}%` })),
    notes.length ? revealParts(reveal("How it's played", notes)) : null
  );
}

function revealParts(control) {
  return [control.button, control.region];
}

const VISIBLE_SECTIONS = 3;

function pieceDrawer(items) {
  const body = el("div", { class: "piece-drawer-body", role: "tabpanel" });
  const built = new Map();
  const buttons = items.map((item) =>
    el(
      "button",
      {
        type: "button",
        role: "tab",
        class: "tab",
        "aria-selected": "false",
        onclick: () => select(item.id),
      },
      item.label
    )
  );
  function select(id) {
    const item = items.find((candidate) => candidate.id === id);
    if (!item) return;
    if (!built.has(id)) built.set(id, item.build());
    body.replaceChildren(built.get(id));
    buttons.forEach((button, index) => {
      const selected = items[index].id === id;
      button.setAttribute("aria-selected", selected ? "true" : "false");
      button.tabIndex = selected ? 0 : -1;
    });
  }
  const strip = el("div", { class: "tabs piece-drawer-tabs", role: "tablist", "aria-label": "More about this piece" }, ...buttons);
  strip.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const index = buttons.indexOf(document.activeElement);
    if (index === -1) return;
    const next = (index + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length;
    buttons[next].focus();
    select(items[next].id);
  });
  if (items.length) select(items[0].id);
  return el("section", { class: "panel detail-section piece-drawer" }, strip, body);
}

function keyFactsSection(overview, { showDifficulty = true } = {}) {
  const difficulty = showDifficulty
    ? difficultyPair(overview.personalized_difficulty, overview.difficulty_score, { band: overview.difficulty_band })
    : null;
  const mood =
    overview.mood && !isJunk("Character", overview.mood)
      ? el("div", { class: "mood-strip" }, el("span", { class: "cue-tag" }, "Character"), overview.mood)
      : null;
  return sectionBlock(
    "About this piece",
    {},
    el(
      "div",
      { class: "meta-grid" },
      metaRow("Catalogue", overview.catalog_number),
      metaRow("Era", overview.era),
      metaRow("Key", overview.key_signature),
      metaRow("Marking", overview.tempo_marking),
      metaRow("Duration", overview.duration_label),
      metaRow("Difficulty", difficulty, { wide: true })
    ),
    mood
  );
}

function storyBody(overview) {
  const composer = overview.composer;
  const facts = el(
    "div",
    { class: "meta-grid" },
    metaRow("Composer", composer ? composer.name : null),
    metaRow("Composed", overview.year_composed),
    metaRow("Genre", overview.genre),
    metaRow("Syllabus grade", overview.syllabus_grade),
    metaRow("Mechanical load", overview.mechanical_load)
  );
  const blocks = [
    prose("What it depicts", overview.scene),
    prose("History", overview.historical_note),
    prose("Worth knowing", overview.fun_fact),
  ].filter(Boolean);
  if (!blocks.length && !facts.children.length) return null;
  return el("div", { class: "lore-panel" }, facts.children.length ? facts : null, ...blocks);
}

function passagesBody(overview) {
  const cards = overview.sections.map(sectionCard);
  const rest = cards.slice(VISIBLE_SECTIONS);
  return el(
    "div",
    {},
    el("p", { class: "section-caption", style: "margin:0 0 var(--space-3)" }, "Hardest first. Tap the bar numbers for a practice pattern built from the passage."),
    el("ol", { class: "section-list" }, ...cards.slice(0, VISIBLE_SECTIONS)),
    rest.length
      ? revealParts(
          reveal(`${rest.length} more passage${rest.length === 1 ? "" : "s"}`, () =>
            el("ol", { class: "section-list", start: String(VISIBLE_SECTIONS + 1) }, ...rest)
          )
        )
      : null
  );
}

function composerBody(composer) {
  const blocks = [
    prose("Signature sound", composer.signature_sound),
    prose("Background", composer.bio),
    prose("Worth knowing", composer.fun_fact),
  ].filter(Boolean);
  const line = [composer.nationality, composer.lifespan, composer.era].filter(Boolean).join(" · ");
  return el("div", { class: "lore-panel" }, line ? el("p", { class: "faint mono", style: "margin:0 0 var(--space-3);font-size:12px" }, line) : null, ...blocks);
}

function loadBody(profile) {
  return el(
    "div",
    { class: "meta-grid" },
    ...[
      metaRow("Load index", profile.load_index),
      metaRow("Widest stretch", profile.max_stretch_semitones ? `${profile.max_stretch_semitones} semitones` : null),
      metaRow("Stretch in cm", profile.max_stretch_cm ? `${profile.max_stretch_cm} cm` : null),
      metaRow("Octave density", profile.octave_density),
      metaRow("Chord density", profile.repeated_chord_density),
      metaRow("Peak notes/sec", profile.notes_per_second_peak),
    ].filter(Boolean)
  );
}

function movementsBody(movements) {
  return el(
    "ul",
    { class: "flat-list" },
    ...movements.map((movement) =>
      el(
        "li",
        { class: "flat-row" },
        el(
          "div",
          {},
          el("div", {}, movement.movement_number != null ? `${movement.movement_number}. ${movement.title}` : movement.title),
          el("div", { class: "faint mono", style: "font-size:11.5px" }, movement.duration_label)
        ),
        movement.difficulty_score != null ? el("span", { class: "pill mono" }, movement.difficulty_score) : null
      )
    )
  );
}

export function pieceOverview(overview, { heading = true, difficulty = true } = {}) {
  const composer = overview.composer;
  const wrap = el("div", { class: "overview" });

  if (heading) {
    wrap.append(
      el(
        "div",
        { class: "overview-head" },
        el("h2", { style: "margin:0" }, overview.title),
        el("p", { class: "muted", style: "margin:5px 0 0" }, composer ? composer.byline : "unknown composer")
      )
    );
  }

  const badges = [
    overview.is_custom ? el("span", { class: "pill pill-custom" }, "custom") : null,
    overview.external_source ? el("span", { class: "pill" }, overview.external_source) : null,
    heading && overview.requires_verification ? el("span", { class: "pill pill-warn" }, "needs verification") : null,
  ].filter(Boolean);
  if (badges.length) wrap.append(el("div", { class: "row" }, ...badges));

  wrap.append(keyFactsSection(overview, { showDifficulty: difficulty }));

  const story = storyBody(overview);
  const hasComposer = composer && (composer.bio || composer.fun_fact || composer.signature_sound);
  const items = [
    overview.sections.length ? { id: "passages", label: `Hard passages · ${overview.sections.length}`, build: () => passagesBody(overview) } : null,
    overview.techniques.length
      ? { id: "techniques", label: "Techniques", build: () => el("ul", { class: "technique-list" }, ...overview.techniques.map(techniqueRow)) }
      : null,
    story ? { id: "story", label: "Story & facts", build: () => story } : null,
    hasComposer ? { id: "composer", label: `About ${composer.name.split(" ").slice(-1)[0]}`, build: () => composerBody(composer) } : null,
    overview.load_profile ? { id: "load", label: "Physical load", build: () => loadBody(overview.load_profile) } : null,
    overview.movements.length ? { id: "movements", label: "Movements", build: () => movementsBody(overview.movements) } : null,
  ].filter(Boolean);
  if (items.length) wrap.append(pieceDrawer(items));

  return wrap;
}

export function linkSummaryPanel(summary) {
  const wrap = el("div", { class: "link-summary" });

  wrap.append(
    el(
      "div",
      { class: "row", style: "justify-content:space-between;align-items:flex-start;gap:12px" },
      el(
        "div",
        {},
        el("div", { class: "stat-label" }, `${summary.link_type.replace(/_/g, " / ")} link`),
        el("strong", { class: "link-headline" }, summary.headline)
      ),
      summary.curated ? el("span", { class: "pill pill-accent" }, "curated") : null
    ),
    el(
      "div",
      { class: "link-ends" },
      el("span", {}, summary.source.title),
      el("span", { class: "link-arrow" }, "—"),
      el("span", {}, summary.target.title)
    ),
    el("p", { class: "lore-text" }, summary.summary)
  );

  if (summary.shared_techniques.length) {
    wrap.append(
      el("div", { class: "stat-label", style: "margin-top:14px" }, "Shared demands"),
      el(
        "ul",
        { class: "shared-list" },
        ...summary.shared_techniques.map((technique) =>
          el(
            "li",
            { class: "shared-item" },
            el(
              "div",
              { class: "row", style: "justify-content:space-between;align-items:baseline" },
              el("strong", { style: "font-weight:500" }, technique.name),
              el(
                "span",
                { class: "faint mono", style: "font-size:11px" },
                `${Math.round(Number(technique.source_weight) * 100)}% / ${Math.round(Number(technique.target_weight) * 100)}%`
              )
            ),
            technique.mechanic ? el("p", { class: "technique-text" }, technique.mechanic) : null
          )
        )
      )
    );
  }

  if (summary.shared_sections.length) {
    wrap.append(
      el("div", { class: "stat-label", style: "margin-top:14px" }, "Where it shows up"),
      el(
        "ul",
        { class: "shared-list" },
        ...summary.shared_sections.map((section) =>
          el(
            "li",
            { class: "shared-item" },
            el(
              "div",
              { class: "row", style: "justify-content:space-between;gap:10px" },
              el("span", { style: "font-size:13.5px" }, `${section.piece_title} · ${section.label || "passage"}`),
              el("span", { class: "pill mono" }, section.measure_span)
            )
          )
        )
      )
    );
  }

  if (summary.facts.length) {
    wrap.append(
      el(
        "div",
        { class: "row", style: "gap:6px;flex-wrap:wrap;margin-top:14px" },
        ...summary.facts.map((fact) => el("span", { class: "pill mono" }, fact))
      )
    );
  }

  return wrap;
}
