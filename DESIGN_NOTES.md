# Design notes — Phase 10 declutter

Written while doing the work, so each decision can be reviewed rather than discovered. Scope:
dashboard, repertoire, piece detail, constellation, onboarding, observatory. **No functionality or
data was removed.** Anything that left the default view moved behind a click-to-reveal, and every
reveal says what it holds. The four-accent rule is untouched: `--yellow`, `--orange`, `--pink` and
`--starlight` on the existing `--bg*` / `--line*` / `--text*` neutrals.

## The audit: what was cluttering things

I screenshotted every view at 1280px against the seeded scratch backend before changing anything.

| View | Height before | What made it heavy |
|---|---|---|
| Piece detail | ~3,800px | Every datum at once: two stacked warning banners, a status tile *and* a separate "Change status" panel for the same field, difficulty shown twice, all of the lore, every technique's mechanic *and* usual fault, the composer bio, the physical-load table, and three always-open submission forms. Nine bordered panels, several nested three deep. |
| Observatory | ~2,300px | Four cosmetic grids plus 14 achievement cards all expanded, and each card repeating "EQUIPPED"/"FREE" pills. |
| Repertoire | fine height | Six filter controls in one row (four rarely used), and up to three boxed pills per row competing with the title. |
| Tier quiz | nested scroll | A 2-line mechanic paragraph on every one of 17 rows, inside a 520px inner scroll box with the Continue button trapped at its bottom. |
| Constellation | fine | The same instructions in two places (the header hint and the empty info panel). |
| Dashboard | fine | Already sparse. Only light touches. |

## System-level decisions

### 1. Hierarchy: a real section title
Every section heading in the app was an `h3`: 11px, uppercase, 0.14em tracking, faint. So section
titles and field labels (`.stat-label`, `label`) looked the same, and nothing told the eye where a
section starts. I added **`.section-title`**: 16px, weight 500, sentence case, full text colour.
There's an optional **`.section-caption`** (12.5px, dim) directly under it for the "ordered by …"
kind of sentence. The small uppercase style stays for what it's good at: field labels and eyebrow
text inside a section. `h3` itself is unchanged, so views I didn't rework keep their look.

Type scale in use after this pass (px): 11 (mono meta) · 12.5 (captions, secondary text) · 13.5
(body in dense lists) · 15 (body) · 16 (section title) · 19 (h2) · 21–29 (h1, fluid). Nothing new is
smaller than 11px.

### 2. Progressive disclosure: one pattern everywhere
Everything collapsible uses `disclosure()` from `lib/dom.js`. It's the same helper behind the tier-list
"?" in Phase 11: a real `<button>` with `aria-expanded` / `aria-controls`, and a region that's
`hidden` until opened and filled lazily on first open. The text variant, **`.reveal-btn`**, is a quiet
link-style button with a chevron that rotates when open. Its label names what's inside
("More about this piece", "How it's played", "All 14 achievements"), so nothing is hidden behind a
bare "More".

What's visible by default: whatever answers "what is this and what do I do next". Behind a reveal:
reference material you read once (history, composer bio, the physical-load table), per-item detail in
long lists (technique mechanics and faults), and input forms you don't use every visit.

### 3. Spacing
A 4px-based scale (`--space-1` … `--space-6` = 4, 8, 12, 16, 24, 32). Major blocks on a page are 24px
apart, and things inside a block 12–16px. Inline `margin-top:16px` on each panel is replaced by a gap
on the parent layout, so spacing lives in one place.

### 4. Cards
Only content you act on, or that groups several fields, gets a bordered `.panel`. Read-only lists
inside a panel are flat rows separated by hairlines, not cards-in-cards. Where the old layout nested
panel › card › inner panel, it's now at most panel › row.

---

## Per-view changes

(Filled in below as each view is done.)

### Piece detail (`entryDetailView` + `pieceOverview`)

**Measured:** 3,792px → **2,636px** tall at 1280 with nothing expanded (−30%). With every reveal
open it's 3,354px, still shorter than before, because the duplicated fields are gone.

**Layout: summary first, then *your work* beside *the reference*.**
- **Header:** the title, plus a byline that now reads `Frederic Chopin · Op. 25 No. 6 · G-sharp minor`
  instead of only the composer. The primary action ("Practice this piece") and a ghost "Back" sit on the right.
- **One summary strip** replaces the Status / Tempo / Difficulty tiles *and* the separate "Change status"
  panel. Status is edited in place: the select shows the current status, and its **Save** stays
  disabled until you pick a different one. Before, "Status" appeared twice on screen: once as a big
  tile and once in its own panel.
- **Notices** (graded gate, verification, orbital decay) are grouped directly under the summary with
  tighter padding. None was merged away, because each carries different rules and the decay one has
  its own button.
- **Two columns from 1100px up:** the left, wider column holds the reference material about the
  piece; the right column (≥340px) holds the things you *do*: the guided plan, Practice recordings, and
  Notes & scores. Before, the forms sat between the plan and the overview in one long single column,
  so reaching the hardest sections meant scrolling past three upload forms. In the DOM the practice
  column comes first, so on phones it stacks right after the summary, above the reference material.
- **Difficulty is shown once.** The summary strip has the paired badge, and the "About" block
  drops its copy on this page. The standalone overview still shows it, via a new
  `pieceOverview(…, { difficulty })` option.
- The "needs verification" pill inside the overview is hidden on this page, because the Verification
  notice already says it. It still shows wherever the overview is used with its own heading.

**Progressive disclosure (all `reveal()`):**
| Visible by default | Behind a reveal |
|---|---|
| Catalogue, Era, Key, Marking, Duration; the Character strip; "What it depicts" | **More about this piece**: Composer, Composed, Genre, Syllabus grade, Mechanical load, History, Worth knowing |
| Top 3 hardest sections, each with description, approach and technique tags | **N more passages**, when a piece has more than 3 |
| Each technique's name, tier, category, share bar and load | **How it's played**: the mechanic and the usual fault, per row |
| Composer lifespan line and signature sound | **More about {composer}**: background and fun fact |
| Load index | **All load measurements**: stretch, density and notes/sec |
| Plan: the next 3 steps from the first unfinished one | **All N steps** |
| Recording history | **Add a recording**: the upload form. **It opens by default** when the piece still needs its verification or graded take and has no recording yet, so the one required action is never hidden |
| Notes & scores history | **Add notes or a score** |

**Cards:**
- The hardest sections were cards inside a panel. They're now flat rows split by hairlines, and the
  hardest keeps its orange left rule.
- Submission history items are flat rows too.
- Movements use the same flat rows.
- Every block is a `sectionBlock()` with a real `.section-title`.

**Verified:** at 1280 and 390px, with a graded/verification piece (Op. 25/6) and an easy one
(Für Elise), every reveal opens and shows its content (8/8 on the graded piece), and there are no console errors.

### Repertoire list (`repertoireView`)

- **Filters: two up front, four on demand.** Search and Status are the two filters used on nearly
  every visit, so they stay in the bar (search gets twice the width of status). Genre, Composer and
  the Min/Max difficulty range move behind **More filters**, with labels, because "Min diff." as a
  bare placeholder didn't say what scale it used; the label now reads "Difficulty (0–100)".
  - The reveal **opens by itself, and says "More filters (N active)"**, whenever one of those four is
    set in the URL, so an active filter is never hidden.
  - A quiet **Clear filters** link appears whenever any filter is active. Before, the only way to reset
    was clearing six controls one by one.
- **Rows carry less chrome.** The exceptional flags (top ten, unverified, frozen) stay as pills,
  because they're what you scan for. The status, which every row has, is plain dim text, and the difficulty is a plain
  number (with a tooltip naming the scale). That's down from up to five bordered boxes per row to
  at most three, and the title reads first.
- "9 piece(s)" → "9 pieces".
- **Phones:** the filters stack, and each row's meta drops under the title instead of squeezing it.
- All filter behaviour (URL query params, debounce, composer autocomplete) is unchanged.

### Onboarding (`onboardingView`, tier quiz)

- **The stepper is a progress indicator, not four identical pills.** Each step is *done* (a starlight ✓),
  *current* (an orange ring with the label in full text colour) or *upcoming* (faint), joined by
  hairlines. It carries `aria-current="step"`. Before, only the current pill differed, so finished
  steps didn't look finished.
- **Tier quiz rows are one line each.** The 2-line mechanic paragraph was on all 17 rows, and it's
  the reference text you read once, if at all. It now sits at the top of that row's **?** reveal, above
  the Phase 11 example, so "how it's played" and "what it sounds like" are in the same place.
  The button's accessible name says so: "How Trills is played, with an example". A caption under
  the intro points at the "?".
- **No nested scroll.** The quiz used to live in a `max-height: 520px; overflow: auto` box, so the page
  scrolled *and* the box scrolled, and Continue was stuck at the box's bottom. Rows now flow in the
  page, and **Continue sits in a sticky footer** (`.sticky-actions`) that stays at the bottom of the
  viewport while you rank, still showing "Rank every technique (n/17)".
- **Tier legend:** five boxed pills became one mono caption line
  (`S · mastered · A · strong · …`). It's reference, not an interactive control, so it shouldn't
  look like one.
- Profile, Top ten and Tastes had little to cut and only pick up the new stepper. Their controls were
  reworked in Phase 2.

### Observatory (`shopView`)

**Measured:** 2,305px → 1,946px at 1280.

- **The wallet is one summary strip** (the same `.summary-bar` as piece detail) instead of three separate panels.
  Level ring, gold and total XP read left to right as one fact: where you stand.
- **Each cosmetic group is a titled section** with a caption that answers the two questions you
  arrive with: *what's on now* and *how much of this is mine* ("Equipped: Soft bloom · 1 of 4 owned").
  Before, you had to scan every card for the one that said EQUIPPED.
- **The shop grids stay open.** Browsing them is the page's job, so hiding them would be disclosure for
  its own sake. The cards got tighter (14px padding, a 210px minimum column, so five per row at 1280
  instead of four), and the "free" tag went from a bordered pill to faint mono text, because it's a
  price note, not a control.
- **Equipped = selected = starlight.** Phase 7 made starlight the "selected" colour, but equipped cards were
  still an orange frame with an orange pill, the same treatment as the orange *Buy* buttons next to
  them. Equipped cards now get a starlight outline and a faint lift, with a starlight "equipped" pill
  (new `.pill-selected`), so the orange that's left means "you can act here".
- **Achievements:** a progress bar, the count, and the **next three to earn** stay visible, since
  those are the actionable part. All 14 are behind **All 14 achievements**. The earned ones are
  still there, just not taking up a 4×4 grid on every visit.
- **Fixed on the way (Phase 7 miss):** the heat-map cosmetic preview still drew its hottest dot with
  `var(--text)` after Phase 7 moved that end of the ramp to starlight. It now uses `var(--starlight)`, so it matches the
  constellation.

### Constellation (`constellationView`)

- **Instructions in one place.** The same gestures were in two places: a mono hint line in the header
  ("drag the sky to pan · scroll to zoom · tap a connector to read it") and the info panel under the
  chart ("Tap a star… tap a connector… drag a star…"). Neither listed all five. The info panel's
  resting text now names all five once, and the header hint is gone.
- **The header states the chart's size** instead ("9 stars · 35 connections"), which is new at-a-glance
  information in the same spot and weight the hint used to occupy.
- **A "How to read the chart" reveal** in the info panel explains the encoding Phase 1 built, which was
  never explained anywhere in the UI: line type = colour + dash, era = hue + spikes, size = difficulty,
  bright core = top ten or held, hollow dashed = needs verification, faded / dashed ring = drifting /
  frozen, dark core with a pale outline = custom. It's closed by default, since you need it once. It's
  the only place in this pass where I *added* information, and it's hidden until asked for.
- The canvas, legend toggles, era key and physics are untouched.
