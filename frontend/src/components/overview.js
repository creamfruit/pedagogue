import { api } from "../api/client.js";
import { el } from "../lib/dom.js";
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

function metaRow(label, value) {
  if (value === null || value === undefined || value === "" || value === "unknown") return null;
  return el(
    "div",
    { class: "meta-row" },
    el("span", { class: "meta-key" }, label),
    el("span", { class: "meta-value mono" }, String(value))
  );
}

function prose(title, body) {
  if (!body) return null;
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
        el("div", { class: "notation-host" }, renderNotation(notation, { width: 560 }))
      );
    } catch (error) {
      stage.replaceChildren(el("p", { class: "faint", style: "font-size:12px" }, error.detail || "Could not forge a pattern for this passage."));
    }
  }

  barButton.addEventListener("click", toggle);

  return el(
    "li",
    { class: "section-card", dataset: { rank: String(index + 1) } },
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
  return el(
    "li",
    { class: "technique-row" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between;align-items:baseline" },
      el(
        "div",
        { class: "row", style: "gap:8px" },
        technique.mastery_tier
          ? el("span", { class: `pill ${masteryTone}` }, technique.mastery_tier)
          : null,
        el("strong", { style: "font-weight:500" }, technique.name),
        el(
          "span",
          { class: "faint mono", style: "font-size:11px" },
          CATEGORY_LABELS[technique.category] || technique.category
        )
      ),
      el("span", { class: "faint mono", style: "font-size:11.5px" }, `${share}% · load ${technique.load_factor}`)
    ),
    el("div", { class: "bar", style: "margin:7px 0 0" }, el("span", { style: `width:${share}%` })),
    technique.mechanic ? el("p", { class: "technique-text" }, technique.mechanic) : null,
    technique.common_fault
      ? el(
          "p",
          { class: "technique-fault" },
          el("span", { class: "cue-tag cue-warn" }, "Usual fault"),
          technique.common_fault
        )
      : null
  );
}

export function pieceOverview(overview, { heading = true } = {}) {
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
    overview.requires_verification ? el("span", { class: "pill pill-warn" }, "needs verification") : null,
  ].filter(Boolean);
  if (badges.length) wrap.append(el("div", { class: "row", style: "margin-bottom:10px" }, ...badges));

  wrap.append(
    el(
      "div",
      { class: "meta-grid" },
      metaRow("Composer", composer ? composer.name : null),
      metaRow("Catalogue", overview.catalog_number),
      metaRow("Key", overview.key_signature),
      metaRow("Composed", overview.year_composed),
      metaRow("Marking", overview.tempo_marking),
      metaRow("Duration", overview.duration_label),
      metaRow("Genre", overview.genre),
      metaRow("Era", overview.era),
      metaRow("Syllabus grade", overview.syllabus_grade),
      metaRow("Difficulty", overview.difficulty_score != null ? `${overview.difficulty_score} · ${overview.difficulty_band}` : null),
      metaRow("Mechanical load", overview.mechanical_load),
      metaRow(
        "For you",
        overview.personalized_difficulty != null && overview.personalized_difficulty !== overview.difficulty_score
          ? overview.personalized_difficulty
          : null
      )
    )
  );

  if (overview.mood) {
    wrap.append(el("div", { class: "mood-strip" }, el("span", { class: "cue-tag" }, "Character"), overview.mood));
  }

  const lore = [
    prose("What it depicts", overview.scene),
    prose("History", overview.historical_note),
    prose("Worth knowing", overview.fun_fact),
  ].filter(Boolean);
  if (lore.length) wrap.append(el("section", { class: "panel lore-panel" }, ...lore));

  if (overview.sections.length) {
    wrap.append(
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, "Hardest sections"),
        el(
          "p",
          { class: "faint mono", style: "font-size:11.5px;margin:-4px 0 12px" },
          `${overview.sections.length} marked passages, hardest first`
        ),
        el("ol", { class: "section-list" }, ...overview.sections.map(sectionCard))
      )
    );
  }

  if (overview.techniques.length) {
    wrap.append(
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, "Techniques involved"),
        el(
          "p",
          { class: "faint mono", style: "font-size:11.5px;margin:-4px 0 12px" },
          "ordered by how much of the difficulty each one carries"
        ),
        el("ul", { class: "technique-list" }, ...overview.techniques.map(techniqueRow))
      )
    );
  }

  if (composer && (composer.bio || composer.fun_fact || composer.signature_sound)) {
    wrap.append(
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, `About ${composer.name}`),
        composer.lifespan
          ? el("p", { class: "faint mono", style: "font-size:11.5px;margin:-4px 0 12px" },
              [composer.nationality, composer.lifespan, composer.era].filter(Boolean).join(" · "))
          : null,
        prose("Signature sound", composer.signature_sound),
        prose("Background", composer.bio),
        prose("Worth knowing", composer.fun_fact)
      )
    );
  }

  const profile = overview.load_profile;
  if (profile) {
    wrap.append(
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, "Physical load"),
        el(
          "div",
          { class: "meta-grid" },
          metaRow("Load index", profile.load_index),
          metaRow("Widest stretch", profile.max_stretch_semitones ? `${profile.max_stretch_semitones} semitones` : null),
          metaRow("Stretch in cm", profile.max_stretch_cm ? `${profile.max_stretch_cm} cm` : null),
          metaRow("Octave density", profile.octave_density),
          metaRow("Chord density", profile.repeated_chord_density),
          metaRow("Peak notes/sec", profile.notes_per_second_peak)
        )
      )
    );
  }

  if (overview.movements.length) {
    wrap.append(
      el(
        "section",
        { class: "panel", style: "margin-top:16px" },
        el("h3", {}, "Movements"),
        el(
          "ul",
          { class: "list" },
          ...overview.movements.map((movement) =>
            el(
              "li",
              { class: "list-item" },
              el(
                "div",
                {},
                el("div", {}, `${movement.movement_number}. ${movement.title}`),
                el("div", { class: "faint mono", style: "font-size:11.5px" }, movement.duration_label)
              ),
              movement.difficulty_score != null
                ? el("span", { class: "pill mono" }, movement.difficulty_score)
                : null
            )
          )
        )
      )
    );
  }

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
