# Technique excerpt library

`frontend/public/excerpts/` holds one short, real passage (or two) for every technique in the
onboarding tier list: the engraved bars as MusicXML, and the notes as timed events for piano
playback. Nothing in it is generated or invented; every excerpt is cut from an existing encoding
of the printed score and, where a second independent source exists, checked against it.

## Rebuild

Clone the sources somewhere outside the repo, then run the builder with this repo's backend
virtualenv plus `mido` and `lxml`:

```bash
git clone --depth 1 https://github.com/pl-wnifc/humdrum-chopin-first-editions chopin-fe
git clone --depth 1 https://github.com/cheriell/ACPAS-dataset acpas

python tools/excerpts/build_excerpts.py --chopin ../chopin-fe --cpm ../acpas --out frontend/public/excerpts
```

From ACPAS only Bernd Krueger's Classical Piano MIDI files are read, under `subset_S/`. They are his
originals, renamed. Each spec records the original `midis/...` path, so a copy downloaded straight
from piano-midi.de can stand in. Nothing that ACPAS took from the ASAP dataset is used.

Each line of output shows the excerpt and how well its notes match every second source listed
in `specs.py` (1.0 is identical). `backend/tests/test_excerpt_library.py` fails if any technique
loses its excerpt or a cross-check drops below 0.9.

## Adding or changing an excerpt

Edit `specs.py`: source file, bar range, hand, tempo and a one-sentence description of what the
bars actually contain. Add every independent source you can under `verify`. If the only second
source disagrees for a known reason (ornament realisation, for example), check it by hand and say
so in `manual_check` instead of lowering the bar.

## Sources and licences

| Source | Used for | Licence |
|---|---|---|
| First Editions of Fryderyk Chopin's Music, Fryderyk Chopin Institute | Chopin excerpts, and cross-checks between editions | CC BY 4.0 |
| Classical Piano MIDI, Bernd Krueger | Beethoven, Liszt and Ravel excerpts, and cross-checks | CC BY-SA (Germany) |
| Salamander Grand Piano V3, Alexander Holm | piano samples in `frontend/public/samples/piano` | CC BY 3.0 |

Every source must allow commercial use. The ASAP dataset (CC BY-NC-SA 4.0) was removed before
launch. Its excerpts were replaced with the same passages from Krueger's sequences, or with
different passages from the Chopin first editions. `LICENSES.md` at the repo root lists every
source and what its licence requires.

Excerpts made from Krueger's MIDI are adaptations under CC BY-SA, so they stay under that licence.
His sequences sometimes notate a passage at half value (a 2/2 Allegro written as 4/8 at double
tempo). `scale` and `meter` in a spec restore the printed note values, and `bar_offset` shifts to
his bar numbering when it differs from the printed score.
