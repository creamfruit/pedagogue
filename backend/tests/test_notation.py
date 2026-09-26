from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.seed import TECHNIQUES
from app.seed_lore import PASSAGES
from app.services.catalog import pick_technique_examples
from app.services.notation import KEY_PITCH_CLASS, MAJOR_SCALE_STEPS, SightReadingForge, forge_key

SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
BEATS = {"s": 0.25, "e": 0.5, "q": 1.0, "h": 2.0, "w": 4.0}
CATALOG_GAPS = {"Broken octaves"}


def midi(pitch: str) -> int:
    letter, rest = pitch[0], pitch[1:]
    shift = 0
    if rest[0] in "#b":
        shift = 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return (int(rest) + 1) * 12 + SEMITONE[letter] + shift


def pitches(measure: dict, voice: str = "notes") -> list[list[str]]:
    return [note.get("pitches") or [note["pitch"]] for note in measure.get(voice, [])]


def bar_length(notes: list[dict]) -> float:
    return sum(BEATS[n["duration"]] * (2 / 3 if n.get("tuplet") == 3 else 1) for n in notes)


@pytest.mark.parametrize("technique, semitones", [("Double sixths", {8, 9}), ("Double thirds", {3, 4})])
def test_double_notes_follow_the_named_interval(technique, semitones):
    for seed in range(12):
        notation = SightReadingForge(seed).generate("double_notes", 8.0, technique)
        for measure in notation["measures"]:
            for low, high in pitches(measure):
                assert midi(high) - midi(low) in semitones


@pytest.mark.parametrize("category", ["dexterity", "double_notes", "octaves", "leaps", "trills", "polyrhythm"])
def test_notes_stay_inside_the_labelled_key(category):
    for seed in range(12):
        notation = SightReadingForge(seed).generate(category, 7.0)
        scale = {(KEY_PITCH_CLASS[notation["key"]] + step) % 12 for step in MAJOR_SCALE_STEPS}
        for measure in notation["measures"]:
            for voice in ("notes", "left"):
                for chord in pitches(measure, voice):
                    assert all(midi(p) % 12 in scale for p in chord), (notation["key"], chord)


def test_flat_keys_are_spelled_with_flats():
    notation = SightReadingForge(0).generate("dexterity", 7.0, "Rapid scales", "Eb")
    names = [p for m in notation["measures"] for chord in pitches(m) for p in chord]
    assert not any("#" in name for name in names)
    assert any("b" in name[1:2] for name in names)


def test_single_hand_patterns_declare_one_hand():
    assert SightReadingForge(1).generate("leaps", 9.0, "Wide leaps")["hand"] == "right"
    assert SightReadingForge(1).generate("pedaling", 6.0, "Half pedalling")["hand"] == "left"
    assert SightReadingForge(1).generate("polyrhythm", 7.0, "Three against two")["hand"] == "both"


@pytest.mark.parametrize("technique, right, left", [("Three against two", 3, 2), ("Four against three", 4, 3)])
def test_polyrhythm_bars_are_complete_in_both_hands(technique, right, left):
    notation = SightReadingForge(4).generate("polyrhythm", 7.0, technique)
    for measure in notation["measures"]:
        assert bar_length(measure["notes"]) == pytest.approx(4.0)
        assert bar_length(measure["left"]) == pytest.approx(4.0)
        assert len(measure["notes"]) == right * 4
        assert len(measure["left"]) == left * 4


def test_forge_key_uses_the_piece_key_or_its_relative_major():
    assert forge_key("G major") == "G"
    assert forge_key("A-flat major") == "Ab"
    assert forge_key("C-sharp minor") == "E"
    assert forge_key("B-flat minor") == "Db"
    assert forge_key("D-sharp minor") is None
    assert forge_key(None) is None
    assert SightReadingForge(9).generate("leaps", 8.0, "Wide leaps", "A")["key"] == "A"


def link(technique_id, passage_id, weight, difficulty):
    passage = SimpleNamespace(id=passage_id, difficulty_score=Decimal(str(difficulty)))
    return SimpleNamespace(technique_id=technique_id, passage_id=passage_id, weight=Decimal(str(weight)), passage=passage)


def test_pick_technique_examples_prefers_weight_then_difficulty():
    chosen = pick_technique_examples([link(1, 10, 0.8, 9.0), link(1, 11, 0.9, 5.0), link(1, 12, 0.9, 7.0), link(2, 13, 0.4, 3.0)])
    assert chosen[1].passage_id == 12
    assert chosen[2].passage_id == 13


def catalog_examples() -> dict[str, tuple[float, float, str]]:
    best: dict[str, tuple[float, float, str]] = {}
    for title, rows in PASSAGES.items():
        for _label, _start, _end, difficulty, _description, _cue, links in rows:
            for name, weight in links:
                if name not in best or (weight, difficulty) > best[name][:2]:
                    best[name] = (weight, difficulty, title)
    return best


def test_every_technique_has_a_catalog_passage_except_known_gaps():
    best = catalog_examples()
    missing = {name for name, _category, _factor in TECHNIQUES if name not in best}
    assert missing == CATALOG_GAPS


def test_requested_examples_come_from_the_named_pieces():
    best = catalog_examples()
    assert best["Double sixths"][2] == "Pas de deux, The Nutcracker"
    assert best["Wide leaps"][2] == "Mephisto Waltz No. 1"
