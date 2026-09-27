# Technique excerpt library

`frontend/public/excerpts/` holds one short, real passage (or two) for every technique in the
onboarding tier list: the engraved bars as MusicXML, and the notes as timed events for piano
playback. Nothing in it is generated or invented; every excerpt is cut from an existing encoding
of the printed score and, where a second independent source exists, checked against it.

## Rebuild

Clone the three sources somewhere outside the repo, then run the builder with this repo's
backend virtualenv plus `music21`, `mido` and `lxml`:

```bash
git clone https://github.com/fosfrancesco/asap-dataset asap
git clone https://github.com/pl-wnifc/humdrum-chopin-first-editions chopin-fe
git clone https://github.com/cheriell/ACPAS-dataset acpas

python tools/excerpts/build_excerpts.py \
  --asap ../asap --chopin ../chopin-fe --cpm ../acpas \
  --out frontend/public/excerpts
```

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
| First Editions of Fryderyk Chopin's Music, Fryderyk Chopin Institute | Chopin excerpts | CC BY 4.0 |
| ASAP dataset (Foscarin et al.) | Beethoven, Liszt, Ravel, Brahms, Schumann, some Chopin | CC BY-NC-SA 4.0 |
| Classical Piano MIDI, Bernd Krueger, via ACPAS | Hungarian Rhapsody No. 2, cross-checks | CC BY-SA 3.0 DE |
| Salamander Grand Piano V3, Alexander Holm | piano samples in `frontend/public/samples/piano` | CC BY 3.0 |

The ASAP encodings are non-commercial. Before a paid release (Steam), replace the excerpts that
come from ASAP with encodings you are licensed to sell, for example your own engraving of the
same bars from a public-domain print.
