import pytest

from tests.harvest_helpers import BARS, SECONDS, write_study
from tools.harvest import features, scoredata
from tools.harvest.scoredata import lilypond_pickup, lilypond_tempo_words, synthetic_bars


@pytest.fixture(scope="module", params=["mid", "mxl"])
def measured(request, tmp_path_factory):
    folder = tmp_path_factory.mktemp(f"study-{request.param}")
    path = write_study(folder, "mid" if request.param == "mid" else "mxl")
    data = scoredata.load_score(path, request.param)
    return features.extract(data), data


def test_the_bars_and_total_length_are_measured(measured):
    found, _ = measured
    assert found["bars"] == BARS
    assert found["length"]["seconds"] == pytest.approx(SECONDS, abs=0.2)
    assert found["length"]["minutes"] == pytest.approx(SECONDS / 60, abs=0.01)


def test_note_density_is_counted_for_every_bar(measured):
    found, _ = measured
    per_bar = found["per_bar"]
    assert len(per_bar["notes"]) == BARS == len(per_bar["numbers"])
    assert per_bar["notes"][0] == 6
    assert per_bar["notes"][4] == 34
    assert found["notes"]["max_per_bar"] == 34
    assert per_bar["nps"][4] == pytest.approx(34 / 2.0, abs=0.1)
    assert found["notes"]["nps_peak"] == pytest.approx(17.0, abs=0.2)


def test_the_widest_hand_span_is_a_sixteen_semitone_chord(measured):
    found, _ = measured
    assert found["span"]["max"] == 16
    assert found["span"]["left_max"] == 16
    assert found["span"]["ge_tenth"] == 2
    assert found["span"]["ge_octave"] == 34
    assert found["per_bar"]["span"][7] == 16


def test_the_largest_leap_is_two_octaves(measured):
    found, _ = measured
    assert found["leaps"]["max"] == 24
    assert found["leaps"]["ge_two_octaves"] >= 3
    assert found["per_bar"]["leap"][6] == 24


def test_repeated_octaves_are_found_in_bars_five_and_six(measured):
    found, _ = measured
    assert found["octaves"]["events"] == 32
    assert found["octaves"]["longest_run"] == 32
    assert found["octaves"]["repeated"] >= 32
    assert found["per_bar"]["octave"][4] == 16 and found["per_bar"]["octave"][5] == 16


def test_triplets_are_counted_as_tuplets(measured):
    found, _ = measured
    assert found["tuplets"]["notes"] == 12
    assert found["tuplets"]["kinds"] == {"3:2": 12}
    assert found["tuplets"]["complex_notes"] == 0
    assert found["per_bar"]["tuplet"][8] == 12


def test_a_fast_stepwise_run_is_found(measured):
    found, _ = measured
    assert found["runs"]["count"] == 1
    assert found["runs"]["longest"] == 16
    assert found["per_bar"]["run"][9] == 16


def test_key_and_metre_changes_are_recorded(measured):
    found, _ = measured
    assert found["metre"]["changes"] == 1
    assert [item["sig"] for item in found["metre"]["signatures"]] == ["4/4", "3/4"]
    assert found["metre"]["signatures"][1]["bar"] == 11
    assert found["key"]["changes"] == 1
    assert found["key"]["signatures"][1]["bar"] == 11


def test_the_tempo_marking_is_recorded(measured):
    found, _ = measured
    assert found["tempo"]["first_bpm"] == pytest.approx(120.0)
    assert found["tempo"]["marks"][0]["bpm"] == pytest.approx(120.0)
    assert found["tempo"]["changes"] == 0


def test_both_hands_are_told_apart(measured):
    found, _ = measured
    assert found["span"]["right_max"] == 12
    assert 0.1 < found["notes"]["left_share"] < 0.25
    assert found["notes"]["lowest"] == 36 and found["notes"]["highest"] == 88


def test_the_vector_is_sixty_four_numbers_between_zero_and_one(measured):
    found, _ = measured
    vector = features.to_vector(found)
    assert len(vector) == features.VECTOR_DIM == 64
    assert all(0.0 <= value <= 1.0 for value in vector)
    assert len(features.VECTOR_NAMES) <= 64
    assert vector[len(features.VECTOR_NAMES) :] == [0.0] * (64 - len(features.VECTOR_NAMES))
    assert vector[features.VECTOR_NAMES.index("tuplet_fraction")] > 0
    assert vector[features.VECTOR_NAMES.index("octave_fraction")] > 0


def test_the_features_are_plain_json(measured):
    import json

    found, _ = measured
    assert json.loads(json.dumps(found)) == found


def test_midi_and_musicxml_agree_on_the_main_figures(tmp_path):
    results = {}
    for kind in ("mid", "mxl"):
        folder = tmp_path / kind
        folder.mkdir()
        results[kind] = features.extract(scoredata.load_score(write_study(folder, kind), kind))
    for group, field in (("span", "max"), ("leaps", "max"), ("octaves", "events"), ("tuplets", "notes"), ("runs", "longest")):
        assert results["mid"][group][field] == results["mxl"][group][field], (group, field)
    assert results["mid"]["notes"]["total"] == results["mxl"]["notes"]["total"]


def test_the_vector_separates_different_pieces(tmp_path):
    calm = {"mean_per_bar": 3.0, "p90": 4.0}
    folder = tmp_path / "a"
    folder.mkdir()
    busy = features.extract(scoredata.load_score(write_study(folder, "mid"), "mid"))
    sparse = dict(busy)
    sparse["notes"] = {**busy["notes"], "mean_per_bar": 2.0, "p90_per_bar": 3.0, "max_per_bar": 4, "nps_mean": 1.0, "nps_p90": 1.5, "nps_peak": 2.0}
    sparse["octaves"] = {**busy["octaves"], "events": 0, "repeated": 0, "longest_run": 0, "fraction": 0.0}
    assert features.to_vector(busy) != features.to_vector(sparse)
    assert calm


@pytest.mark.parametrize(
    "source, expected",
    [
        ("\\partial 4", 1.0),
        ("\\partial 8", 0.5),
        ("\\partial8", 0.5),
        ("\\partial 4.", 1.5),
        ("\\partial 8*3", 1.5),
        ("\\partial 2.", 3.0),
        ("no pickup here", 0.0),
    ],
)
def test_a_pickup_is_read_from_the_lilypond_source(source, expected):
    assert lilypond_pickup(source) == expected


def test_bars_after_a_pickup_start_at_one():
    bars = synthetic_bars([(0.0, "3/4", 3.0)], 12.0, 1.0)
    assert bars[0] == (0, 0.0, 1.0)
    assert bars[1] == (1, 1.0, 3.0)
    assert bars[2] == (2, 4.0, 3.0)


def test_a_metre_change_changes_the_bar_length():
    bars = synthetic_bars([(0.0, "4/4", 4.0), (8.0, "3/4", 3.0)], 14.0, 0.0)
    assert [(number, start) for number, start, _ in bars[:5]] == [(1, 0.0), (2, 4.0), (3, 8.0), (4, 11.0), (5, 14.0)]


def test_tempo_words_come_from_the_lilypond_header_and_marks():
    text = '\\header { piece = "Allegro vivace" title = "Study" }\n\\tempo "Andante" 4 = 76'
    words = lilypond_tempo_words(text)
    assert "Andante" in words and "Allegro vivace" in words


def test_too_short_a_piece_is_refused(tmp_path):
    from music21 import note, stream

    short = stream.Score()
    part = stream.Part()
    part.partName = "Piano"
    measure = stream.Measure(number=1)
    measure.append(note.Note(60, quarterLength=4))
    part.append(measure)
    short.insert(0, part)
    path = tmp_path / "short.mid"
    short.write("midi", fp=str(path))
    with pytest.raises(ValueError):
        features.extract(scoredata.load_score(path, "mid"))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Opus 9. No. 1", "Op. 9 No. 1"),
        ("Op.23", "Op. 23"),
        ("Opus 100.", "Op. 100"),
        ("O 52", "Op. 52"),
        ("71", "Op. 71"),
        ("op. 31,1", "Op. 31 No. 1"),
        ("BWV 772", "BWV 772"),
        ("WoO 59", "WoO 59"),
        ("K. 545", "K. 545"),
        ("", None),
        ("Untitled", None),
    ],
)
def test_catalogue_numbers_are_written_the_way_the_catalogue_writes_them(raw, expected):
    from tools.harvest.naming import catalogue_number

    assert catalogue_number(raw) == expected


def test_keys_are_written_the_way_the_catalogue_writes_them():
    from tools.harvest.naming import pretty_key

    assert pretty_key("Eb major") == "E-flat major"
    assert pretty_key("F# minor") == "F-sharp minor"
    assert pretty_key("G major") == "G major"
    assert pretty_key("nonsense") is None


def test_lieder_are_titled_as_piano_parts_and_long_titles_are_cut():
    from tools.harvest.naming import piece_title

    assert piece_title("Gute Nacht", "openscore-lieder") == "Gute Nacht (piano part)"
    assert piece_title("Fur Elise", "mutopia") == "Fur Elise"
    assert len(piece_title("x" * 400, "openscore-lieder")) == 200
    assert piece_title("x" * 400, "openscore-lieder").endswith("(piano part)")


def test_an_era_is_chosen_by_the_years_a_composer_was_active():
    from types import SimpleNamespace

    from tools.harvest.naming import era_for

    eras = [
        SimpleNamespace(name="Baroque", start_year=1600, end_year=1750),
        SimpleNamespace(name="Classical", start_year=1730, end_year=1820),
        SimpleNamespace(name="Romantic", start_year=1800, end_year=1910),
        SimpleNamespace(name="Impressionist", start_year=1875, end_year=1925),
        SimpleNamespace(name="Contemporary", start_year=1975, end_year=None),
    ]
    assert era_for(eras, 1685).name == "Baroque"
    assert era_for(eras, 1770).name == "Classical"
    assert era_for(eras, 1810).name == "Romantic"
    assert era_for(eras, 1862).name == "Impressionist"
    assert era_for(eras, 1300) is None
    assert era_for(eras, None) is None
