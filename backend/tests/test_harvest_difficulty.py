import copy
import json

import numpy as np
import pytest

from tests.harvest_helpers import write_study
from tools.harvest import calibration, difficulty, extract, features as feature_module, scoredata
from tools.harvest.licences import parse_licence
from tools.harvest.models import Candidate
from tools.harvest.workspace import Workspace


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    path = write_study(tmp_path_factory.mktemp("difficulty"), "mid")
    return feature_module.extract(scoredata.load_score(path, "mid"))


def at_level(template, level):
    found = copy.deepcopy(template)
    found["notes"].update(
        nps_p90=level / 6.0, nps_peak=level / 3.0, p90_per_bar=level / 2.0, polyphony_mean=1.0 + level / 40.0
    )
    found["span"].update(max=int(8 + level / 8), window_p95=6 + level / 5)
    found["leaps"].update(top5_mean=6 + level / 4, ge_octave=int(level / 10))
    found["octaves"].update(repeated=int(level / 2), fraction=level / 400)
    found["runs"].update(fraction=level / 300)
    found["tuplets"].update(fraction=0.0, complex_fraction=0.0)
    found["length"].update(minutes=1 + level / 25)
    return found


def rows_for(template, levels, anchors=()):
    return [(difficulty.terms(at_level(template, level)), level, difficulty.ANCHOR_WEIGHT if level in anchors else 1.0) for level in levels]


def test_the_fit_recovers_a_difficulty_that_grows_with_the_figures(template):
    levels = [10, 15, 22, 30, 38, 45, 52, 60, 68, 75, 82, 90]
    model = difficulty.fit(rows_for(template, levels))
    for level in levels:
        assert abs(model.score(at_level(template, level)) - level) < 5
    assert model.fitted_on == len(levels)


def test_every_weight_is_non_negative_so_more_difficulty_never_lowers_the_score(template):
    model = difficulty.fit(rows_for(template, [10, 20, 30, 40, 50, 60, 70, 80, 90]))
    assert all(weight >= 0 for weight in model.coefficients)


def test_a_harder_score_never_scores_lower(template):
    model = difficulty.fit(rows_for(template, [10, 20, 30, 40, 50, 60, 70, 80, 90]))
    scores = [model.score(at_level(template, level)) for level in range(5, 100, 5)]
    assert scores == sorted(scores)


def test_scores_stay_inside_the_scale(template):
    model = difficulty.fit(rows_for(template, [10, 20, 30, 40, 50, 60, 70, 80, 90]))
    assert 0 <= model.score(at_level(template, 0)) <= 100
    assert model.score(at_level(template, 1000)) == difficulty.CEILING
    assert model.score(at_level(template, -1000)) == difficulty.FLOOR


def test_anchor_pieces_pull_the_fit_toward_themselves(template):
    levels = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    noisy = [(terms, target + (12 if target == 30 else 0), weight) for terms, target, weight in rows_for(template, levels)]
    unanchored = difficulty.fit(noisy, ridge=1.0)
    anchored = difficulty.fit([(terms, target, 50.0 if target == 42 else 1.0) for terms, target, _ in noisy], ridge=1.0)
    probe = at_level(template, 30)
    assert abs(anchored.score(probe) - 42) < abs(unanchored.score(probe) - 42)


def test_too_few_pieces_are_refused(template):
    with pytest.raises(ValueError):
        difficulty.fit(rows_for(template, [10, 20, 30]))


def test_a_model_survives_being_saved_and_loaded(template, tmp_path):
    model = difficulty.fit(rows_for(template, [10, 20, 30, 40, 50, 60, 70, 80, 90]))
    model.save(tmp_path / "model.json")
    loaded = difficulty.Model.load(tmp_path / "model.json")
    probe = at_level(template, 55)
    assert loaded.score(probe) == model.score(probe)
    assert difficulty.Model.load(tmp_path / "missing.json") is None


def test_the_shipped_model_is_there_and_keeps_the_ladder_order():
    model = difficulty.Model.load()
    if model is None:
        pytest.skip("the model has not been fitted yet")
    assert model.version == difficulty.MODEL_VERSION
    assert model.names == list(difficulty.TERM_NAMES)
    assert all(weight >= 0 for weight in model.coefficients)
    assert model.fitted_on >= 8


def test_the_rank_correlation_is_one_for_matching_orders():
    assert difficulty.spearman([1, 2, 3, 4], [10, 20, 35, 80]) == pytest.approx(1.0)
    assert difficulty.spearman([1, 2, 3, 4], [80, 35, 20, 10]) == pytest.approx(-1.0)


def candidate_for(index, title, composer, catalogue):
    return Candidate(
        source="mutopia",
        source_id=str(index),
        title=title,
        composer=composer,
        source_url=f"https://www.mutopiaproject.org/cgibin/piece-info.cgi?id={index}",
        licence=parse_licence("Public Domain"),
        licence_text="Public Domain",
        catalog_number=catalogue,
        extra={"composer_label": composer},
    )


LADDER_PIECES = [
    ("Fur Elise", "Ludwig van Beethoven", "WoO 59"),
    ("Ballade No. 1", "Frederic Chopin", "Op. 23"),
    ("Etude Op. 10 No. 12", "Frederic Chopin", ""),
    ("Clair de lune", "Claude Debussy", ""),
    ("Arabesque No. 1", "Claude Debussy", ""),
    ("Liebestraum No. 3", "Franz Liszt", ""),
    ("Nocturne Op. 9 No. 2", "Frederic Chopin", ""),
    ("Hungarian Rhapsody No. 2", "Franz Liszt", ""),
    ("Prelude in C major, WTC I", "Johann Sebastian Bach", "BWV 846"),
    ("Sonata No. 14 Moonlight", "Ludwig van Beethoven", "Op. 27 No. 2"),
]


def build_workspace(tmp_path, template, pieces):
    ws = Workspace(tmp_path / "work")
    candidates = []
    for index, (title, composer, catalogue) in enumerate(pieces, start=1):
        entry = difficulty.ladder_entry(title, composer, catalogue)
        level = float(entry.score) if entry is not None else 40.0
        candidate = candidate_for(index, title, composer, catalogue)
        target = ws.root / "features" / "mutopia" / f"{index}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"features": at_level(template, level), "vector": [0.0] * 64, "content_hash": "x"}), encoding="utf-8")
        candidate.local["features"] = ws.rel(target)
        candidates.append(candidate)
    ws.write_stage(extract.STAGE_EXTRACT, candidates, [])
    return ws


def test_every_piece_that_is_on_the_ladder_is_compared(tmp_path, template):
    ws = build_workspace(tmp_path, template, LADDER_PIECES + [("Unknown Study", "Nobody Known", "")])
    rows = calibration.ladder_rows(ws, extract.STAGE_EXTRACT)
    assert len(rows) == len(LADDER_PIECES)
    labels = {row["label"] for row in rows}
    assert "Beethoven: Fur Elise" in labels


def test_two_movements_of_one_ladder_work_count_once_using_the_busiest(tmp_path, template):
    ws = build_workspace(tmp_path, template, LADDER_PIECES[:1] + [("Fur Elise", "Ludwig van Beethoven", "WoO 59")])
    second = ws.read_stage(extract.STAGE_EXTRACT)[1]
    payload = json.loads(ws.abs(second.local["features"]).read_text(encoding="utf-8"))
    payload["features"]["notes"]["nps_p90"] += 5
    ws.abs(second.local["features"]).write_text(json.dumps(payload), encoding="utf-8")
    rows = calibration.ladder_rows(ws, extract.STAGE_EXTRACT)
    assert len(rows) == 1
    assert rows[0]["busy"] == payload["features"]["notes"]["nps_p90"]


def test_calibrating_writes_a_model_and_a_report_that_compares_every_piece(tmp_path, template):
    ws = build_workspace(tmp_path, template, LADDER_PIECES)
    summary = calibration.calibrate(ws, extract.STAGE_EXTRACT, model_path=tmp_path / "model.json")
    assert summary["pieces_compared"] == len(LADDER_PIECES)
    assert summary["rmse"] < 8
    assert (tmp_path / "model.json").exists()
    text = summary["text"]
    for title in ("Fur Elise", "Ballade No. 1", "Liebestraum No. 3"):
        assert title in text
    assert "| Beethoven: Fur Elise | 30.0 |" in text
    assert "## Anchors" in text
    assert "La Campanella" in text and "Islamey" in text
    assert "| no |" in text


def test_the_report_says_when_an_anchor_is_in_the_corpus(tmp_path, template):
    pieces = LADDER_PIECES + [("La Campanella", "Franz Liszt", ""), ("Islamey", "Mily Balakirev", "")]
    ws = build_workspace(tmp_path, template, pieces)
    summary = calibration.calibrate(ws, extract.STAGE_EXTRACT, model_path=tmp_path / "model.json")
    text = summary["text"]
    line = next(row for row in text.splitlines() if row.startswith("| La Campanella"))
    assert "yes" in line and "| 90 |" in line
    assert "n/a" not in line


def test_the_terms_cover_every_figure_the_model_uses(template):
    values = difficulty.terms(template)
    assert set(values) == set(difficulty.TERM_NAMES)
    assert all(np.isfinite(value) for value in values.values())
