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

// Personalised ("for you") difficulty in the orange accent beside the neutral
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

function aboutSection(overview, { showDifficulty = true } = {}) {
  const composer = overview.composer;
  const difficulty = showDifficulty
    ? difficultyPair(overview.personalized_difficulty, overview.difficulty_score, { band: overview.difficulty_band })
    : null;
  const primary = el(
    "div",
    { class: "meta-grid" },
    metaRow("Catalogue", overview.catalog_number),
    metaRow("Era", overview.era),
    metaRow("Key", overview.key_signature),
    metaRow("Marking", overview.tempo_marking),
    metaRow("Duration", overview.duration_label),
    metaRow("Difficulty", difficulty, { wide: true })
  );
  const secondary = [
    el(
      "div",
      { class: "meta-grid" },
      metaRow("Composer", composer ? composer.name : null),
      metaRow("Composed", overview.year_composed),
      metaRow("Genre", overview.genre),
      metaRow("Syllabus grade", overview.syllabus_grade),
      metaRow("Mechanical load", overview.mechanical_load)
    ),
    prose("History", overview.historical_note),
    prose("Worth knowing", overview.fun_fact),
  ].filter((node) => node && (node.className !== "meta-grid" || node.children.length));
  const mood =
    overview.mood && !isJunk("Character", overview.mood)
      ? el("div", { class: "mood-strip" }, el("span", { class: "cue-tag" }, "Character"), overview.mood)
      : null;
  const scene = prose("What it depicts", overview.scene);
  return sectionBlock(
    "About this piece",
    {},
    primary,
    mood,
    scene ? el("div", { class: "lore-panel" }, scene) : null,
    secondary.length ? revealParts(reveal("More about this piece", el("div", { class: "lore-panel" }, ...secondary))) : null
  );
}

function sectionsSection(overview) {
  const cards = overview.sections.map(sectionCard);
  const shown = el("ol", { class: "section-list" }, ...cards.slice(0, VISIBLE_SECTIONS));
  const rest = cards.slice(VISIBLE_SECTIONS);
  return sectionBlock(
    "Hardest sections",
    {
      caption: `${overview.sections.length} marked passage${overview.sections.length === 1 ? "" : "s"}, hardest first. Tap the bar numbers for a practice pattern.`,
    },
    shown,
    rest.length
      ? revealParts(
          reveal(`${rest.length} more passage${rest.length === 1 ? "" : "s"}`, () =>
            el("ol", { class: "section-list", start: String(VISIBLE_SECTIONS + 1) }, ...rest)
          )
        )
      : null
  );
}

function composerSection(composer) {
  const signature = prose("Signature sound", composer.signature_sound);
  const more = [prose("Background", composer.bio), prose("Worth knowing", composer.fun_fact)].filter(Boolean);
  return sectionBlock(
    `About ${composer.name}`,
    {
      caption: composer.lifespan
        ? [composer.nationality, composer.lifespan, composer.era].filter(Boolean).join(" · ")
        : null,
    },
    signature ? el("div", { class: "lore-panel" }, signature) : null,
    more.length ? revealParts(reveal(`More about ${composer.name}`, el("div", { class: "lore-panel" }, ...more))) : null
  );
}

function loadSection(profile) {
  const rows = [
    metaRow("Widest stretch", profile.max_stretch_semitones ? `${profile.max_stretch_semitones} semitones` : null),
    metaRow("Stretch in cm", profile.max_stretch_cm ? `${profile.max_stretch_cm} cm` : null),
    metaRow("Octave density", profile.octave_density),
    metaRow("Chord density", profile.repeated_chord_density),
    metaRow("Peak notes/sec", profile.notes_per_second_peak),
  ].filter(Boolean);
  return sectionBlock(
    "Physical load",
    {},
    el("div", { class: "meta-grid" }, metaRow("Load index", profile.load_index)),
    rows.length ? revealParts(reveal("All load measurements", el("div", { class: "meta-grid" }, ...rows))) : null
  );
}

function movementsSection(movements) {
  return sectionBlock(
    "Movements",
    {},
    el(
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

  wrap.append(aboutSection(overview, { showDifficulty: difficulty }));
  if (overview.sections.length) wrap.append(sectionsSection(overview));
  if (overview.techniques.length) {
    wrap.append(
      sectionBlock(
        "Techniques involved",
        { caption: "Ordered by how much of the difficulty each one carries." },
        el("ul", { class: "technique-list" }, ...overview.techniques.map(techniqueRow))
      )
    );
  }
  if (composer && (composer.bio || composer.fun_fact || composer.signature_sound)) wrap.append(composerSection(composer));
  if (overview.load_profile) wrap.append(loadSection(overview.load_profile));
  if (overview.movements.length) wrap.append(movementsSection(overview.movements));

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
