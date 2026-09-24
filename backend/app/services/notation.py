from __future__ import annotations

import random
from typing import Optional

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_SCALE_STEPS = [0, 2, 4, 5, 7, 9, 11]
KEYS = ["C", "G", "D", "A", "F", "Bb", "Eb"]
BEATS_PER_MEASURE = 4.0
MEASURE_COUNT = 8


def _midi_to_name(midi: int) -> str:
    octave = midi // 12 - 1
    name = NOTE_NAMES[midi % 12]
    return f"{name}{octave}"


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


def _build_dexterity(rng: random.Random, root: int, difficulty: float) -> list[dict]:
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


def _build_double_notes(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    interval = 2 if difficulty >= 6 else 3
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


def _build_octaves(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    degree, direction = 0, 1
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(4):
            base = _scale_midi(root, degree)
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


def _build_polyrhythm(rng: random.Random, root: int, difficulty: float) -> list[dict]:
    measures = []
    degree = 0
    for _ in range(MEASURE_COUNT):
        notes = []
        for _ in range(3):
            notes.append(_note(_scale_midi(root, degree), "e"))
            degree = (degree + 1) % 8
        notes.append(_note(_scale_midi(root, degree), "q"))
        measures.append(_measure(notes))
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


class SightReadingForge:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def generate(self, category: Optional[str], difficulty: float) -> dict:
        key = self.rng.choice(KEYS)
        root_midi = 60 + self.rng.choice([-12, -5, 0, 5])
        clamped = max(1.0, min(10.0, difficulty))
        tempo = int(58 + clamped * 8)
        builder = CATEGORY_BUILDERS.get(category or "", _build_dexterity)
        measures = builder(self.rng, root_midi, clamped)
        return {
            "technique": category or "dexterity",
            "key": key,
            "time_signature": "4/4",
            "tempo_bpm": tempo,
            "measures": measures,
        }
