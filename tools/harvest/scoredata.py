import math
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Optional

TEMPO_WORDS = [
    ("prestissimo", 200), ("presto", 176), ("vivacissimo", 168), ("allegro molto", 160), ("allegro vivace", 156),
    ("vivace", 150), ("allegro assai", 150), ("allegro", 132), ("allegretto", 108), ("moderato", 96),
    ("andantino", 88), ("andante", 76), ("adagietto", 66), ("adagio", 56), ("larghetto", 56), ("lento", 50),
    ("largo", 46), ("grave", 42),
]
PIANO_NAME = re.compile(r"piano|klavier|keyboard|pianoforte|clavier", re.I)
DEFAULT_BPM = 100.0
MIN_BPM, MAX_BPM = 20.0, 400.0
GRID_LIMIT = 48
MIDDLE_C = 60


class UnreadableScore(Exception):
    pass


def tempo_word(text: str) -> Optional[tuple[str, float]]:
    lowered = (text or "").lower()
    for word, bpm in TEMPO_WORDS:
        if word in lowered:
            return word, float(bpm)
    return None


@dataclass
class Hit:
    onset: float
    duration: float
    pitches: tuple
    hand: int
    tuplet: Optional[str] = None
    bar: int = 0


@dataclass
class ScoreData:
    hits: list
    bars: list
    segments: list
    metres: list
    keys: list
    marks: list
    words: list
    part_names: list = field(default_factory=list)
    pickup: float = 0.0
    tempo_guessed: bool = False

    @property
    def starts(self) -> list:
        return [start for _, start, _ in self.bars]

    def bar_at(self, offset: float) -> int:
        index = bisect_right(self.starts, offset + 1e-6) - 1
        index = min(max(index, 0), len(self.bars) - 1)
        return self.bars[index][0]

    def clock(self):
        segments = self.segments or [(0.0, math.inf, DEFAULT_BPM)]
        table, elapsed = [], 0.0
        for start, end, bpm in segments:
            table.append((start, end, bpm, elapsed))
            if math.isfinite(end):
                elapsed += (end - start) * 60.0 / bpm

        def seconds(offset: float) -> float:
            for start, end, bpm, before in table:
                if offset < end or not math.isfinite(end):
                    return before + max(offset - start, 0.0) * 60.0 / bpm
            start, end, bpm, before = table[-1]
            return before + (offset - start) * 60.0 / bpm

        return seconds


def lilypond_pickup(text: str) -> float:
    found = re.search(r"\\partial\s*(\d+)(\.*)(?:\s*\*\s*(\d+)(?:/(\d+))?)?", text)
    if not found:
        return 0.0
    length = Fraction(4, int(found.group(1)))
    dots = len(found.group(2))
    if dots:
        length *= 2 - Fraction(1, 2**dots)
    if found.group(3):
        length *= int(found.group(3))
        if found.group(4):
            length /= int(found.group(4))
    return float(length)


def lilypond_tempo_words(text: str) -> list:
    from .mutopia import parse_ly_header

    words = [match.group(1) for match in re.finditer(r'\\tempo\s+"([^"]+)"', text)]
    header = parse_ly_header(text)
    for key in ("piece", "title", "subtitle", "opus"):
        if header.get(key):
            words.append(header[key])
    return words


def grid_kind(quarter_length: float, offset: float) -> Optional[str]:
    for value in (quarter_length, offset):
        fraction = Fraction(value).limit_denominator(GRID_LIMIT)
        if abs(float(fraction) - value) > 1e-3:
            return "irregular"
        denominator = fraction.denominator
        while denominator % 2 == 0:
            denominator //= 2
        if denominator == 3:
            return "3:2"
        if denominator == 5:
            return "5:4"
        if denominator == 7:
            return "7:4"
        if denominator > 1:
            return "other"
    return None


def tuplet_label(element) -> Optional[str]:
    tuplets = getattr(element.duration, "tuplets", ())
    if tuplets:
        actual, normal = tuplets[0].numberNotesActual, tuplets[0].numberNotesNormal
        return f"{actual}:{normal}"
    return None


def pitches_of(element) -> list:
    if element.isChord:
        return [member.pitch.midi for member in element.notes if not (member.tie is not None and member.tie.type in ("stop", "continue"))]
    if element.tie is not None and element.tie.type in ("stop", "continue"):
        return []
    return [element.pitch.midi]


def collect_hits(part, hand: int) -> list:
    grouped: dict = {}
    for element in part.flatten().notes:
        if element.duration.isGrace or element.duration.quarterLength <= 0:
            continue
        pitches = pitches_of(element)
        if not pitches:
            continue
        onset = round(float(element.offset), 4)
        label = tuplet_label(element) or grid_kind(float(element.duration.quarterLength), onset)
        slot = grouped.get(onset)
        if slot is None:
            grouped[onset] = Hit(onset, float(element.duration.quarterLength), tuple(sorted(set(pitches))), hand, label)
        else:
            slot.pitches = tuple(sorted(set(slot.pitches) | set(pitches)))
            slot.duration = min(slot.duration, float(element.duration.quarterLength))
            slot.tuplet = slot.tuplet or label
    return sorted(grouped.values(), key=lambda hit: hit.onset)


def mean_pitch(hits: list) -> float:
    values = [pitch for hit in hits for pitch in hit.pitches]
    return sum(values) / len(values) if values else 0.0


def split_by_pitch(hits: list) -> tuple:
    upper: dict = {}
    lower: dict = {}
    for hit in hits:
        high = tuple(pitch for pitch in hit.pitches if pitch >= MIDDLE_C)
        low = tuple(pitch for pitch in hit.pitches if pitch < MIDDLE_C)
        if high:
            upper[hit.onset] = Hit(hit.onset, hit.duration, high, 0, hit.tuplet)
        if low:
            lower[hit.onset] = Hit(hit.onset, hit.duration, low, 1, hit.tuplet)
    return sorted(upper.values(), key=lambda h: h.onset), sorted(lower.values(), key=lambda h: h.onset)


def tempo_segments(score) -> tuple:
    segments, marks = [], []
    try:
        boundaries = list(score.metronomeMarkBoundaries())
    except Exception:
        boundaries = []
    for start, end, mark in boundaries:
        value = mark.getQuarterBPM() if hasattr(mark, "getQuarterBPM") else None
        if value and MIN_BPM <= value <= MAX_BPM and end > start:
            segments.append((float(start), float(end), float(value)))
    if segments:
        segments[0] = (0.0, segments[0][1], segments[0][2])
        segments[-1] = (segments[-1][0], math.inf, segments[-1][2])
    seen = set()
    for mark in score.recurse().getElementsByClass("MetronomeMark"):
        value = mark.getQuarterBPM()
        key = (round(float(mark.getOffsetInHierarchy(score)), 3), round(value or 0, 1))
        if key in seen:
            continue
        seen.add(key)
        marks.append({"offset": key[0], "bpm": float(value) if value else None, "text": str(mark.text or "")})
    return segments, marks


def text_words(score) -> list:
    words = []
    for element in score.recurse().getElementsByClass(("TempoText", "TextExpression", "MetronomeMark")):
        text = str(getattr(element, "text", None) or getattr(element, "content", None) or "")
        if text and tempo_word(text):
            words.append(text.strip())
    return words


def signature_events(score) -> tuple:
    metres, keys = [], []
    seen_metre, seen_key = set(), set()
    for element in score.recurse().getElementsByClass("TimeSignature"):
        offset = round(float(element.getOffsetInHierarchy(score)), 3)
        label = element.ratioString
        if (offset, label) not in seen_metre:
            seen_metre.add((offset, label))
            metres.append((offset, label, float(element.barDuration.quarterLength)))
    for element in score.recurse().getElementsByClass("KeySignature"):
        offset = round(float(element.getOffsetInHierarchy(score)), 3)
        label = f"{element.asKey().tonic.name.replace('-', 'b')} {element.asKey().mode}" if hasattr(element, "asKey") else str(element)
        if (offset, label) not in seen_key:
            seen_key.add((offset, label))
            keys.append((offset, label, getattr(element, "sharps", 0)))
    metres.sort()
    keys.sort()
    return metres, keys


def synthetic_bars(metres: list, end: float, pickup: float) -> list:
    table = sorted(metres) or [(0.0, "4/4", 4.0)]
    bars: list = []
    offset, number = 0.0, 1
    if pickup > 0:
        bars.append((0, 0.0, pickup))
        offset = pickup
    index = 0
    while offset < end + 1.0 and number < 5000:
        while index + 1 < len(table) and table[index + 1][0] <= offset + 1e-6:
            index += 1
        length = table[index][2]
        bars.append((number, offset, length))
        offset += length
        number += 1
    return bars


def xml_bars(part) -> list:
    from music21 import stream

    bars = []
    for measure in part.getElementsByClass(stream.Measure):
        number = measure.number if isinstance(measure.number, int) else int(re.sub(r"\D", "", str(measure.number)) or 0)
        length = float(measure.duration.quarterLength or measure.barDuration.quarterLength)
        bars.append((number, float(measure.offset), length))
    unique = []
    for number, start, length in bars:
        if not unique or start > unique[-1][1] + 1e-6:
            unique.append((number, start, length))
    return unique


def choose_piano_parts(parts: list) -> list:
    named = [part for part in parts if PIANO_NAME.search(str(part.partName or "")) or PIANO_NAME.search(str(part.getInstrument(returnDefault=True).instrumentName or ""))]
    return named


def load_score(path: Path, kind: str, lilypond_text: Optional[str] = None) -> ScoreData:
    import warnings

    from music21 import converter, stream

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = converter.parse(str(path), forceSource=True)
    except Exception as error:
        raise UnreadableScore(f"music21 could not read {Path(path).name}: {error}") from error
    parts = [part for part in (parsed.parts if hasattr(parsed, "parts") else [parsed]) if any(True for _ in part.flatten().notes)]
    if not parts:
        raise UnreadableScore("the score has no notes")
    part_names = [str(part.partName or "") for part in parts]
    if kind == "mxl" or kind == "musicxml":
        chosen = choose_piano_parts(parts)
        if not chosen:
            raise UnreadableScore("the score has no piano part")
        parts = chosen
    pickup = lilypond_pickup(lilypond_text) if lilypond_text and kind == "mid" else 0.0
    end = max(float(part.highestTime) for part in parts)

    if kind == "mid":
        metres, keys = signature_events(parsed)
        bars = synthetic_bars(metres, end, pickup)
    else:
        metres, keys = signature_events(parts[0])
        bars = xml_bars(parts[0]) or synthetic_bars(metres, end, 0.0)

    ordered = sorted(parts[:4], key=lambda part: -sum(1 for _ in part.flatten().notes))[:2] if len(parts) > 2 else parts
    if len(ordered) >= 2:
        first = collect_hits(ordered[0], 0)
        second = collect_hits(ordered[1], 1)
        if mean_pitch(first) < mean_pitch(second):
            first, second = second, first
            for hit in first:
                hit.hand = 0
            for hit in second:
                hit.hand = 1
        hits = first + second
    else:
        upper, lower = split_by_pitch(collect_hits(ordered[0], 0))
        hits = upper + lower
    if not hits:
        raise UnreadableScore("the score has no notes")

    segments, marks = tempo_segments(parsed)
    words = text_words(parsed)
    if lilypond_text:
        words += lilypond_tempo_words(lilypond_text)
    data = ScoreData(hits=hits, bars=bars, segments=segments, metres=[], keys=[], marks=[], words=words, part_names=part_names, pickup=pickup)
    for hit in data.hits:
        hit.bar = data.bar_at(hit.onset)
    data.metres = [(data.bar_at(offset), label) for offset, label, _ in metres]
    data.keys = [(data.bar_at(offset), label) for offset, label, _ in keys]
    data.marks = [{"bar": data.bar_at(mark["offset"]), "bpm": mark["bpm"], "text": mark["text"]} for mark in marks]
    if not data.segments:
        guess = next((tempo_word(word) for word in words if tempo_word(word)), None)
        bpm = guess[1] if guess else DEFAULT_BPM
        data.segments = [(0.0, math.inf, bpm)]
        data.tempo_guessed = True
    return data
