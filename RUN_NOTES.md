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
