from __future__ import annotations

import random
from typing import Optional

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
MAJOR_SCALE_STEPS = [0, 2, 4, 5, 7, 9, 11]
KEYS = ["C", "G", "D", "A", "F", "Bb", "Eb"]
KEY_PITCH_CLASS = {"C": 0, "G": 7, "D": 2, "A": 9, "E": 4, "B": 11, "F": 5, "Bb": 10, "Eb": 3, "Ab": 8, "Db": 1}
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db"}
MAJOR_KEY_FOR_PITCH_CLASS = {pc: name for name, pc in KEY_PITCH_CLASS.items()}
LETTER_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LEFT_HAND_CATEGORIES = {"pedaling"}
TWO_HAND_CATEGORIES = {"polyrhythm"}
BEATS_PER_MEASURE = 4.0
MEASURE_COUNT = 8


def _midi_to_name(midi: int) -> str:
    octave = midi // 12 - 1
    name = NOTE_NAMES[midi % 12]
    return f"{name}{octave}"


def forge_key(key_signature: Optional[str]) -> Optional[str]:
    if not key_signature:
        return None
    words = key_signature.replace("-", " ").lower().split()
    if len(words) < 2 or words[0][0].upper() not in LETTER_PITCH_CLASS:
        return None
    pitch_class = LETTER_PITCH_CLASS[words[0][0].upper()]
    if "sharp" in words[1:-1]:
        pitch_class += 1
    if "flat" in words[1:-1]:
        pitch_class -= 1
    if words[-1] == "minor":
        pitch_class += 3
    elif words[-1] != "major":
        return None
    return MAJOR_KEY_FOR_PITCH_CLASS.get(pitch_class % 12)


def _to_flat(pitch: str) -> str:
    name, octave = pitch[:-1], pitch[-1]
    if pitch[-2] == "-":
        name, octave = pitch[:-2], pitch[-2:]
    return f"{SHARP_TO_FLAT.get(name, name)}{octave}"


def _respell_flats(measures: list[dict]) -> list[dict]:
    for measure in measures:
        for note in measure["notes"] + measure.get("left", []):
            if "pitch" in note:
                note["pitch"] = _to_flat(note["pitch"])
            if "pitches" in note:
                note["pitches"] = [_to_flat(pitch) for pitch in note["pitches"]]
    return measures


def _scale_midi(root_midi: int, degree: int) -> int:
    octave, step = divmod(degree, 7)
    if step < 0:
        step += 7
        octave -= 1
    return root_midi + MAJOR_SCALE_STEPS[step] + octave * 12


def _note(midi: int, duration: str) -> dict:
    return {"pitch": _midi_to_name(midi), "duration": duration}


def _chord(midis: list[int], duration: str) -> dict:
    return {"pitches": [_midi_to_name(m) for m in midis], "duration": duration}


def _measure(notes: list[dict]) -> dict:
    return {"notes": notes}


def _bounce(degree: int, direction: int, span: int) -> tuple[int, int]:
    if degree >= span:
        direction = -1
    elif degree <= 0:
        direction = 1
    return degree, direction


def _build_dexterity(rng: random.Random, root: int, difficulty: float, technique: Optional[str] = None) -> list[dict]:
    if "arpeggio" in (technique or "").lower():
        return _build_arpeggios(rng, root, difficulty)
    span = 7 + int(min(difficulty, 12) / 2)
    duration = "s" if difficulty >= 6 else "e"
    per_measure = int(BEATS_PER_MEASURE / {"s": 0.25, "e": 0.5, "q": 1.0}[duration])
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(per_measure):
            notes.append(_note(_scale_midi(root, degree), duration))
            degree += direction
            degree, direction = _bounce(degree, direction, span)
        measures.append(_measure(notes))
    return measures


def _build_arpeggios(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    duration = "s" if difficulty >= 6 else "e"
    per_measure = int(BEATS_PER_MEASURE / {"s": 0.25, "e": 0.5}[duration])
    progression = [0, 3, 4, 0]
    measures = []
    for measure_index in range(MEASURE_COUNT):
        degree = progression[measure_index % len(progression)]
        rising = [degree, degree + 2, degree + 4, degree + 7, degree + 9, degree + 11, degree + 14]
        figure = rising + rising[-2:0:-1]
        notes = [_note(_scale_midi(root, figure[i % len(figure)]), duration) for i in range(per_measure)]
        measures.append(_measure(notes))
    return measures


def _double_note_interval(technique: Optional[str], difficulty: float) -> int:
    name = (technique or "").lower()
    if "sixth" in name:
        return 5
    if "third" in name:
        return 2
    return 2 if difficulty >= 6 else 3


def _build_double_notes(rng: random.Random, root: int, difficulty: float, technique: Optional[str] = None) -> list[dict]:
    interval = _double_note_interval(technique, difficulty)
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(4):
            notes.append(_chord([_scale_midi(root, degree), _scale_midi(root, degree + interval)], "q"))
            degree += direction
            degree, direction = _bounce(degree, direction, 8)
        measures.append(_measure(notes))
    return measures


def _build_octaves(rng: random.Random, root: int, difficulty: float, technique: Optional[str] = None) -> list[dict]:
    broken = "broken" in (technique or "").lower()
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(4):
            base = _scale_midi(root, degree)
            if broken:
                notes.append(_note(base, "e"))
                notes.append(_note(base + 12, "e"))
            else:
                notes.append(_chord([base, base + 12], "q"))
            degree += direction * 2
            degree, direction = _bounce(degree, direction, 7)
        measures.append(_measure(notes))
    return measures


def _build_leaps(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(4):
            low = rng.randint(0, 3)
            high = low + rng.randint(6, 10)
            notes.append(_note(_scale_midi(root, low), "e"))
            notes.append(_note(_scale_midi(root, high), "e"))
        measures.append(_measure(notes))
    return measures


def _build_chords(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    progression = [0, 3, 4, 0]
    measures = []
    for measure_index in range(MEASURE_COUNT):
        degree = progression[measure_index % len(progression)]
        triad = [_scale_midi(root, degree), _scale_midi(root, degree + 2), _scale_midi(root, degree + 4)]
        measures.append(_measure([_chord(triad, "h"), _chord(triad, "h")]))
    return measures


def _build_repeated_notes(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    duration = "s" if difficulty >= 6 else "e"
    per_measure = int(BEATS_PER_MEASURE / {"s": 0.25, "e": 0.5}[duration])
    measures = []
    degree = 0
    for _ in range(MEASURE_COUNT):
        pitch = _scale_midi(root, degree)
        measures.append(_measure([_note(pitch, duration) for _ in range(per_measure)]))
        degree = (degree + 2) % 8
    return measures


def _build_trills(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    degree = 2
    for _ in range(MEASURE_COUNT):
        low = _scale_midi(root, degree)
        high = _scale_midi(root, degree + 1)
        notes = [low, high] * 8
        measures.append(_measure([_note(m, "s") for m in notes]))
        degree = 1 if degree == 2 else 2
    return measures


def _build_stretches(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    span = 9 if difficulty >= 7 else 7
    measures = []
    for measure_index in range(MEASURE_COUNT):
        base = _scale_midi(root, measure_index % 4)
        measures.append(_measure([_chord([base, base + span], "w")]))
    return measures


def _triplet(midi: int) -> dict:
    return {**_note(midi, "e"), "tuplet": 3}


def _build_polyrhythm(rng: random.Random, root: int, difficulty: float, technique: Optional[str] = None) -> list[dict]:
    four_three = "four" in (technique or "").lower()
    bass_root = root - 12
    measures = []
    degree, direction = 0, 1
    bass_degree = 0
    for measure_index in range(MEASURE_COUNT):
        right, left = [], []
        for _ in range(int(BEATS_PER_MEASURE)):
            for _ in range(4 if four_three else 3):
                midi = _scale_midi(root, degree)
                right.append(_note(midi, "s") if four_three else _triplet(midi))
                degree += direction
                degree, direction = _bounce(degree, direction, 7)
            chord_tones = [bass_degree, bass_degree + 4, bass_degree + 2]
            for tone in chord_tones[: 3 if four_three else 2]:
                midi = _scale_midi(bass_root, tone)
                left.append(_triplet(midi) if four_three else _note(midi, "e"))
        bass_degree = [0, 3, 4, 0][(measure_index + 1) % 4]
        measures.append({"notes": right, "left": left})
    return measures


def _build_voicing(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(4):
            soprano = _scale_midi(root, degree + 4)
            alto = _scale_midi(root, degree)
            notes.append(_chord([alto, soprano], "q"))
            degree += direction
            degree, direction = _bounce(degree, direction, 6)
        measures.append(_measure(notes))
    return measures


def _build_pedaling(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    degree, direction = 2, 1
    for measure_index in range(MEASURE_COUNT):
        bass = _scale_midi(root, -7 + (measure_index % 3))
        notes = [_chord([bass], "w")]
        measures.append(_measure(notes))
        degree, direction = _bounce(degree + direction, direction, 8)
    return measures


def _build_endurance(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    span = 10
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(8):
            notes.append(_note(_scale_midi(root, degree), "e"))
            degree += direction
            degree, direction = _bounce(degree, direction, span)
        measures.append(_measure(notes))
    return measures


CATEGORY_BUILDERS = {
    "dexterity": _build_dexterity,
    "double_notes": _build_double_notes,
    "octaves": _build_octaves,
    "leaps": _build_leaps,
    "chords": _build_chords,
    "repeated_notes": _build_repeated_notes,
    "trills": _build_trills,
    "stretches": _build_stretches,
    "polyrhythm": _build_polyrhythm,
    "voicing": _build_voicing,
    "pedaling": _build_pedaling,
    "endurance": _build_endurance,
}


TECHNIQUE_AWARE_BUILDERS = {_build_dexterity, _build_double_notes, _build_octaves, _build_polyrhythm}


class SightReadingForge:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def generate(
        self, category: Optional[str], difficulty: float, technique: Optional[str] = None, key: Optional[str] = None
    ) -> dict:
        drawn = self.rng.choice(KEYS)
        key = key if key in KEY_PITCH_CLASS else drawn
        pitch_class = KEY_PITCH_CLASS[key]
        if category in TWO_HAND_CATEGORIES:
            hand = "both"
        elif category in LEFT_HAND_CATEGORIES:
            hand = "left"
        else:
            hand = "right"
        root_midi = 60 + pitch_class - (12 if pitch_class > 7 else 0)
        if hand == "left":
            root_midi -= 12
        clamped = max(1.0, min(10.0, difficulty))
        tempo = int(58 + clamped * 8)
        builder = CATEGORY_BUILDERS.get(category or "", _build_dexterity)
        if builder in TECHNIQUE_AWARE_BUILDERS:
            measures = builder(self.rng, root_midi, clamped, technique)
        else:
            measures = builder(self.rng, root_midi, clamped)
        if key in FLAT_KEYS:
            measures = _respell_flats(measures)
        return {
            "technique": category or "dexterity",
            "technique_name": technique,
            "key": key,
            "time_signature": "4/4",
            "tempo_bpm": tempo,
            "hand": hand,
            "measures": measures,
        }
