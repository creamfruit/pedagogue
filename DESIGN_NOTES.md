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
