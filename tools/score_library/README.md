# Analysed score library

`backend/app/data/score_library.json` holds, for each work, its bar count, duration, techniques,
hardest passages and a calibrated difficulty. They are measured from public-domain scores by
`backend/app/services/score_analysis.py`. The seed turns the entries into catalogue pieces, and
imported pieces that match an entry take its passages.

Only sources whose licence allows commercial use go into the library. Right now that is the
First Editions of Fryderyk Chopin's Music (CC BY 4.0). See `LICENSES.md` at the repo root for the
sources that were removed and why.

## Rebuild

Clone the source outside the repo, then run both steps with the backend virtualenv:

```bash
git clone --depth 1 https://github.com/pl-wnifc/humdrum-chopin-first-editions chopin-fe

python tools/score_library/build_library.py --chopin ../chopin-fe --out /tmp/score_library.json --workers 6
python tools/score_library/calibrate.py /tmp/score_library.json
cp /tmp/score_library.json backend/app/data/score_library.json
```

`calibrate.py` fits the difficulty model against the pieces on the reference ladder and prints the
fit (RMSE). Then run `pytest backend/tests/test_score_library.py`. It fails if a source without a
commercial licence slips in, or if the library loses its passages.

To add a source, give it an entry in `SOURCES` in `build_library.py` with its licence, attribution
text and `"commercial": True`, add a collector for it, and list it in `LICENSES.md` and on the
Credits page.
