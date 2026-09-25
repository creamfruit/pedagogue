# RUN_NOTES — ui-ux-overhaul overnight run

<!-- CONSOLIDATED SUMMARY is written at the top of this file in Phase 6. -->

## Phase-by-phase log

### 2026-09-26 — Phase 0 (baseline)

- **Decision: `onboarding.js` resolved to `main`'s committed version, not the zip.** Per your
  instruction, `git checkout -- frontend/src/views/onboarding.js`. The awaited
  `store.refreshOnboarding()` / `draw()` fix stays. `git status` was clean afterwards.
- **Observation: the planned 0e commit ("chore: revert in-progress styles/onboarding edits…") was
  not made because there was nothing to commit.** `styles.css` on `main` is byte-identical to the
  zip, and `onboarding.js` went back to `main`, so both files matched `HEAD` and the branch starts
  at `main`'s commit `5886966`. Making an empty commit would have added noise without any content.
- Cline's discarded uncommitted edits were saved outside the repo (session scratchpad:
  `cline-uncommitted-styles-onboarding.patch` plus full file copies). They are *not* in git. If
  you want them, ask me for them or re-derive them from Cline's history.
- `backend/.env`, `backend/alembic/versions/a77858f33c61_*.py` and `origin/master` were not touched.
- Installs: `pip install -r requirements.txt` into the existing `backend/.venv` (Python 3.14.2)
  was clean and `pip check` passed. `npm install` was clean, but it reported 3 advisories
  (2 moderate, 1 high; not addressed) and said esbuild's postinstall is "not yet covered by
  allowScripts". `npm run build` still succeeds.
- Baseline tests: 50 passed.

### 2026-09-26 — Verification harness (applies to every phase)

- Postgres/Redis are not running and Docker Desktop is stopped, so the real backend can't be
  started. I did not start Docker unattended. For visual/runtime checks I wrote a
  dependency-free mock API (Node) and drove the Vite dev server with headless Chrome through
  `puppeteer-core`, capturing console errors and screenshots. Both live in the session scratchpad,
  not in the repo. Every phase still runs the real gates: `npm run build` and the backend `pytest`
  suite.

### 2026-09-26 — Phase 1: four-colour token system

**What changed**
- `styles.css` `:root` defines the four accents `--yellow #ffd08a`, `--orange #f0a13c`
  (was `--amber`), `--pink #e05a78` (was `--rose`) and `--black #020202`. It also adds
  `--*-rgb` triplets, so tints are written as `rgba(var(--orange-rgb), a)`, i.e. opacity steps of
  an accent, never new hues. `--amber-deep`, `--amber-wash`, `--coral`, `--cool` and the green
  `--ok` were removed. Every rule that referenced them now uses the new tokens.
- New `frontend/src/lib/palette.js` reads the tokens from CSS at runtime for canvas drawing, so
  JS and CSS can't drift apart. It holds the era and difficulty encodings shared by the
  constellation and the Observatory previews.

**Decisions made without you**
- **Status semantics (no fifth hue).** `bad` = pink, bolder, with a triangle marker; `warn` =
  orange with a diamond marker; `ok` = white text on a black fill with a round marker (the
  "black/white contrast treatment"). The markers make status readable without colour. Toasts
  follow the same mapping.
- **`--black` as an accent.** Primary `.btn` is a black fill with an orange outline and text,
  inverting to an orange fill with black text on hover. Selected tier buttons are an orange fill
  with black text. Custom-piece pills and stars use black fills with white outlines.
- **`--yellow` = `#ffd08a`**, the existing gold tone, used for gold amounts. `#ffe3b0` was
  dropped as a separate colour.
- **Constellation encoding** (each distinction the old hues carried is kept):
  - Link types: composer = orange solid; technique = yellow dashed (7/4); era/genre = pink dotted.
    The legend swatches draw the same dash patterns. When a link type has its own pattern, that
    pattern wins over the "Survey lines" dashed cosmetic, so the cosmetic now only restyles
    composer links.
  - Six eras on three hues: Baroque/Classical = yellow, Romantic/Impressionist = orange,
    Modern/Contemporary = pink. The later era of each pair gets diffraction spikes (a "+"
    through the star). An era key with matching glyphs was added under the link legend, which
    didn't exist before. Stars with an unknown era use the neutral text colour.
  - Custom pieces (was violet): a black core with a white outline, the only hollow-looking lit
    star. The old dashed violet outer ring was dropped because the frozen ring is also dashed now.
  - Unverified (was grey): unchanged, a neutral dashed hollow ring.
  - Frozen (was ice blue `#9fd4f0`): a neutral dashed ring. Pills use the new `pill-frozen`
    class (dashed neutral border) in `constellation.js` and `repertoire.js`.
  - "Heat map" difficulty cosmetic: pink → orange → yellow → white for easiest → hardest. The
    old "cool" end was blue. The cosmetic's description ("Cool for easy") lives in
    `backend/app/seed.py` and was **not** edited.
- **Left as-is on purpose:**
  - Purchased cosmetic payload colours in `backend/app/seed.py` (Ice field `#9fd4f0`, Emerald
    `#5fd9a4`, Violet `#a98cf5`, nebula RGB layers). These are item data users buy by name
    ("Emerald drift"), not app accents. Recolouring them would break the product descriptions.
    Flag this if you want them retired or recoloured.
  - `public/icons/favicon.svg` (cyan `#2fd9e8` / violet `#9b7cf0`) and its PNG siblings. They're
    outside `frontend/src`, and changing the SVG without regenerating the PNGs would make them
    mismatch. This is a follow-up item.
  - Neutrals confirmed as neutrals: the `--bg*`, `--line*` and `--text*` scales,
    `rgba(255,255,255,.016)` scanlines, `rgba(8,9,10,.86)` topbar, `rgba(10,10,12,.62)` modal
    scrim, `rgba(3,3,5,.72)` legend backdrop, `#08090a` theme-color in `index.html` and
    `vite.config.js`, and the `#ffffff` highlight core in `palette.js`.
  - `MASTERY_TONE` in `overview.js`: the keys (`green`/`red`/`amber`) are backend
    `mastery_color` values, so the mapping stays. The pill classes it points to now render with
    the four-token system.

**Verification**: build ✔, pytest 50/50 ✔, and the constellation, Observatory and piece-detail
pages render against the mock with no console errors.

**Summary**: The app now uses exactly four accents plus neutrals. Status and category meaning
that used to come from extra hues (green ok, blue frozen, violet custom, six era colours,
three link colours) now comes from marker shape, dash pattern, spikes and fill-vs-outline.

### 2026-09-26 — Phase 2: onboarding input UX, button states, tier-list notation

**2a**: already satisfied by the committed `await` fix, so no action was needed.

**2b — Enter key.** Both searches now go through one shared `wireSearch()` helper in
`onboarding.js`. Enter cancels the 280 ms debounce and searches immediately; the mock measured
8 ms against 302 ms through the debounce. **Decision:** if the results already on screen are for
the current text, Enter selects the first result, which matches your "reasonable enhancement".
If the text changed since those results arrived, Enter runs a fresh search instead of picking a
stale result. Because an immediate search can race the debounced one, I added a request
sequence number so late responses are dropped. Result rows are now focusable
(`tabindex=0`, `role=button`, Enter/Space picks them) and reuse the existing
`.list-item-link` focus style. After a pick, focus returns to the search box.

**2c — Button states.** These are built from the accents plus neutrals, with no new hues:
- `.btn` (primary): rest = black fill with orange outline; hover = orange fill with black text;
  focus-visible = 2px yellow ring; pressed = yellow fill; disabled = transparent with a dashed
  neutral border and faint text (hover no longer applies to disabled buttons, which it did
  before); **saving** (`aria-busy="true"`) = moving orange stripes and the label "Saving…".
- **Decision:** "not ready yet" and "saving" are now two distinct looks. A new `setBusy()`
  helper sets `aria-busy` and the "Saving…" label on the profile, tier, top-ten and tastes
  Continue buttons, and restores the label if the save fails.
- `.btn-ghost`, `.btn-danger`, tier buttons: hover and pressed states added. The selected
  tier is an orange fill with black text. Tier buttons now carry `aria-pressed` and an
  `aria-label` (e.g. "Trills: B · solid").
- `select`/`input`/`textarea`: hover (brighter neutral border), focus-visible
  (orange border + yellow ring), select pressed (yellow border), disabled (dashed, faint).
- `.option-card` (used by the practice modal): focus-visible, pressed, selected
  (`aria-pressed`/`.is-selected`) and disabled states added.
- Genre chips in the tastes step are now `.pill-toggle` buttons with `aria-pressed`: orange fill
  when chosen, plus hover, focus-visible and pressed states.
- Small fix: the tier quiz's disabled Continue now shows "Rank every technique (0/N)" from the
  start. Before, it showed a bare "Continue" until the first click.

**2d — Notation snippets. Decision: a static snippet per category, client-side, hand-written
in the forge's note format** (`frontend/src/lib/techniqueSnippets.js`). Reasoning:
- Neither the `Technique` model nor `GET /catalog/techniques` carries a note pattern, so there
  was no existing per-technique notation data to reuse.
- `backend/app/services/notation.py` has per-*category* builders, but they're randomised
  8-bar sight-reading exercises. Using them would need a new endpoint and backend tests, plus a
  network request during onboarding. I ran them (seed 7, C4, difficulty 5) and several are poor
  illustrations at a representative difficulty: "double notes" come out as fourths, "stretches"
  span only a fifth, dexterity and endurance are identical, and polyrhythm is a single voice.
- So each snippet is one bar in the exact `{measures:[{notes}]}` shape the forge emits, drawn by
  the unchanged `renderNotation()` API. I used the builders' output where it was already good
  (octaves, trills, voicing idea) and wrote the rest by hand (thirds, stride leaps, a real
  tenth, etc.).
- **Limitation:** `renderNotation()` has no tuplets, so "polyrhythm" is shown as two hands
  against each other rather than a true 3-against-2.
- **Decision:** one snippet per *category*, shown on the category header rather than on every
  technique row. With 17 techniques in 12 categories, per-row snippets would repeat the same
  pattern (e.g. both double-note techniques). The SVG is scaled to 88px tall via CSS.
- **Noticed, not fixed:** onboarding shows `technique.mechanic`, but `GET /catalog/techniques`
  returns `TechniqueRead`, which has no `mechanic` field, so that sub-line never appears with the
  real backend. That's a backend schema gap that's out of scope here.

**Verification**: build ✔, pytest 50/50 ✔. Scripted in headless Chrome: Enter latency, Enter-picks-
first, input cleared, debounce still works, computed disabled/hover/busy styles differ, tier
hover/selected/focus-visible, no console errors. One bug was caught and fixed while checking: tier
hover lost a specificity fight with `.btn-ghost:hover`.

**Summary**: Enter now searches immediately in both onboarding searches, and picks the first
result when results are already showing. Every onboarding control has distinct hover,
focus-visible, pressed, disabled and saving looks. The tier quiz shows a one-bar notation
snippet per technique category.

### 2026-09-26 — Phase 3: Piece Detail overhaul

**3a — meta-grid order.** It's now Composer, Catalogue, Era, Duration, then Key, Composed,
Marking, Genre, Syllabus grade, Difficulty, Mechanical load, keeping their previous relative
order. The old separate "For you" row is gone (see 3c).

#### Piece Detail — nullnullnull

**Root cause found and fixed; it was static after all, just not in `metaRow()`.** In
`entryDetailView` (`frontend/src/views/repertoire.js`), `host.replaceChildren(...)` was passed
`banner`, `verificationBanner(entry)`, `decayBanner(entry, render)` and
`overview ? pieceOverview(...) : null` directly. Each is `null` when it doesn't apply, and
unlike the app's `el()` helper, the DOM's `replaceChildren()`/`append()` does **not** skip
`null`: it converts it to the text node `"null"`. On an ordinary piece (below the grading
threshold, not needing verification, not decaying) that's three nulls in a row between the title
row and the Status/Tempo/Difficulty panels, i.e. **"nullnullnull"**. A fourth appears if the
overview request fails. **Reproduced** against the mock with the pre-fix file (the page text read
`…Practice this piece\nBack\nnullnullnull\nSTATUS…`) and **gone** after the fix (no "null" text
anywhere on the page). Fix: collect the sections in an array and
`replaceChildren(...sections.filter(Boolean))`.

What I checked and ruled out on the way:
- **Every DOM insertion in the frontend.** I parsed all of `frontend/src` with acorn and listed
  each `append/prepend/replaceChildren/before/after/replaceWith` argument that isn't an obvious
  element or string. The four in `entryDetailView` were the only ones that can be `null`.
  `practice.js:217` and `progression.js:81` were checked by hand and always pass elements.
- **Meta-grid fields traced to source.** `PieceOverviewService.render()` in
  `backend/app/services/catalog.py` → `PieceOverview` in `schemas.py`. The only non-Optional
  `str` fields are `difficulty_band` (always one of the band names, "unrated" for None) and
  `duration_label` (the `Piece.duration_label` property returns "unknown" for None, which
  `metaRow` already filters). In `ComposerProfile`, `lifespan`/`byline` are model properties that
  never emit None (they return "" or join only present parts). `SectionRead.measure_span` is
  always "bar N" or "bars A–B". None of these can produce "null"/"None" text.
- **Frontend concatenations on the page.** No `${a}${b}${c}` anywhere on the detail path. The
  only adjacent interpolation in the codebase is `repertoire.js:346` (external search), which is
  guarded. I fixed three single-`null` leaks that would read badly (but not as "nullnullnull"):
  - plan step `~${est_days}d`, which rendered "~nulld" when `est_days` is null (Optional);
  - interpretation stats, which rendered "null bpm off" / "rubato variance null";
  - movement rows, which rendered `null. Title` when `movement_number` is null.

  All three now use the `[...].filter(Boolean).join(" · ")` pattern or a guard.
- **The database, which I couldn't check.** A literal "null"/"None" string stored in a text
  column would display as-is; I couldn't inspect this because Postgres isn't running. The most
  plausible writer is the metadata generator: `_normalize()` in
  `backend/app/services/metadata_generator.py` copied the LLM's `historical_note`, `fun_fact`,
  `syllabus_grade`, `mood` and `scene` straight into the piece with no type or placeholder check.
  **Hardened:** a new `clean_text()` turns non-strings and placeholder text ("null", "None",
  "nullnullnull", "N/A", "unknown", …) into `None`, with 2 new unit tests. **Defence in depth on
  the frontend:** `metaRow`, the lore paragraphs (`prose`) and the mood strip now hide values
  made only of null/None/undefined and `console.warn` the field name. So if bad data already in
  your DB is behind a variant of this, the page stays clean and the console names the field.

**3c — dual difficulty.** A new `difficultyPair(personalized, baseline, {band})` component
(exported from `components/overview.js`) shows **for you** (orange on a black cell) and
**baseline · band** (neutral grey) side by side as one badge. Both are always visible, with "--"
if one is missing. It replaces the meta-grid's "Difficulty" + conditional "For you" rows **and**
the baseline-only Difficulty stat panel in `entryDetailView`. A tooltip gives the gap ("6.5
harder for you than the catalogue baseline").
- **Decision:** passage (section) difficulties and per-movement difficulties were left as single
  values. The API has no personalised score for those, so a pair would be invented data.

**Verification**: build ✔, pytest 52/52 ✔ (2 new). Headless checks: meta-grid order, both
pairs render with orange/grey computed colours, junk `fun_fact` hidden with a warning,
before/after reproduction of "nullnullnull", desktop and 390px mobile layouts.

**Summary**: Found the actual "nullnullnull" bug: null banners passed to `replaceChildren()` on
the piece detail page. It's fixed and verified before/after. I also hardened the LLM metadata
path and the overview renderer against placeholder text. Composer/Catalogue/Era/Duration now
lead the meta-grid, and difficulty everywhere on the page is a paired "for you | baseline"
badge.
