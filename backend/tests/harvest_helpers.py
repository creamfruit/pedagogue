from pathlib import Path

from music21 import chord, instrument, key, meter, note, stream, tempo

BARS = 12
SECONDS = 23.0


def piano_part(name: str) -> stream.Part:
    part = stream.Part()
    part.partName = "Piano"
    part.id = name
    part.insert(0, instrument.Piano())
    return part


def right_hand(number: int) -> list:
    if number <= 4:
        return [note.Note(pitch, quarterLength=1) for pitch in (72, 74, 76, 77)]
    if number in (5, 6):
        return [chord.Chord([72, 84], quarterLength=0.25) for _ in range(16)]
    if number == 7:
        return [note.Note(60 if step % 2 == 0 else 84, quarterLength=0.5) for step in range(8)]
    if number == 8:
        return [note.Note(pitch, quarterLength=1) for pitch in (72, 74, 76, 77)]
    if number == 9:
        return [note.Note(72 + step % 3, quarterLength=1 / 3) for step in range(12)]
    if number == 10:
        return [note.Note(60 + step, quarterLength=0.25) for step in range(16)]
    return [note.Note(pitch, quarterLength=1) for pitch in (84, 86, 88)]


def left_hand(number: int) -> list:
    if number == 8:
        return [chord.Chord([36, 52], quarterLength=2) for _ in range(2)]
    if number >= 11:
        return [note.Note(48, quarterLength=3)]
    return [note.Note(48, quarterLength=2), note.Note(55, quarterLength=2)]


def build_study() -> stream.Score:
    right, left = piano_part("right"), piano_part("left")
    for number in range(1, BARS + 1):
        upper, lower = stream.Measure(number=number), stream.Measure(number=number)
        if number == 1:
            upper.append(tempo.MetronomeMark(number=120))
            for measure in (upper, lower):
                measure.append(meter.TimeSignature("4/4"))
                measure.append(key.KeySignature(0))
        if number == 11:
            for measure in (upper, lower):
                measure.append(meter.TimeSignature("3/4"))
                measure.append(key.KeySignature(1))
        for element in right_hand(number):
            upper.append(element)
        for element in left_hand(number):
            lower.append(element)
        right.append(upper)
        left.append(lower)
    score = stream.Score()
    score.insert(0, right)
    score.insert(0, left)
    return score


def write_study(folder: Path, kind: str) -> Path:
    score = build_study()
    if kind == "mid":
        path = folder / "study.mid"
        score.write("midi", fp=str(path))
    else:
        path = folder / "study.musicxml"
        score.write("musicxml", fp=str(path))
    return path
