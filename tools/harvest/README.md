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
on its own.

| Stage | Command | Writes |
|---|---|---|
| Crawl and licence filter | `crawl` | `01-crawl.jsonl` |
| Fetch score files | `fetch` | `03-fetch.jsonl` |

OpenScore scores arrive as MuseScore `.mscx` files. They are converted to MusicXML with MuseScore 4
(`MUSESCORE_BIN`, default `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`).
