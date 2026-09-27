from types import SimpleNamespace

import pytest

from app.services.family_tree import ADJACENT_ERA, affinity, assign_parents, context, placed_year, shared_techniques
from app.services.practice_dna import demand_profile, match_label, pearson, readiness, similarity, summary_line
from app.services.progression import SAME_ERA


def era(id, name):
    return SimpleNamespace(id=id, name=name, start_year=1600 + id * 100)


def piece(year=None, birth=None, era_obj=None, genre_id=None, genre="Etude"):
    composer = SimpleNamespace(birth_year=birth, era=era_obj, era_id=era_obj.id if era_obj else None)
    return SimpleNamespace(year_composed=year, composer=composer, genre_id=genre_id, genre=SimpleNamespace(name=genre))


def test_demand_profile_is_a_share_of_total_weight():
    profile = demand_profile([{1: 1.0, 2: 0.5}, {1: 0.5}, {}])
    assert profile == pytest.approx({1: 0.75, 2: 0.25})
    assert demand_profile([{}]) == {}


def test_pearson_handles_flat_and_short_inputs():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([5, 5, 5], [1, 2, 3]) is None
    assert pearson([1, 2], [1, 2]) is None


def test_similarity_reads_shape_not_level():
    demand = {1: 0.6, 2: 0.4}
    strong_where_needed = {1: 9.0, 2: 7.2, 3: 1.5, 4: 1.5}
    weak_where_needed = {1: 1.5, 2: 1.5, 3: 9.0, 4: 9.0}
    assert similarity(strong_where_needed, demand) > 0.5
    assert similarity(weak_where_needed, demand) < -0.5
    assert similarity({1: 9.0, 2: 9.0, 3: 9.0, 4: 9.0}, demand) is None


def test_readiness_weights_tiers_by_demand_and_reports_coverage():
    value, covered = readiness({1: 9.0, 2: 3.0}, {1: 0.5, 2: 0.25, 3: 0.25})
    assert value == pytest.approx(7.0)
    assert covered == pytest.approx(0.75)
    assert readiness({}, {1: 1.0}) == (None, 0.0)


def test_labels_and_summary():
    assert match_label(None) == "Not enough to compare"
    assert match_label(0.6) == "Strong match"
    assert match_label(-0.4) == "Leans on your weaker techniques"
    proficiency = {1: 9.0, 2: 7.2, 3: 1.5, 4: 1.5}
    rows = [{"name": "Frederic Chopin", "similarity": 0.8, "demand": [{"technique_id": 1}, {"technique_id": 3}, {"technique_id": 2}]}]
    line = summary_line(rows, proficiency, {1: "Rapid scales", 2: "Trills", 3: "Wide leaps"})
    assert line.startswith("Closest to Chopin's technical demands")
    assert "rapid scales and trills" in line
    assert "Rate at least" in summary_line(rows, {1: 9.0}, {})


def test_placed_year_falls_back_to_composer_then_era():
    romantic = era(2, "Romantic")
    assert placed_year(piece(year=1836)) == 1836
    assert placed_year(piece(birth=1810)) == 1840
    assert placed_year(piece(era_obj=romantic)) == romantic.start_year + 50
    assert placed_year(piece()) is None


def test_context_extends_the_constellation_era_genre_link():
    classical, romantic, modern = era(1, "Classical"), era(2, "Romantic"), era(4, "Modern")
    rank = {1: 1, 2: 2, 4: 4}
    same, reasons = context(piece(era_obj=romantic, genre_id=7), piece(era_obj=romantic, genre_id=7), rank)
    assert same == pytest.approx(min(1.0, SAME_ERA + 0.3)) and reasons == ["Romantic", "Etude"]
    adjacent, reasons = context(piece(era_obj=classical), piece(era_obj=romantic), rank)
    assert adjacent == pytest.approx(ADJACENT_ERA) and reasons == ["Classical to Romantic"]
    assert context(piece(era_obj=classical), piece(era_obj=modern), rank) == (0.0, [])


def test_parents_are_earlier_best_matches_above_the_floor():
    scores = {(1, 2): 0.5, (1, 3): 0.4, (2, 3): 0.9, (1, 4): 0.1, (2, 4): 0.2, (3, 4): 0.25}
    parents = assign_parents([1, 2, 3, 4], lambda a, b: scores.get((a, b), 0.0))
    assert parents[1] is None
    assert parents[2] == (1, 0.5)
    assert parents[3] == (2, 0.9)
    assert parents[4] is None


def test_affinity_and_shared_techniques():
    assert affinity(1.0, 1.0) == pytest.approx(1.0)
    assert affinity(0.5, 0.0) == pytest.approx(0.3)
    names = {1: "Trills", 2: "Wide leaps", 3: "Double thirds"}
    assert shared_techniques({1: 0.9, 2: 0.5, 3: 0.1}, {1: 0.4, 2: 0.8, 3: 0.9}, names) == ["Wide leaps", "Trills"]
