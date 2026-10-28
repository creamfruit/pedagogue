# Open score harvester

Downloads the Mutopia Project piano catalogue and the OpenScore corpora, keeps only works whose
licence is public domain, CC0 or CC BY, and records the source URL, licence and composer of every
piece. Run it from the repository root with the backend virtualenv:

```bash
backend/.venv/Scripts/python -m pip install -r tools/harvest/requirements.txt
backend/.venv/Scripts/python -m tools.harvest crawl
backend/.venv/Scripts/python -m tools.harvest fetch
```

Everything the tool downloads and writes goes to the work folder, `~/.cache/pedagogue-harvest` by
default (set `HARVEST_DIR` or pass `--work` to change it). Keep it outside OneDrive.

## What it accepts

| Source | Kept | Licence taken from |
|---|---|---|
| Mutopia Project | works listed "for Piano" only | the catalogue row, then checked against the licence in the LilyPond header |
| OpenScore Lieder | scores whose song has a piano part | the repository's `LICENSE.txt`, which must be CC0 1.0 |
| OpenScore String Quartets | nothing: a string quartet has no piano part | the repository's `LICENSE.txt` |

Licence text must be a clear public domain, CC0 or CC BY (with a version) statement. Share-alike,
non-commercial, no-derivatives, unversioned and unrecognised text is skipped, and so is anything
where the catalogue and the file disagree. Every skip is written to
`state/<stage>.rejected.jsonl` with the reason.

## Being polite

- One request at a time per host with a minimum gap (`config.MIN_INTERVAL_SECONDS`).
- A User-Agent that names the project and a contact (`HARVEST_CONTACT`, default the repository URL).
- `robots.txt` is read and obeyed on Mutopia.
- Retries with backoff, honouring `Retry-After`.
- Every response is cached on disk, so a second run makes no requests for what it already has.
  Expired pages are revalidated with `If-None-Match` and `If-Modified-Since`.
- Large downloads (the OpenScore archive) resume from a `.part` file.

## Stages

Each stage reads the previous stage's file in `state/` and writes its own, so any stage can be re-run
on its own. Commands run from the repository root.

| Stage | Command | Writes | What it does |
|---|---|---|---|
| 1 | `crawl` | `01-crawl.jsonl` | lists the catalogues and applies the licence rules |
| 2 | `composers` | `02-composers.jsonl` | keeps works whose composer died more than 70 years ago, per Wikidata |
| 3 | `fetch` | `03-fetch.jsonl` | downloads the LilyPond/MIDI or MuseScore files |
| 4 | `extract` | `04-extract.jsonl`, `features/` | measures each score with music21; builds the feature vector and the reference notes |
| 5 | `calibrate` | `difficulty_model.json`, `calibration-report.md` | fits the 0 to 100 difficulty to the reference ladder and prints the report |
| 6 | `render` | `05-render.jsonl`, `images/` | finds the hardest passages and renders each as a cropped SVG |
| 7 | `ingest` | the database | upserts pieces, provenance, features, vector, difficulty, passages, images and reference notes |

`ingest` needs `DATABASE_URL` (and the storage settings) like the API does, and migrations applied. It is
idempotent: a piece is keyed on its source and source id, so running it again changes nothing unless the
score, the licence or the calibration changed. A full run (no `--limit`) hides works that stopped passing
the rules; an admin's own hides are left alone.

OpenScore scores arrive as MuseScore `.mscx` files and are converted to MusicXML with MuseScore 4
(`MUSESCORE_BIN`, default `C:/Program Files/MuseScore 4/bin/MuseScore4.exe`).

Rendering needs LilyPond for Mutopia (`LILYPOND_BIN`, default `lilypond` on the PATH). A Mutopia source
that will not compile, or has no LilyPond installed, falls back to the notes read from its MIDI, drawn
with Verovio.

## Composer filter

Mutopia gives a composer's name and years, which are matched to a composer on Wikidata who was born
and died in those years and whose name shares the surname and initials. OpenScore gives a Wikidata
identifier, which is looked up directly. A composer is accepted only if Wikidata gives a death date
more than 70 years before today, judged to the day (the latest possible date when only a month or
year is known). Anonymous, "Traditional", unmatched, ambiguous and recently deceased composers are
rejected, and a Wikidata outage stops the run.

## What is measured

`extract` reads each score with music21 and records, per work: note density per bar, maximum hand
span, largest leaps, repeated octaves, tuplets, fast runs, key and metre changes, tempo markings and
total length, plus per-bar figures used to find the hardest passages. The raw figures go in the JSON
column `piece_sources.features`; a 64-number vector of them, each scaled to 0 to 1, goes in the
existing pgvector column `pieces.technique_vector`. `features.VECTOR_NAMES` lists what each
position means.

For Mutopia the notes come from the MIDI file and the pickup bar from the LilyPond source, so bar
numbers match the printed score. For OpenScore the piano part is picked out of the converted MusicXML.

## Difficulty

`difficulty.py` turns the measurements into ten terms (speed, density, reach, leaps, octaves, fast runs,
tuplets, length and changes) and fits a non-negative ridge model to the reference ladder over every
harvested piece that also appears on it. The ridge strength is chosen by leave-one-out error. Pieces
named in `difficulty.ANCHORS` (Für Elise 30, Ballade No. 1 70, La Campanella 90, Islamey 98) count for
more in the fit. `calibrate` prints, for every shared piece, the ladder value against the computed one,
the error figures, and whether each anchor is in the harvested corpus at all. Where the ladder has a
piece, the ladder value is what the piece shows; the computed value is kept beside it.

## Passages and reference notes

`passages.py` scores each bar from its speed, stretch, leaps, octaves, fast runs, tuplets and density,
grows the peaks into non-overlapping passages of two to eight bars, and names the techniques in them.
Each is stored with the source marker `harvest`. `reference_notes` (in the backend) holds each piece's notes in
the keyboard engine's form and marks the piece `scoring_ready` only when they pass validation,
including a perfect run through the timed and wait scorers.
