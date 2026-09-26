# RUN_NOTES — ui-ux-overhaul overnight run

## Read this first — consolidated summary (2026-09-26)

**Status:** all six phases are done, each built and tested, then committed and pushed to
`origin/ui-ux-overhaul`. **No phase was reverted.** No build or test failed at any phase gate.
`main` and `origin/master` were not touched and nothing was merged. The backend suite is **52
passed** (50 existing + 2 new), and `npm run build` is clean.

**How it was verified.** Postgres and Redis weren't running and Docker Desktop was stopped, so I
didn't start the real backend (I wasn't going to launch Docker unattended). Besides the required
build and pytest gates, I ran the Vite dev app against a small mock API and drove it with headless
Chrome to check behaviour, computed styles and console errors, with before/after reproductions for
the two bugs. The mock and scripts are outside the repo. **Nothing here has been clicked through
against your real data yet, so please do that first.**

### Decisions I made without you
1. **Phase 0:** the planned "chore: revert…" commit was skipped because there was nothing to
   commit. After restoring `onboarding.js` to `main`, both files matched `HEAD`. Cline's
   discarded edits are only in my session scratchpad, not in git.
2. **Phase 1 palette:** `--yellow #ffd08a` (the existing gold), `--orange #f0a13c`,
   `--pink #e05a78`, `--black #020202`. Tints are opacity steps of an accent.
   - Status: bad = pink + triangle marker, warn = orange + diamond, ok = white-on-black + dot.
   - Primary buttons are black with an orange outline; selected states are an orange fill with
     black text.
3. **Phase 1 constellation encoding:**
   - Link types = accent + dash pattern: composer = orange solid, technique = yellow dashed,
     era/genre = pink dotted. A type's pattern overrides the "Survey lines" dashed cosmetic.
   - Six eras = three hues, with the later era of each pair drawn with diffraction spikes. An
     era key was added to the legend.
   - Custom pieces = black core with a white outline; frozen = neutral dashed ring.
   - "Heat map" cosmetic = pink → orange → yellow → white.
4. **Phase 1 things left alone on purpose:**
   - Purchased cosmetic colours in `backend/app/seed.py` (Ice field, Emerald drift, Violet
     nursery, nebula layers). They're product data sold by name, not app accents.
   - `public/icons/favicon.svg` and its PNGs (cyan/violet). They're outside `src`, and the PNGs
     would need regenerating.
5. **Phase 2b:** Enter picks the first result only if the visible results match the current
   text; otherwise it searches immediately. Stale out-of-order responses are dropped.
6. **Phase 2c:** "saving" (`aria-busy`, "Saving…", moving orange stripes) is a separate look from
   "disabled" (dashed, faint). Yellow is the app-wide focus ring.
7. **Phase 2d:** hand-written **static one-bar snippets per category**
   (`lib/techniqueSnippets.js`), shown on each category header. No technique carries a note
   pattern, and the backend's category builders are random 8-bar exercises, several of them poor
   illustrations (fourths for "double notes", a fifth for "stretches"). Polyrhythm is only
   approximate, because `renderNotation()` has no tuplets.
8. **Phase 3b:** fixed the root cause, and also hardened the LLM metadata normalizer and the
   overview renderer against placeholder text as defence in depth.
9. **Phase 3c:** section and movement difficulties stay single values (the API has no personalised
   score for them).
10. **Phase 4a:** a new `pointerdown` finishes *any* live drag or pan, not just one from a
    different pointerId, because the mouse reuses pointerId 1 after a lost `pointerup`.
    `pointercancel` no longer opens the piece detail.
11. **Phase 4b:** `dot = 1.6·(9.5/1.6)^(d/100)` and `radius = 2.8·dot`. The hardest stars' mass
    roughly doubles (≈1.7 → ≈3.4). If they feel sluggish, lower `RADIUS_PER_DOT`.
12. **Phase 5:** I restyled the existing header level bar into a labelled XP bar instead of adding
    a second bar, because `level_progress` already is XP-into-level. On small screens the header
    hides the "online" pill while online (offline still shows) and hides gold at ≤360px.

### Bugs found and fixed
- **"nullnullnull" on Piece Detail: root cause found.** `entryDetailView` passed null banners to
  `replaceChildren()`, and the DOM renders each `null` as the text "null". An ordinary piece
  gets three in a row. Reproduced before the fix and gone after it. Details are under
  "Piece Detail — nullnullnull" below.
- **Constellation stranded star**, reproduced on the old code (a star stayed grabbed forever)
  and fixed.
- **Tier-quiz Continue label:** "Rank every technique (0/N)" now shows from the start.
- **Tier hover** was losing a specificity fight with `.btn-ghost:hover`.
- **Unguarded `null`s on the detail page:** "~nulld" on plan steps, "null bpm" in
  interpretation stats, "null. Title" on movements.

### Still open / worth your attention
- **Nothing is known broken.** Please click through against the real backend, especially:
  - the constellation feel with the new masses;
  - whether your existing data contains literal "null"/"None" strings. The frontend now hides
    them and logs `[piece overview] "<field>" arrived as placeholder text` in the console.
- **Backend gap (not fixed):** `GET /catalog/techniques` returns `TechniqueRead`, which has no
  `mechanic` field, so the onboarding tier list's mechanic sub-line never shows with real data.
- `api.wallet()`/`api.ledger()` were kept as instructed, but they now have **no callers** (I
  couldn't find a ledger view in `frontend/src`).
- `npm install` reported 3 advisories (2 moderate, 1 high) that I didn't address. The esbuild
  postinstall "allowScripts" warning is harmless for the build.
- Follow-ups outside `src`: the favicon/PWA icons still use cyan/violet, and the cosmetic seed
  descriptions say "Cool for easy" for the heat map, whose easy end is now pink.

### Commits on `ui-ux-overhaul` (all pushed)
`6ce5fe7` Phase 1 tokens · `9ee232e` Phase 2 onboarding · `4d10623` Phase 3 piece detail ·
`ffb606c` Phase 4 constellation + wallet · `ca50b23` Phase 5 header XP · Phase 6 final pass
(this file + unused-token cleanup).

---

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

### 2026-09-26 — Phase 4: Constellation

**4a — drag duplication.** `dragging`/`panning` are now owned by an explicit `activePointer`,
and all release logic lives in one `finishInteraction()`, which releases capture, clears the
pan, calls `release()` on the grabbed star, spawns the throw ripple, and opens the detail only
on a real `pointerup`.
- `pointerdown`: if a drag or pan is still live, it's finished first. **Decision: I did this
  for *any* live interaction, not only one owned by a different pointerId** (a superset of your
  spec). The mouse always reuses `pointerId` 1, so a lost `pointerup` (e.g. focus stolen
  mid-drag) followed by a new press is a *same-id* case, and it strands a star exactly like
  the two-finger case.
- `pointermove` from a pointer that doesn't own the interaction is ignored.
- `endPointer()` returns early unless `event.pointerId === activePointer`, so a stray up or
  cancel from another finger no longer releases (or throws) the star someone else is holding.
  It's also wired to `lostpointercapture`, and a window `blur` finishes any live interaction.
- `setPointerCapture` is now in a try/catch, and capture is taken only when a drag or pan
  actually starts (no capture-then-release for connector taps).
- **Behaviour change:** `pointercancel` no longer opens the piece detail. Only a real tap
  (`pointerup` with <3px movement) does.
- **Evidence** (synthetic pointer events against a temporary, uncommitted debug hook):
  - Pre-fix code, press star A then star B with pointerId 1 and no up in between: both
    grabbed; after the up, **star 20 stayed grabbed forever**. That's the reported glitch.
  - Post-fix: B's press releases A; a stray up from finger A leaves B held; B's up releases B;
    the same-id case cleans up; nothing is left grabbed.
  - Real mouse input: click opens detail; drag holds, then throws on release (speed 9.7);
    nothing stranded.

**4b — star size.** Measured the difficulty distribution from `backend/app/seed.py` (stored as
`scale100`, i.e. 0–100): 23 catalogue pieces, **min 30, p10 40, median 78, p90 92, max 98**.
It's heavily clustered in 75–95, which the old linear ramp (dot 3.0→6.8) compressed. New:
`dot = 1.6 · (9.5/1.6)^(d/100)` gives d=30 → 2.7, 50 → 3.9, 78 → 6.4, 90 → 8.0, 98 → 9.2, so
the crowded top end now spreads out (78→98 grows 43%, versus 20% before). `radius = 2.8 × dot`
follows the same curve, so size and mass stay proportional.
- **Trade-off to be aware of:** `massOf()` = r²/190, so the hardest stars go from mass ≈1.7 to
  ≈3.4 (heavier and slower to throw, and less affected by the ambient current), while easy ones
  stay at the 0.45 floor. This is intended ("looks bigger, feels heavier"), but if the big stars
  feel sluggish, lower `RADIUS_PER_DOT` in `constellation.js`.
- The API's own `radius` field (`progression.py`, a linear formula) was already ignored by the
  frontend and is left unchanged.

**4c — header / Observatory desync.** `shop.js` no longer calls `api.wallet()`. `renderWallet()`
now calls `store.refreshProfile()` and draws from `store.wallet`, the same source as the header.
`shopView` subscribes via `subscribe()` from `lib/store.js` and redraws the wallet on any store
change.
- The subscriber only *draws*, it never refetches. If it called `refreshProfile()`, that would
  emit, which would trigger the subscriber again, forever.
- It skips redraws when nothing changed (so the level ring's animation doesn't restart), and it
  unsubscribes itself if the view is gone. `shopView` also returns the unsubscribe for the
  router's cleanup.
- The purchase handler's extra `store.refreshProfile()` + `renderWallet()` double fetch is now
  one refresh.
- `api.wallet()`/`api.ledger()` are kept in `client.js` as instructed. **Note:** a grep found no
  remaining callers (there's no ledger view in `frontend/src`), so they're currently unused.
- **Verified:** `/wallet` hit 0 times; an external `store.refreshProfile()` moved both the header
  and the Observatory from LV 4 to LV 9 together; navigating away and back threw no errors.

**Verification**: build ✔, pytest 52/52 ✔, plus the headless checks above.

**Summary**: Constellation drags can no longer strand a star, verified before and after. Stars
now scale exponentially, which spreads apart the crowded high-difficulty range, with mass
following size. The Observatory wallet comes from the same store as the header and updates live.

### 2026-09-26 — Phase 5: header XP bar

Checked `index.html` first: the top-right is `.topbar-right` with `#wallet` (a link to
/observatory) and `#net-status`, and `main.js` inserts the Sign out button before it.

**Decision: I restyled the existing bar into the XP bar instead of adding a second one.**
`level_progress` *is* XP progress through the current level (`xp_into_level /
(xp_into_level + xp_for_next_level)`, per `Wallet` in `models.py`). A second bar would show the
same quantity twice, and the only other XP figure, lifetime/total XP, has no target to fill
towards. So the old 54×3px sliver became a proper XP bar right next to the level pill:
- **Level pill:** "LV n" as a solid orange chip with black text.
- **XP bar:** a 92×7px black track with an outline and an orange→yellow fill, plus an
  "into/span xp" label (e.g. `340/500 xp`). It's `role="progressbar"` with
  `aria-valuenow`/`aria-valuemax` and "Experience toward level n+1".
- **Gold:** unchanged, yellow. The tooltip now also shows total XP.
- **The wallet link:** hover (orange outline) and focus-visible (yellow ring) states added. Only
  the four accents plus neutrals are used.

**Responsive:** at ≤720px the xp label hides and the bar shrinks to 56px. At ≤420px the brand
word hides (the logo mark stays), the "online" pill hides **only while online** (the orange
"offline" pill still shows), and spacing tightens. At ≤360px gold hides; it's still on the
Observatory. Header buttons no longer wrap. Verified: no horizontal overflow at 1100, 720, 420,
390, 360, 340 and 320px.

**Verification**: build ✔, pytest 52/52 ✔, plus headless header checks at the widths above.

**Summary**: The header's level pill now has a clearly labelled XP bar beside it (the old
unlabelled sliver, restyled rather than duplicated), with correct progressbar semantics. The top
bar also fits down to 320px without overflowing.

### 2026-09-26 — Phase 6: final pass

- **Colour-literal sweep of `frontend/src`.** The only hex codes left are the `:root` token
  definitions in `styles.css` and their runtime-fallback mirror in `lib/palette.js` (plus
  `#ffffff` for the star highlight core). The only numeric `rgba()`s left are neutrals: the white
  scanline texture, the dark topbar/modal/legend scrims, and transparent canvas gradient stops.
  No named colours are used in styles.
- **Token check:** every `var(--…)` used in JS or CSS is defined. Two tokens that ended up
  unused (`--pink-line`, `--yellow-wash`) were removed.
- **End to end:** `npm run build` ✔ and full `pytest` ✔ (52 passed). A headless sweep of every
  route (/, /repertoire, /repertoire/:id, /constellation, /practice, /progression,
  /performances, /observatory) and all four onboarding steps showed no JS exceptions. The only
  console noise was 404s for endpoints the mock doesn't implement.

**Summary**: The final sweep confirmed the four-token system holds across `frontend/src`, with
only definitions and neutrals left. The build and all 52 tests pass. The consolidated summary is
at the top of this file.

---

# Run 2 — Phases 7–12 (2026-09-26)

## Read this first — run 2 summary

**Status:** every phase is done, built and tested, and committed and pushed to `origin/ui-ux-overhaul`
(no merge; `main` untouched). The backend suite is **68 passed** (52 → 68, 16 new) and `npm run build`
is clean at every gate. Phases ran in the order **7, 8, 9, 11, 12, 10**; the reason is below.

**This run was verified against a real backend**, which the previous one wasn't. Docker was up, so I used a
separate scratch database, `piano_uitest`, on your Postgres container. Your `piano` DB was only ever
*read*: a few `SELECT count(*)`s and a technique list.

**Four things need your eyes:**
1. **Phase 11's premise didn't hold.** `passageSightReading()` doesn't render real passage notes: no
   passage stores any. It forges a pattern. The stem and stave bugs were in `renderNotation()` itself. I
   fixed the renderer, made the forge technique- and key-aware, and label the result as a practice pattern
   next to the *real* passage details. Details are under Phase 11.
2. **Placeholder bar numbers** for the two passages you asked for: Pas de deux **1–8** and Mephisto **111–142**.
   Please correct them in `seed_lore.PASSAGES`, then run `python -m app.seed` to load both pieces into your DB.
3. **Phase 12: no slow path found.** No LLM runs when saving the top ten, and the save measured
   ~55ms server-side and ~105ms click-to-next-step. I didn't move anything to the queue. A DevTools
   Network screenshot from your machine would pin it down. See Phase 12.
4. **Phase 10 is a real redesign.** It's documented decision by decision in **`DESIGN_NOTES.md`**, with three open
   questions at the end.

| Phase | Commit(s) | One line |
|---|---|---|
| 7 Palette | `a5fd409` | `--black` removed; `--starlight #e8ecf5` added (also the backdrop stars); selected = starlight |
| 8 Meta-grid gap | `6bdf60c` | Not orphaned rows: the wrapped Difficulty cell stretched its grid row. It's now a full-width row |
| 9 Submissions | `41ce9c4` | "Practice recordings" and "Notes & scores" are separate sections; checkbox layout fixed |
| 11 Notation | `238e217` | "?" per row; real catalogue passage + honest pattern; renderer and forge fixed; 2 pieces seeded |
| 12 Top-ten latency | `ac511eb` | Profiled; no LLM on that path; findings only |
| 10 Declutter | `c3cdf67` `ef473e2` `426988b` `a32aae0` `a870010` `7de6404` | One commit per view; see `DESIGN_NOTES.md` |

**Other fixes found along the way:**
- The seed crashed on re-run once any assessment existed, and cascade-deleted drills. It now upserts.
- New composers never reached an already-seeded DB.
- The forge's key label didn't match its notes.
- The polyrhythm bars were 2.5 beats long.
- The synth couldn't play flats.
- `TechniqueRead` lacked `mechanic`, which was last run's open item.
- The heat-map preview's hottest dot wasn't starlight.

**Known gaps left open:**
- **Broken octaves** has no catalogue passage. It's logged and not fabricated.
- The tap-tempo curve is never submitted.
- `import_external()` blocks on the LLM. It's a separate flow from the top ten.
- The favicon still uses the old cyan/violet, as noted last run.

**Scratch environment:**
- `piano_uitest` is still on the container. Drop it with
  `docker exec piano-db psql -U piano -c "DROP DATABASE piano_uitest"`.
- The test servers on :8001 and :5174 have been stopped.
- The harness scripts live only in the session scratchpad.


Branch check: `ui-ux-overhaul` was **not** merged into `main` (`origin/main` is still `5886966`), so
this run continues on `ui-ux-overhaul` rather than branching `ui-ux-overhaul-2`.

**Verification harness this run.** Docker was up this time (piano-db + piano-redis already running).
To avoid touching your real `piano` database I created a separate database **`piano_uitest`** on the
same Postgres container (`create_all` from the models + `python -m app.seed`), ran uvicorn against it
on **:8001** with `ANTHROPIC_API_KEY` blanked, and Vite on **:5174** proxying to it. Headless Chrome
(puppeteer-core, installed in the session scratchpad, not the repo) drives two throwaway users
(`ui-done@example.com` onboarded, `ui-fresh@example.com` fresh). Your `piano` database was never
written to. Drop the scratch DB with `docker exec piano-db psql -U piano -c "DROP DATABASE piano_uitest"`.

### Phase 7 — Palette correction

- `--black` is gone from `styles.css` `:root`, `lib/palette.js`, `constellation.js` and `shop.js`.
  A frontend-wide grep for `black` / `020202` now finds only `apple-mobile-web-app-status-bar-style
  = black-translucent` in `index.html`, which is an iOS keyword, not a colour, and was left alone.
- **Decision — the starlight value.** You said to reuse the constellation backdrop-star colour.
  `drawBackdrop()` actually painted with `colors.text` = `#ddd9d3`, a *warm* grey outside the
  #eef2ff–#dfe4ec range, and no cool near-white existed anywhere in the codebase. Reusing `#ddd9d3`
  would make starlight indistinguishable from body text. So I set **`--starlight: #e8ecf5`** (inside
  your range) and switched `drawBackdrop()` to `colors.starlight`, so the token and the backdrop
  stars are the same colour as you intended. The one-off `#ffffff` core highlight on top-ten/active
  stars was folded into starlight too.
- **Remapping — every former black usage:**
  | Where | Was | Now |
  |---|---|---|
  | `.btn` primary rest | black fill, orange outline | 8% orange tint, orange outline + text, weight 600 |
  | `.btn` hover | solid orange, black text | 20% orange tint, starlight text, glow |
  | `.btn` pressed | solid yellow, black text | 24% yellow tint, yellow text |
  | tier button selected | solid orange, black text | starlight outline + 8% starlight wash, starlight text, weight 700 |
  | tier button pressed | solid yellow, black text | 18% yellow tint, yellow text |
  | genre chip selected (`.pill-toggle[aria-pressed]`) | solid orange, black text | starlight outline + wash, weight 600 |
  | `.btn-danger` rest / hover | black fill / solid pink with black text | transparent / 20% pink tint, starlight text |
  | status `ok` (`--ok`, `--ok-fill`, `.pill-ok`, success toast) | white on black | starlight text on starlight wash, starlight border (dot marker unchanged) |
  | `.pill-custom` / custom-piece star | black core, white outline | `--bg-sunk` core, starlight dashed outline |
  | header level pill | solid orange, black text | orange wash + orange outline, orange text, weight 700 |
  | difficulty pair "for you" half | black cell | orange-wash cell |
  | ghost / option-card pressed, focus-ring gap, constellation well, XP track, nebula swatch | `--black` | `--bg-sunk` (background scale — structural, not accent) |
  | heat-map cosmetic hottest tier | `white` | `starlight` |
- Net effect: selected = **starlight**, action = **orange**, pressed = **yellow**, danger/bad = **pink**,
  and no control anywhere is a solid accent block with near-black text on it.

**Verification**: build ✔, pytest 52/52 ✔, dashboard/repertoire/constellation/observatory/onboarding
rendered against the scratch backend with no console errors.

### Phase 8 — Piece Detail meta-grid gap

- **The suspected cause wasn't there.** `pieceOverview()` had no orphaned `metaRow()` calls: the old
  "For you" row was already deleted in Phase 3c and there's exactly one Difficulty row. `metaRow()`
  returns `null` for empty values and `el()` drops nulls, so there were no blank DOM cells either.
- **Actual cause (measured in headless Chrome):** the Difficulty cell used
  `.meta-row:has(.difficulty-pair) { flex-wrap: wrap }`, so the paired badge wrapped under its label
  and made that cell 77px tall versus 39px for the others. CSS grid stretches every item in a row to
  the tallest one, so Composed/Marking/Genre/Mechanical load (the cells sharing Difficulty's row) each
  grew a ~38px empty band under their label/value — that's the "empty row" under the badge before the
  Character strip.
- **Fix:** Difficulty is now a full-width row (`.meta-row-wide`: `grid-column: 1 / -1`, label and
  badge side by side, no wrap), and the grid uses `grid-auto-flow: row dense` so the cell that used
  to follow Difficulty backfills instead of leaving a hole. The `:has()` wrap rule was removed.
  Measured after: every ordinary cell is 39px at 1280, 900 and 390px widths; the difficulty row is 54px
  and no other cell shares it.
- The Physical-load grid had no such issue (no tall cells).

**Verification**: build ✔, pytest 52/52 ✔, grid geometry probed at three widths, no console errors.

### Phase 9 — Recordings vs. other submissions

- `submissionsPanel()` in `repertoire.js` was a single "Submissions" panel with one mixed history list
  and three stacked forms (notes, PDF, recording). It is replaced by `submissionSections()`, which
  renders two separately-labelled `<section>`s side by side (stacked under ~760px):
  - **Practice recordings** (`recordingPanel`): audio history only, plus the recording form (file,
    Full run-through, Verification take, tap-tempo, **Submit recording**). It has an orange top rule so
    it reads as the primary flow — it's the one that clears the grading gate and verification.
  - **Notes & scores** (`writtenSubmissionPanel`): text + PDF history, plus **Submit notes** and
    **Upload score** (renamed from "Submit score" so no two buttons on the page share a verb+noun
    pattern with the recording button). This mirrors `services/analyzers.py`: `TextAnalyzer` +
    `ScoreAnalyzer` vs. `AudioAnalyzer`.
- History cards now say "Recording" / "Practice notes" / "Scanned score" plus the date, instead of
  the raw `audio`/`text`/`pdf` enum.
- The verification banner copy now points at "Practice recordings below" instead of "the submissions
  panel".
- **Fixed along the way:** checkboxes inherited `input { width: 100% }`, so "Full run-through" /
  "Verification take" were squeezed into a 3-line column. Checkboxes/radios now size to 16px with
  `accent-color: var(--orange)`, and the labels use a new `.check-label` class.
- **Noticed, not fixed:** `tapTempoWidget().curve()` is never read — the tap-tempo curve isn't sent
  with the recording (`api.submitAudio` has no parameter for it). That was already the case before
  this run; wiring it needs a backend field, so I left it.

**Verification**: build ✔, pytest 52/52 ✔, rendered with a real text + audio submission against the
scratch backend at 1280 and 390px, no console errors.

### Phase order (decision)

Phase 10 says to reuse "the same click-to-reveal pattern used for the tier-list notation in Phase
11", and Phase 12 changes the top-ten step that Phase 10's onboarding audit covers. So I ran
**11 → 12 → 10**: the declutter pass then works on the final state of every view and reuses a pattern
that already exists. Each phase is still its own commit.

### Phase 11 — Tier-list notation, full redo

#### ⚠ Read first: the premise of 11b didn't hold, and here's what I did instead

1. **`api.passageSightReading()` does not render the real passage.** No passage in the database
   stores notes: a `Passage` has only bars, label, difficulty, description and cue. The endpoint
   (`GET /catalog/passages/{id}/sight-reading`) runs `SightReadingForge(seed).generate(category, difficulty)`,
   the same randomised per-category builders from the last run, seeded by the passage ID. The piece page
   even labels it "representative pattern". So "render that real passage" would have produced a
   generic pattern again, and for sixths it would have produced *thirds*: the double-notes builder
   only knew thirds and fourths.
2. **The stem-direction and wrong-stave bugs were in the renderer, not in the patterns.**
   `renderNotation()` pointed every treble stem up and every bass stem down (`stemUp = clef === "treble"`),
   drew a separate stem for every note of a chord, and put each *note* on a staff by middle C. So any
   one-hand leap crossing C4, or an octave B3–B4, was split across both staves. `sectionCard()` on the
   piece page had the same bugs. Real passage data would *not* have fixed them.

So, following your pipeline (highest-weighted marked passage → `passageSightReading` →
`renderNotation`), I fixed the two things that stood between it and correct output, and I labelled the
result honestly instead of calling it a score excerpt:

- **The renderer is rewritten** (`lib/notation.js`, same API):
  - one stem per chord, with direction set by the standard rule (the note farthest from the middle
    line decides; ties go down);
  - beaming within each beat, with secondary beams for sixteenths, stems at least 2.5 spaces long,
    and flags on the correct side;
  - a whole chord always stays on one staff;
  - `hand: "right" | "left"` renders a **single stave**, and `hand: "both"` or a `left` voice renders
    the grand staff with right hand = treble and left hand = bass;
  - key signatures (up to 5♯/5♭), accidentals only where they differ from the key, and flats
    supported, all drawn as SVG paths (the ♯ font glyph rendered orange-tinted on Windows);
  - time signature, triplets (`tuplet: 3`) with a "3" over the beam, and a viewBox fitted to the
    content so ledger lines never clip;
  - default width is now ~110px per bar, so the 8-bar Piece Detail/Practice patterns are no
    longer crushed into 560px.
- **The forge is now technique-aware** (`services/notation.py`;
  `generate(category, difficulty, technique=None, key=None)`, backwards compatible):
  - Double sixths draws sixths and Double thirds draws thirds, instead of thirds/fourths by
    difficulty. Broken octaves alternate; Blocked stay blocked. Arpeggio figuration draws
    broken-chord arpeggios instead of a scale.
  - **Polyrhythm is actually polyrhythmic now:** 3:2 is RH triplet eighths against LH eighths, and
    4:3 is RH sixteenths against LH triplet eighths. Before, it was a single voice of three
    eighths plus a quarter, which is **2.5 beats in a 4/4 bar**.
  - **Key bug fixed:** the forge picked a key *label* at random but always built the notes on C, F or G.
    The notes now match the key. Flat keys are spelled with flats, and the synth now parses flats,
    which it couldn't before.
  - The passage endpoint passes the piece's own key (`forge_key()`; minor keys use their relative
    major's signature). So the Pas de deux example is in G, Mephisto is in A, and Rachmaninoff's
    C minor uses the E♭ signature. It also takes `?technique_id=` so the pattern illustrates the row's
    technique, not the passage's top-weighted one.
  - Every single-hand category declares `hand: "right"` (pedalling: `"left"`), so leaps and jumps
    render on **one stave**. Verified: each opened example has one 5-line stave, and polyrhythm has two.
  - The coach's sight-reading exercises pass the technique name too, so they benefit.
- **The UI never presents it as the score.** Each example shows the **real** passage (piece, composer,
  bars, label, description) above the pattern, and the caption under it reads *"Practice pattern built
  from this passage's double sixths · G · 128 bpm. Not an engraving of the printed score."*

**If you want actual score excerpts** (the real notes of the Tchaikovsky and Liszt passages), that needs
a new `notation` JSON column on `passages`, a migration, and transcriptions checked against a score. I
didn't transcribe anything from memory, because a wrong "real" excerpt would be worse than an honest
pattern. The renderer is now ready for real data: it handles two voices, chords, key signatures and
single-stave hands.

#### 11a — hidden by default
- Every technique row in `tierQuizStep()` has a small round **?** button (`.tier-help`, `aria-expanded`,
  `aria-controls`, `aria-label="Show an example of Trills"`). **Nothing renders up front:** 0 SVGs on
  load, and 17 "?" buttons, verified in the browser. The first click fetches the examples list (once per
  quiz, cached), then that row's pattern. Closing a row stops its playback.
- The old per-category header snippets and `lib/techniqueSnippets.js` (hand-written patterns) are **deleted**.
- The click-to-reveal is a new reusable `disclosure()` in `lib/dom.js` (button + lazily-filled
  region), which Phase 10 reuses.
- Each revealed example shows the passage, a **Play** button, and one bar of sixteenths (or two bars
  of anything slower), which scales to fit on mobile.
- Tier rows no longer wrap their S–D buttons onto two lines, and they stack on phones.

#### 11b — real passage lookup
- New `GET /catalog/techniques/examples` (`TechniqueExampleService` + `pick_technique_examples()` in
  `services/catalog.py`): for each technique, the catalogue passage with the highest
  `PassageTechnique.weight`, with ties broken by passage difficulty. Only `source = catalog` passages on
  non-user pieces are used, so nobody's private analyzer-found "Hard bar"s leak into onboarding.
- Bonus fix for last run's open item: `TechniqueRead` now includes `mechanic`, so the tier list's
  mechanic sub-line finally shows with the real backend.

#### 11c — Pas de deux (sixths) and Mephisto Waltz No. 1 (leaps)
Neither was seeded. Added to `seed.py`/`seed_lore.py`: composer **Pyotr Ilyich Tchaikovsky**, genres
**Ballet** and **Waltz**, the pieces, their lore, and one marked passage each at weight **1.0**, so each is
the top example for its row. Verified: Sixths → *Pas de deux, The Nutcracker*, and Leaps → *Mephisto Waltz No. 1*.

**⚠ Please check these. I couldn't verify them against a score:**

| | Value I used | Confidence |
|---|---|---|
| Pas de deux passage bars | **1–8**, "The scale theme in sixths" | **placeholder**: correct them to the bars you mean |
| Mephisto passage bars | **111–142**, "Right-hand chorus leaps" | **placeholder**: correct them to the chorus bars |
| Pas de deux key / catalogue | G major, Op. 71 | fairly sure (Intrada theme) |
| Pas de deux arrangement | lore says pianists usually play **Pletnev's** concert arrangement | an assumption about which version you mean |
| Mephisto | A major, S. 514, 1862, Allegro vivace, Lenau programme | confident |
| Difficulty / duration | Pas de deux 8.8 / 5:30; Mephisto 9.5 / 11:00 | judgement |

The descriptions avoid claims I couldn't back up. To correct the bars, edit the tuples in
`seed_lore.PASSAGES` and re-run `python -m app.seed`.

**Getting them into your real DB:** run `python -m app.seed`. `seed_catalog_detail()` now also inserts
missing composers and genres (before, a new composer would never reach an already-seeded DB, because
`seed()` exits early).

**Seed bug fixed on the way.** Re-running the seed deleted and recreated every catalogue passage, which:
- **crashed** as soon as any `passage_assessment` existed (I hit it on the scratch DB after one text
  submission);
- **cascade-deleted users' drills** tied to catalogue passages.

Passages are now upserted in place, matched on (piece, label). Stale ones are deleted only when nothing
references them. Your real DB currently has 0 assessments and 0 drills (checked read-only), so it's
unaffected so far.

#### 11d — Arpeggios
**Already exists** as **"Arpeggio figuration"** (id 8, category *dexterity*) in `TECHNIQUES` *and* in your
real DB. It was already in the tier list, under the "dexterity" heading next to Rapid scales (verified in
the browser: all 17 rows render). I didn't add a duplicate. Its example is Ravel's *Jeux d'eau*,
"Opening cascade" (bars 1–18, weight 0.95), and it now draws a broken-chord arpeggio rather than a
scale. If "Arpeggio figuration" was just hard to spot, renaming it is a one-line change, but I didn't
want to rename catalogue data without asking.

#### 11e — Scales
"Rapid scales" is linked: *Winter Wind*, "The storm entry" (bars 5–12, 0.95).

#### 11f — Coverage for all 17 techniques
Every technique has a catalogue passage **except Broken octaves**. No seeded passage is tagged with it
(the Hungarian Rhapsody's octave run is tagged *Blocked* octaves). **Not fabricated.** The row's "?" says
*"No marked passage in the catalogue uses this technique yet."* That's catalogue-expansion work. A test
(`test_every_technique_has_a_catalog_passage_except_known_gaps`) pins the gap list, so adding a passage
will remind whoever does it to update the list.

| Technique | Example passage |
|---|---|
| Double thirds | Chopin Op. 25/6, bars 33–44 |
| Double sixths | **Tchaikovsky Pas de deux, bars 1–8** (new) |
| Broken octaves | **none — gap** |
| Blocked octaves | Hungarian Rhapsody No. 2, bars 300–320 |
| Wide leaps | **Mephisto Waltz No. 1, bars 111–142** (new) |
| Repeated chords | Rachmaninoff Prelude in G minor, bars 61–88 |
| Rapid scales | Winter Wind, bars 5–12 |
| Arpeggio figuration | Jeux d'eau, bars 1–18 |
| Repeated notes | Für Elise, bars 77–82 |
| Trills | Chasse-neige, bars 1–12 (a tremolo, tagged as trills in the seed data) |
| Tenth stretches | Rachmaninoff Concerto 2/I, bars 1–9 |
| Three against two | Brahms Rhapsody Op. 79/2, bars 1–12 |
| Four against three | Rachmaninoff Concerto 2/II, bars 5–28 |
| Melody over accompaniment | Chopin Nocturne Op. 9/2, bars 25–28 |
| Inner voice projection | Chasse-neige, bars 25–44 |
| Half pedalling | Clair de lune, bars 27–42 |
| Sustained endurance | Winter Wind, bars 81–96 |

**Verification**: build ✔, pytest **68/68** ✔ (16 new in `tests/test_notation.py`: the named intervals,
notes inside the labelled key, flat spelling, hand declarations, complete polyrhythm bars in both hands,
key mapping, example ranking and catalogue coverage). Seed run twice on the scratch DB (idempotent).
Every tier example was opened in headless Chrome at 1280 and 390px: one stave for single-hand patterns,
two for polyrhythm, 0 SVGs before any click, and no console errors. The Piece Detail "Hardest sections"
pattern was re-checked.

### Phase 12 — Onboarding top-ten save latency

**Result: the suspected slow path isn't on this route, and I couldn't reproduce slowness. Nothing
was moved to the queue and no code changed. Profile below, as you asked, rather than a further guess.**

**Is an LLM call blocking the save? No.**
- `topTenStep()` only ever sends catalogue `piece_id`s. Its search is `api.searchPieces` →
  `GET /catalog/pieces`, catalogue only.
- `OnboardingService.set_top_ten()` → `CatalogService.resolve_piece()`: for a `piece_id` that's a
  single `session.get(Piece, id)`. For an inline custom `piece` payload it's `create_user_piece()`,
  which is pure arithmetic with no generator.
- The **only** caller of `MetadataGenerator` / the `anthropic` package in the backend is
  `CatalogService.import_external()` (`POST /catalog/external/import`). That's the Repertoire page's
  "add from the external (OpenOpus) catalogue" flow, not onboarding.
- Your real DB (read-only check) has 1 user, 1 repertoire entry, 27 catalogue pieces and **0**
  OpenOpus or custom pieces, so no piece you could pick has ever gone through the generator.

**Measured timings.** Scratch backend on the same Postgres container; 1 piece; warm process; data volume
matches yours (27 pieces, indexed `repertoire_entries`).

| Path | Timing |
|---|---|
| `PUT /onboarding/top-ten`, server work (curl → `127.0.0.1`) | **46–72 ms** |
| Same request via curl → `localhost` | **~257 ms**, of which **~206 ms is TCP connect** |
| Any trivial GET via curl → `localhost` (e.g. `/catalog/techniques`) | ~235 ms (same ~206 ms connect) |
| Real UI flow in Chrome through the Vite dev proxy: click Continue → PUT → refresh (`summary` + `techniques`) → tastes step `genres` → rendered | **~105 ms total** (PUT finished at 55 ms) |
| Chrome fetching the API directly, as a production build does (`localhost` vs `127.0.0.1`) | 18–30 ms vs 9–28 ms |

**The one real latency source I found (not confirmed as your symptom).** On this machine `localhost`
resolves to IPv6 `::1` first, but uvicorn / `fastapi dev` listen on IPv4 `127.0.0.1` only. A client
that tries `::1` first without a fast fallback pays **~200 ms per new connection**. curl does. Chrome
and Vite's Node proxy don't (both measured fast). On some Windows setups the refused `::1` attempt takes
~2 s instead. If your slowness comes from some other client or a different Node/OS networking
config, pointing things at `127.0.0.1` (`VITE_API_URL=http://127.0.0.1:8000` in `frontend/.env`,
`DATABASE_URL=...@127.0.0.1:5432`) removes it. I didn't change defaults, because in this stack it
isn't what makes the save slow.

**Also ruled out:**
- `DEBUG=true` root DEBUG logging: 0 SQLAlchemy lines are emitted per request, so no console-I/O cost.
- Service worker: only in production builds, and it never intercepts the PUT.
- Data volume and missing indexes: data is tiny and indexes exist.

**What would pin it down on your machine.** In DevTools → Network, click Continue on the top-ten step
and check two things:
1. whether the long bar is the `PUT /api/v1/onboarding/top-ten` itself, or the follow-up GETs;
2. in its **Timing** tab, whether the time is "Initial connection" (→ the `localhost` issue above) or
   "Waiting for server response" (→ backend work, and then the uvicorn log line helps).

With that one screenshot I can fix the right thing.

**Noticed, not changed:** `import_external()` *does* block its HTTP request on the Claude call (up to
the SDK timeout) when `ANTHROPIC_API_KEY` is set. If adding pieces from the external catalogue feels
slow, that's the place for the queue move you described. It's a separate flow from the one you
asked about, so I left it alone.

**Verification**: no code changed in this phase. The build and pytest 68/68 were re-run as the gate.

### Phase 10 — Declutter (run last; see "Phase order" above)

Full reasoning, before/after measurements and every layout decision are in **`DESIGN_NOTES.md`**.
Headlines:
- **Piece detail:** 3,792 → 2,636px.
  - One status strip with inline editing, instead of a status tile *plus* a separate "Change status" panel.
  - A practice column (plan, recordings, notes) beside the reference column.
  - Reveals for history, extra metadata, technique mechanics and faults, the composer bio, load
    measurements, sections beyond 3, plan steps beyond 3, and the upload forms. The recording form
    auto-opens when a verification or graded take is still owed.
- **Repertoire:** Search + Status up front; Genre, Composer and Difficulty behind "More filters",
  which auto-opens with an active count; a "Clear filters" link; status as quiet text.
- **Onboarding:** a real progress stepper; tier rows are one line, with the mechanic moved into the
  "?" reveal; no nested scroll box; a sticky Continue.
- **Observatory:** 2,305 → 1,946px. A wallet strip; each shop section is captioned with what's equipped
  and how many you own; equipped = starlight (selected), not orange; achievements show progress plus
  the next 3, with all 14 on demand.
- **Constellation:** one instruction line instead of two partial ones; the header shows the chart
  size; a new "How to read the chart" reveal explains the star and line encoding.
- **Dashboard:** a stats strip, section titles, and quieter in-progress rows.
- **Shared:** `.section-title` / `.section-caption`, `reveal()` and `sectionBlock()` in `lib/dom.js`
  (built on Phase 11's `disclosure()`), a `--space-1..6` scale, and `.summary-bar`, `.flat-list` /
  `.flat-row`.

**Nothing was removed.** Every datum that left the default view is one labelled click away. This was
verified by opening every reveal on the piece detail page (8/8 with content). The four-token colour rule is
untouched. Practice, Progression and Performances were re-screenshotted to confirm they're unaffected, and the
8-bar Practice forge renders with the new engraving.

**Verification**: build ✔ and pytest 68/68 ✔ after each of the six view commits; 1280 and 390px screenshots of
every reworked view against the scratch backend; no console errors.


---

# Run 3 — Phases 13–26 (2026-09-26)

Branch check: `ui-ux-overhaul` is still **not** merged into `main` (`origin/main` = `5886966`), so this run
continues on `ui-ux-overhaul` rather than creating `feature-roadmap`.

### Phase 13 — AI foundation

#### State before any change (audit, as requested)

| Service | Calls the Anthropic API? | What it actually is | Runs on a request path? | Once per subject? |
|---|---|---|---|---|
| `services/metadata_generator.py` | **Yes**, the only one. `anthropic.AsyncAnthropic().messages.create(model="claude-sonnet-4-5")`, a retired model ID, with free-text JSON parsed by `json.loads` (no structured outputs), and any exception silently falling back to a seeded-random heuristic | Per-piece scene / history / fun fact / syllabus grade / mood, plus **technique weights and "hard bars"**, which feed the difficulty score | **Yes.** `CatalogService.import_external()` awaits it inside `POST /catalog/external/import`, so the HTTP request blocks on the LLM | **Partly.** A second import of the *same* OpenOpus `external_ref` returns the existing piece without regenerating. `Piece.metadata_generated_at` and `metadata_generation_model` columns exist. But there's no claim or lock: two concurrent imports of the same work both pay, and nothing records spend |
| `services/difficulty.py` | **No** | Pure deterministic maths: `compute_mechanical_load`, `compute_difficulty_score`, bands, tier→profile, personalisation, mastery | n/a, microseconds | n/a |
| `services/coach.py` | **No** | Deterministic: `DrillForge`, `PlanBuilder`, `SightReadingGenerator` (the notation forge), `PolyrhythmTrainer`. **There is no per-submission "coach feedback" at all**; that's new work for Phase 15 | n/a | n/a |
| `services/interpretation.py` | **No** | Deterministic tempo-curve comparison against a synthetic reference curve | n/a | n/a |
| `workers/queue.py` | n/a | `InlineQueue`, `BackgroundQueue` (FastAPI `BackgroundTasks`, in-process after the response; this is what submissions use), and `RedisQueue` (arq), which is unused. **Latent bug:** `RedisQueue` enqueues the job name `"process_submission"`, but the only function arq registers is `arq_process_submission`, so any Redis-queued job would fail to resolve. The queue only knows one job type (submissions) | — | — |

So "extend the same fix to coach.py and difficulty.py" is a no-op: neither makes a paid call. The one real
synchronous paid call is the metadata generator on external import.

#### What I added

- **`ai_generations` table**: the idempotency key *and* the spend ledger for every paid call (model, migration
  `c13a1f0e2b77`, chained on your current head `a77858f33c61`; `alembic check` on a freshly migrated DB reports no
  drift). There's one row per `(purpose, subject_key)`, enforced by a unique constraint, e.g.
  `("piece_metadata", "piece:32")`. It stores the model, the full structured output, the error, input/output tokens
  and timestamps.
  - **Claiming is an atomic `INSERT … ON CONFLICT DO NOTHING RETURNING id`.** Only the job that wins the
    insert may make the paid call. Everyone else either re-applies the stored output (no call) or does nothing.
  - This is the `seed_catalog_detail()` idea (match the subject, update in place, never duplicate) made
    race-safe with a database constraint, because concurrent jobs, unlike the seed script, really can collide.
  - Because the full output is kept, re-deriving a piece's fields later never needs a second paid call.
- **`services/ai.py`**: the one place the app talks to Claude.
  - **Structured outputs** (`output_config.format: json_schema`) replace "please return JSON" and `json.loads` on
    free text. The schema pins technique names to an `enum` of the catalogue's techniques, so a hallucinated
    technique can't come back.
  - **`stop_reason == "refusal"` is handled** before reading content, and server-side refusal fallbacks are on
    (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`).
  - The token usage returned by the API is recorded in the ledger.
- **Model decision (logged, not asked).** The old code pinned `claude-sonnet-4-5`, a retired ID. The default is
  now **`claude-opus-5`**, set by `ANTHROPIC_MODEL`, with **`ANTHROPIC_EFFORT=medium`** as the default because
  this is short structured extraction. I didn't downgrade the model for cost on my own. If you want it
  cheaper, `ANTHROPIC_MODEL=claude-sonnet-5` (roughly 60% cheaper) or `claude-haiku-4-5` (80% cheaper) is a
  one-line `.env` change. Every call is now once per piece and recorded, so spend is bounded by how many pieces
  you import.
- **`services/piece_metadata.py`**: the queued job `generate_piece_metadata(piece_id)`.
  - It returns immediately if `Piece.metadata_generated_at` is set. Otherwise it claims, calls Claude (or the
    heuristic when no key is configured), and applies the result.
  - Applying under a `SELECT … FOR UPDATE` row lock re-checks "already generated". This fixed a real race the
    concurrency test caught: a losing job re-applying the winner's stored output while the winner was writing
    the same rows.
  - What it writes: technique weights → mechanical load → **difficulty score**, "Hard bar" passages, prose fields,
    and `metadata_generated_at` / `metadata_generation_model`.
- **`import_external()` no longer blocks on the LLM.** It creates the piece (title, composer, duration, source)
  and returns in ~0.1s (measured). The route commits, then enqueues `generate_piece_metadata`. A re-import of the
  same `external_ref` returns the existing piece, and at most re-enqueues a job that no-ops (measured: still one
  `ai_generations` row).
- **The queue is a named-job registry** (`workers/queue.py`: `JOBS`, `run_job`, `get_queue()`), selected by
  `JOB_QUEUE=background|redis|inline` (default `background` = FastAPI background tasks, as before).
  - **Fixed the Redis name mismatch:** arq functions are now generated from the registry with matching names.
  - Job failures are logged instead of vanishing.
  - Submissions use the same registry.
- **Seed fix:** the Phase 11 seed upsert deleted *any* catalogue passage not listed in `PASSAGES`. That would
  have wiped AI-generated "Hard bar" passages on imported pieces on every re-seed. The cleanup now only touches
  seeded pieces.
- `requirements.txt`: `anthropic>=1.8,<2`, since `fallbacks` / `output_config` need it; 1.8.0 was already installed.

#### Policy decisions to review
- **A failed paid call is not retried automatically.** The ledger row goes to `failed` with the error. The piece
  still gets heuristic technique weights and a difficulty score (so it's usable), but no prose, and it's marked
  generated. Re-running would risk paying twice for a call that may have been billed. A manual "regenerate"
  action would delete that piece's ledger row and clear `metadata_generated_at`; I didn't build that UI.
- **A crash mid-call leaves the row `running` forever**, and the piece never gets AI prose. A stale-claim reaper
  (e.g. treat `running` older than 15 minutes as failed) would fix it, but it trades against possibly paying
  twice. It's logged here rather than built.
- **Custom pieces you type in yourself** (`create_user_piece`) still don't call Claude. You supply their
  techniques. Only external imports generate.

**Verification**:
- build ✔ and pytest **72 passed, 1 skipped** ✔.
- The skipped one is an opt-in DB test (`PIANO_TEST_DATABASE_URL`). Run against a scratch DB **six times**, it
  proves three concurrent jobs plus a fourth later one make **exactly one** paid call, with the fake client
  counting calls.
- The live HTTP check against the scratch backend is described above.
- No API key was configured, so nothing here cost money.

### Phase 14 — MusicBrainz as a second catalogue source

**Interface.** `services/musicbrainz_catalog.py`'s `MusicBrainzClient.search(query, limit) -> list[dict]` mirrors
`OpenOpusClient.search` and returns the same candidate dict shape (`external_ref` = `musicbrainz:<work MBID>`,
`title`, `subtitle`, `composer_name`, `composer_external_ref`, `epoch`, `birth_year`, `death_year`), plus `source`.

**Usage policy (both hard requirements):**
- **User-Agent** on every request: `PianoPedagogue/0.1.0 ( https://github.com/creamfruit/pedagogue )`.
  - **Decision:** the contact is your repo URL, *not* your email. MusicBrainz accepts either. Putting a personal
    email in a header to a third party is something you should opt into, so it's configurable with
    `MUSICBRAINZ_CONTACT` in `.env`.
  - A test asserts the header is on every request.
- **~1 request/second:** a process-wide `Throttle` (an `asyncio.Lock` plus a monotonic timestamp, 1.1s spacing)
  serialises every MusicBrainz request; they're never fired concurrently.
  - A `503` (MusicBrainz's rate-limit reply) gets one retry after 2s, then gives up quietly.
  - Results are cached per normalised query for 15 minutes, so retyping a search doesn't spend the budget.
  - **Limitation:** the throttle is per process. If you ever run several API workers, they'd each get 1/s.
    Moving the timestamp into Redis would fix that; it's not needed for a single `fastapi dev` process.

**Search strategy (2 requests, measured ~2–3s per fresh query):**
1. **Artist index first** (`type:person`), because it searches aliases. Accept the top hit (score ≥85) only if
   one of your words is in its name, sort-name or aliases, *and* it's a classical composer (below).
2. **Then that composer's works** (`arid:<MBID>` plus your remaining words).
3. If no composer matches, fall back to a work-name search.

The work index alone missed Rachmaninoff entirely, because his MusicBrainz name is Cyrillic.

**The classical/piano bar, applying OpenOpus's standard.**

OpenOpus's validation is:
- (a) the composer is in OpenOpus, which is classical by construction;
- (b) the work is in the "Piano" genre, or, as a fallback, has a piano-form title (`PIANO_HINTS`).

MusicBrainz has neither a classical flag nor instrumentation, so the equivalents are:
- **Composer:** a MusicBrainz *composer* relationship (not performer/recording) to an artist whose
  disambiguation says "composer" ("German composer", "Hungarian composer, pianist and conductor"), or whose
  genres/tags are classical, baroque, romantic, impressionism or renaissance. Pop songwriters fail this. The
  probe's top hit for "chopin ballade" was a pop *song* titled "Chopin Ballade".
- **Work:** instrumental only (MusicBrainz language `zxx` or unset). It must have no lyricist or librettist,
  and must not be a Song, Opera, Symphony, Quartet, Soundtrack or similar type. Titles naming another
  instrument are excluded ("violon", "cello", "four hands", …), and so are orchestral or vocal forms, unless
  it's a *piano* concerto.
  - Separate movements of concertos and sonatas are dropped; the whole work is listed instead.
  - Movements of suites and sets are kept ("Suite bergamasque: III. Clair de lune" is learnt on its own).
- **Decision:** MusicBrainz works with no piano-form title are *kept* when they pass the other checks. Requiring a
  title hint, as OpenOpus's fallback does, would have dropped *Clair de lune*.

**One search, deduped by title + composer:**
- `GET /catalog/external/search` now queries both sources concurrently, and returns 502 only if *both* fail.
- Results are **interleaved** before truncating (OpenOpus's 30 Liszt works filled the whole limit otherwise),
  and merged with `catalog_match.same_work()`.
- `same_work()` compares composer surnames (so "Fryderyk" = "Frédéric" = "Frederic" Chopin). The two are the
  same work if they share a catalogue number (op./S./BWV/K./D./L./Hob. …), which catches reordered titles like
  "Sonata for Piano in B minor, S. 178" vs "Piano Sonata in B minor, S.178". Otherwise they are the same work
  if their normalised titles match and no catalogue numbers conflict. Normalising ignores accents, dashes,
  "no.", and quoted or bracketed subtitles.
  - Conflicting numbers mean different works: Schubert's D. 664 and D. 959 are both "Sonata in A".
- Merged rows carry `sources: [...]`. The UI shows OpenOpus / MusicBrainz tags, and its copy now names both
  databases.

**Import across sources:**
- `import_external` derives the source from the `external_ref` prefix; an unknown prefix returns 422.
- **Before creating a piece, it checks for the same work by that composer from any source, including the seeded
  catalogue**, and returns it. Verified live: importing MusicBrainz's "Ballade no. 1 in G minor, op. 23"
  returned the seeded Ballade No. 1, and "Mephisto Waltz no. 1, S. 514" returned the seeded piece.
- **Composers match by surname + first initial**, so MusicBrainz's "Fryderyk Chopin" reuses your
  "Frederic Chopin" instead of creating a duplicate composer (verified in the DB).
- Because the same work resolves to one piece whichever source it came from, the Phase 13 "once per piece"
  generation holds across sources too.

**Verification**:
- build ✔ and pytest **80 passed, 1 skipped** ✔. The new tests use `httpx.MockTransport` and never touch the
  network: User-Agent, throttle spacing, filters, dedupe, 503 retry, cache, Cyrillic names, and merge.
- A handful of live MusicBrainz queries were spaced ≥1.1s apart.
- The import dedupe was checked against the scratch backend, and the merged panel was screenshotted
  (8 OpenOpus + 7 MusicBrainz tags for "liszt").

### Phase 15 — The three AI features on the Phase 13 foundation

| Feature | State after the Phase 13 audit | Action |
|---|---|---|
| Description / history / fun fact on import | **Already correct after Phase 13**: queued, once per piece, stored | Confirmed, not rebuilt. Now also holds across OpenOpus and MusicBrainz (Phase 14 dedupe) |
| Difficulty / technique-weight scoring on import | **Already correct after Phase 13**: the same job writes technique weights → mechanical load → difficulty score, from the same single call | Confirmed, not rebuilt |
| Coach feedback per recording | **Didn't exist** | Built |

**Coach feedback, once per recording.**
- **Trigger:** when an *audio* submission finishes processing (`processing_status = done`), `process_submission`
  runs the `generate_coach_feedback` job.
- **Once per recording:** the same `ai_generations` claim, keyed `submission:<id>`. Re-processing a submission
  via `/retry` hits the existing claim and makes no second call (verified live: one row after a retry).
- **Where it's stored and shown:** the output is kept in the ledger and returned as `coach_feedback` on
  `GET /repertoire/{entry}/submissions` and `GET /submissions/{id}`.
- **Decision: honesty about the audio.** The audio analyzer still says "transcription and score alignment not yet
  wired", so nothing in the data describes *how the take sounded*. So:
  - The prompt tells Claude it cannot hear the recording and must not comment on sound, accuracy or
    musicality.
  - Claude gets only real data: the piece's hardest marked passages and their techniques, your tier for each
    of the piece's techniques, the take's flags (full run-through / verification / duration), a tempo-shape
    match *if* one exists, and your last three practice notes on this piece.
  - The card says so in plain words: "Written from your technique tiers, this piece's marked passages and your
    practice notes. The audio itself isn't analysed yet."
- **Output shape:** structured output with a strict schema — a summary, 1–3 focus items (passage, why for
  *you*, drill), and the next session.
- **No API key:** a deterministic coach writes the same shape. It leads with the hardest passage that uses
  your weakest-tier technique, reusing the passage's own practice cue as the drill.
- **UI:**
  - The recording card shows the coach-notes summary. The focus passages and next session sit behind a
    reveal.
  - It polls every 3s (10 times at most) while notes are being written.
  - Recordings uploaded before this feature say "No coach notes were written for this take" rather than
    spinning. They're *not* backfilled automatically, because backfilling would mean a paid call per old
    recording.

**Verification**:
- build ✔ and pytest **85 passed, 1 skipped** ✔. New `tests/test_coach_feedback.py` covers tiers, weakest-passage
  choice, the heuristic, cleaning and schema strictness.
- Live against the scratch backend: submit a recording → notes appear, retry → still one ledger row, card
  screenshotted.

### Phase 16 — Full redesign, page by page

**Order decision:** I did Phase 16 *before* 17–24 as numbered, but designed the information architecture knowing
what those phases add, so each gets a planned home (streak → Today's "This week" card; growth chart and Practice
DNA → Progress › Growth; tier retake, nudges, leaderboard opt-in and export → Settings; metronome and ambient rooms →
Practice; sky achievements and meteor showers → the constellation drawer and Observatory › Achievements).

**Disclosure decision (you left it to me):** `reveal()` is now **the app's standard** for hiding secondary detail.
The "?" button stays only for inline help attached to a control. Tabs are for peer views. Every other hiding
mechanism is out. This is written up in `DESIGN_NOTES.md` under Phase 16.

Commits, one per page:

| Commit | Change |
|---|---|
| `f7bc9da` | Shell: one header bar, Today / Repertoire / Constellation / Practice / **Progress** / Observatory, account menu with **Settings** + Sign out; `/progression` and `/performances` still work |
| `690a8c4` | Today: *Next up* card (least recently practised active piece), This week, In progress, Needs attention, stats last |
| `2dac676` | Repertoire grouped by status; wishlist/retired collapsed (top ten named); tempo and last-practised on active rows |
| `0f97b59` | Piece detail: one "Before this counts as learnt" checklist replaces two banners |
| `51f00df` | Constellation: the selection opens in a drawer over the sky (a panel below it on phones) |
| `51d8dc2` | Onboarding: nav hidden during setup, 760px wizard, finished steps editable and pre-filled |
| (this commit) | Observatory: Sky shop / Achievements tabs plus a live try-before-you-buy sky preview |

**Judgement calls:**
- **Dashboard is renamed "Today".** Constellation keeps its name, since it's the product's identity.
- **"Active" = learning + polishing everywhere,** matching the backend stat.
- **Gold hides in the header below 420px** to make room for the account button. It's still on the Observatory.
- **Palette unchanged:** yellow, orange, pink and starlight on the existing background scale. Navigation's active
  state and the Observatory's equipped state both use starlight, per the "selected = starlight" rule.

**Verification**: build ✔ and pytest 85 passed, 1 skipped ✔ after every page commit. Each page was screenshotted
at 1280px, several at 390px, against the scratch backend, with interaction scripts: account menu and
focus, requirement-checklist button, star-click drawer, stepper editing plus tier pre-fill, cosmetic hover preview.
No console errors.
