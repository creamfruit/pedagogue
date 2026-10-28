# Data sources and licences

Every piece of third-party data Pedagogue ships or fetches, its licence, and what that licence asks
of us. The in-app Credits page (Settings → Credits) carries the attributions listed here.

Software dependencies are licensed separately; see `backend/requirements.txt` and
`frontend/package.json`.

## Shipped with the app

| Data | Where it lives | Source | Licence | Commercial use |
|---|---|---|---|---|
| Analysed score library: bar counts, techniques, hard passages and difficulty for 185 Chopin works | `backend/app/data/score_library.json`, seeded into the catalogue | [First Editions of Fryderyk Chopin's Music](https://github.com/pl-wnifc/humdrum-chopin-first-editions), Fryderyk Chopin Institute | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Yes |
| Technique excerpts from Chopin | `frontend/public/excerpts/chopin-*` | First Editions of Fryderyk Chopin's Music | CC BY 4.0 | Yes |
| Technique excerpts from Beethoven, Liszt and Ravel | `frontend/public/excerpts/beethoven-*`, `liszt-*`, `ravel-*` | [Classical Piano MIDI](http://www.piano-midi.de), Bernd Krueger | CC BY-SA, German port (see note) | Yes |
| Piano samples | `frontend/public/samples/piano` | [Salamander Grand Piano V3](https://archive.org/details/SalamanderGrandPianoV3), Alexander Holm | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | Yes |
| Reference difficulty ladder, piece and composer notes in the seed | `backend/app/services/repertoire_reference.py`, `backend/app/seed_lore.py` | Written for Pedagogue | Ours | Yes |

### What each licence requires

**First Editions of Fryderyk Chopin's Music (CC BY 4.0).** Credit the source with the first five
lines of the dataset's `LICENSE.txt`:

> First Editions of Fryderyk Chopin's Music
> Copyright 2017-2021 The Fryderyk Chopin Institute (https://nifc.pl)
> Website: https://chopinscores.org
> Digital scores: https://github.com/pl-wnifc/humdrum-chopin-first-editions
> License: https://creativecommons.org/licenses/by/4.0

CC BY 4.0 also asks us to link the licence and say that we changed the material. The library holds
measurements taken from the scores, not the scores themselves, and the excerpts are short extracts
re-engraved as MusicXML. Both are adaptations, and the Credits page says so.

**Classical Piano MIDI (CC BY-SA).** Credit "Bernd Krueger" as the copyright holder and give
`piano-midi.de` as the source. Share-alike: the excerpts made from these files (their MusicXML and
note events) are adaptations, so they must stay under the same licence, and anyone may reuse them on
those terms. The site names the licence as "cc-by-sa Germany" without a version. Copies elsewhere
list both 2.0 DE and 3.0 DE, so confirm the version with the author before a formal release. The
files used here are Krueger's originals, with his copyright text intact. They were taken from the
copies in the [ACPAS dataset](https://github.com/cheriell/ACPAS-dataset), and nothing ACPAS added
(alignments, annotations, audio) is used. Each excerpt records its original `midis/...` path.

**Salamander Grand Piano V3 (CC BY 3.0).** Credit Alexander Holm, link the licence, and say that
the samples were changed. We ship a subset of notes converted to MP3.

## Fetched while the app runs

| Data | Used for | Source | Licence | What it requires |
|---|---|---|---|---|
| Short piece histories | "History" on piece pages | [Wikipedia](https://en.wikipedia.org) page summaries | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Link the article, credit Wikipedia's contributors, link the licence, say the text may be shortened, and keep any adapted text under CC BY-SA. Each history links its article and the licence. |
| Work and composer identifiers, composition years | Import matching and facts | [Wikidata](https://www.wikidata.org) | CC0 | Nothing. Credited as a courtesy. |
| Work titles, catalogue numbers, composers | Catalogue search and imports | [MusicBrainz](https://musicbrainz.org) core data | CC0 | Nothing for core data. Credited as a courtesy. |
| Artist tags and genres | Read during a search to decide whether an artist is a classical composer, never stored or shown | MusicBrainz supplementary data | CC BY-NC-SA 3.0 | **Non-commercial.** See "Open questions" below. |
| Composers and works | Catalogue search and imports | [Open Opus](https://openopus.org) | Public domain (CC0) | Nothing. Credited as a courtesy. |

Links to IMSLP and MuseScore on piece pages are search links only. Nothing is copied from either.

## Harvested open scores

`tools/harvest` downloads open scores and measures them. Nothing is copied into the repository: the
results go to the database (`piece_sources`, `piece_reference_notes`, passages and their images in
storage), and the work folder it downloads into stays on the machine that ran it.

| Source | What is taken | Licence | What it requires |
|---|---|---|---|
| [Mutopia Project](https://www.mutopiaproject.org), works listed "for Piano" | Notes (from the MIDI), the LilyPond source for cropped images, title, opus, composer, typesetter | Public Domain, or Creative Commons Attribution (CC BY, any version) | For CC BY, credit the typesetter and link the licence. Every harvested piece page does, and the Credits page names the project. Share-alike (CC BY-SA), non-commercial and no-derivatives works are skipped. |
| [OpenScore Lieder Corpus](https://musescore.com/openscore-lieder-corpus), the piano part of each song | Notes (MuseScore converted to MusicXML), title, composer, Wikidata id | CC0 1.0 | Nothing. The corpus asks for credit and a link, which the pieces and the Credits page give. |
| [OpenScore String Quartets](https://musescore.com/openscore-string-quartets) | Nothing: a string quartet has no piano part | CC0 1.0 | None |
| [Wikidata](https://www.wikidata.org) | Composers' birth and death dates | CC0 | Nothing. Credited as a courtesy. |

The rules the tool applies before it keeps a work:

- The licence must be clearly public domain, CC0 or CC BY with a version. Mutopia states it twice, in
  its catalogue and in the LilyPond header, and the two must agree. Anything unclear is skipped.
- The composer must be found on Wikidata with a death date more than seventy years ago, judged to the
  day. Anonymous, "Traditional", unmatched, ambiguous and more recent composers are rejected.
- Each piece records its source URL, licence (name and link), composer and the credit line.

Every skipped work is listed with its reason in the tool's `state/*.rejected.jsonl` files. A full import
hides any work that has since stopped passing these rules, and an admin can hide any piece at once
(`POST /api/v1/admin/pieces/{id}/hide`). Each harvested piece page, public and in the app, shows the
source, the licence and a report-a-problem link (`REPORT_PROBLEM_URL`). The cropped score images are
adaptations of the score, so they carry the score's licence.

Software used while harvesting but not shipped: MuseScore 4 (GPL-3.0) to convert OpenScore files,
LilyPond (GPL-3.0) to engrave Mutopia sources, and Verovio (LGPL-3.0) for MusicXML. The files they
produce are the scores' own licence, not the tools'.

## What the public pages show

The public piece, composer and landing pages (see `DEPLOY.md`, "Public pages and search") use only what is listed above:

- difficulty, load figures, techniques and our own notes, which are ours;
- the hardest sections of harvested pieces, with a cropped image of the bars, the piece's source, licence and credit, and a report-a-problem link;
- the hardest sections of catalogue pieces, which for Chopin are measurements from the First Editions of Fryderyk Chopin's Music (CC BY 4.0). Pages for pieces measured from it carry the credit lines, the licence link and a statement that we changed the material;
- short histories taken from Wikipedia (CC BY-SA 4.0), each with a link to its article, the contributors' credit, the licence link and a note that the text is shortened. Nothing else on those pages is taken from Wikipedia.

They never show the Classical Piano MIDI excerpts or the Salamander samples, pieces added by users, passages a user assessed or that were found in a user's own score, or anything a user uploaded.

## Removed before launch

| Source | Licence | What it was used for |
|---|---|---|
| [ASAP dataset](https://github.com/fosfrancesco/asap-dataset) | CC BY-NC-SA 4.0 | 216 analysed library entries and 12 technique excerpts. Nothing derived from it remains in the library, the seed or the excerpts, and `backend/tests/test_harvest_fallback.py` fails if it comes back. |
| Craig Sapp's Mozart, Haydn and Scarlatti sonatas and Joplin rags | CC BY-NC-SA 4.0 | Library entries |
| Craig Sapp's Beethoven sonatas and Hummel preludes | No licence given (all rights reserved) | Library entries |
| Humdrum Bach Well-Tempered Clavier and Inventions | "Rights to all derivative electronic formats reserved" (David Huron, 1994) | Library entries |

When `python -m app.seed` runs, it withdraws what an earlier seed added from these sources.
- **Unused pieces:** library pieces nobody has in their repertoire are deleted.
- **Pieces in use:** their analysed passages are removed, unless a user has assessed a passage or
  uploaded a score for the piece. Their difficulty and techniques are then re-derived from the
  reference ladder, or estimated.

Pieces outside the library show the reference ladder's difficulty (or an estimate) and invite an
upload: the PDF reader marks hard bars from the user's own score.

## Rebuilding the shipped data

- Harvested scores: `tools/harvest/README.md`
- Score library: `tools/score_library/README.md`
- Technique excerpts: `tools/excerpts/README.md`

The builders accept only the sources above. Before adding a new one, check its licence allows
commercial use, then add it here and to the Credits page.

## Open questions

- **MusicBrainz tags.** The composer filter in `backend/app/services/musicbrainz_catalog.py`
  (`is_classical_composer`) reads artist tags and genre associations. These are supplementary data
  under CC BY-NC-SA 3.0. They are used only at search time and never stored or shown, but to be
  safe, filter on core data only (the disambiguation comment, or the composers already known from
  Open Opus) or ask the MetaBrainz Foundation about a commercial licence.
- **Classical Piano MIDI licence version.** Confirm 2.0 DE or 3.0 DE with Bernd Krueger.
