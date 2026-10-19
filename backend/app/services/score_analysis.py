from __future__ import annotations

import math
import os
import re
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

T3 = "Double thirds"
T6 = "Double sixths"
BO = "Broken octaves"
OC = "Blocked octaves"
LP = "Wide leaps"
RC = "Repeated chords"
SC = "Rapid scales"
AR = "Arpeggio figuration"
RN = "Repeated notes"
TR = "Trills"
ST = "Tenth stretches"
P32 = "Three against two"
P43 = "Four against three"
MEL = "Melody over accompaniment"
END = "Sustained endurance"

LOAD = {T3: 1.7, T6: 1.6, BO: 1.5, OC: 1.8, LP: 1.3, RC: 1.65, SC: 1.1, AR: 1.15, RN: 1.35, TR: 1.25, ST: 1.55, P32: 1.2, P43: 1.4, MEL: 0.7}

SCORE_SUFFIXES = {".musicxml", ".xml", ".mxl", ".mid", ".midi", ".krn"}
TEMPO_WORDS = [
    ("prestissimo", 200), ("presto", 176), ("vivacissimo", 168), ("allegro molto", 160), ("allegro vivace", 156),
    ("vivace", 150), ("allegro assai", 150), ("allegro", 132), ("allegretto", 108), ("moderato", 96),
    ("andantino", 88), ("andante", 76), ("adagietto", 66), ("adagio", 56), ("larghetto", 56), ("lento", 50),
    ("largo", 46), ("grave", 42),
]

LABELS = {
    OC: "Octave passage", BO: "Broken-octave passage", T3: "Double-third run", T6: "Double-sixth passage",
    LP: "Leaping passage", RC: "Repeated-chord passage", SC: "Fast scales", AR: "Arpeggio figuration",
    RN: "Repeated-note passage", TR: "Trill passage", ST: "Wide stretches", P32: "Three against two",
    P43: "Four against three", MEL: "Melody over moving accompaniment",
}

PHRASES = {
    OC: "octaves", BO: "broken octaves", T3: "double thirds", T6: "double sixths", LP: "leaps",
    RC: "repeated chords", SC: "fast scale runs", AR: "arpeggio figuration", RN: "fast repeated notes",
    TR: "trills", ST: "stretches of a tenth or more", P32: "three against two between the hands",
    P43: "four against three between the hands", MEL: "a melody held over moving accompaniment",
}

CUES = {
    OC: "Practise the octaves blocked and slow with a loose wrist, then group them in fours at tempo.",
    BO: "Drill the rotation slowly with the thumb as the pivot, then speed up in short bursts.",
    T3: "Take the upper and lower lines separately first, then join them in dotted rhythms.",
    T6: "Keep the hand in a fixed frame and practise the fingering in pairs before joining.",
    LP: "Practise the jumps as a silent shift first: land on the target, then add the sound.",
    RC: "Drop from the arm on each chord and release between them; practise in groups at half tempo.",
    SC: "Practise in rhythms and in groups, placing the thumb without an accent.",
    AR: "Block each hand position as a chord first so the hand knows the shapes before the speed.",
    RN: "Change fingers on the repeated notes and practise with a light, shallow key stroke.",
    TR: "Build the trill from even rhythms, then measured groups, before letting it run free.",
    ST: "Roll or split the widest chords where the hand needs it and keep the wrist relaxed.",
    P32: "Tap the composite rhythm on a table first, then play it hands together very slowly.",
    P43: "Count the composite rhythm aloud and practise in the smallest shared unit before tempo.",
    MEL: "Play the melody alone for shape, then keep the accompaniment one level quieter underneath.",
}

HANDS = {0: "right hand", 1: "left hand"}


@dataclass
class NoteEvent:
    onset: float
    duration: float
    midi: int
    hand: int
    measure: int


@dataclass
class ParsedScore:
    events: list[NoteEvent]
    measure_starts: dict[int, float]
    measure_lengths: dict[int, float]
    quarter_bpm: float
    trills: set[tuple[int, int]] = field(default_factory=set)
    tempo_segments: list[tuple[float, float, float]] = field(default_factory=list)
    key: Optional[str] = None

    def clock(self):
        segments = self.tempo_segments or [(0.0, float("inf"), self.quarter_bpm)]
        starts, elapsed = [], 0.0
        for start, end, bpm in segments:
            starts.append((start, end, bpm, elapsed))
            if math.isfinite(end):
                elapsed += (end - start) * 60.0 / bpm

        def seconds(offset: float) -> float:
            for start, end, bpm, before in starts:
                if offset < end or not math.isfinite(end):
                    return before + max(offset - start, 0.0) * 60.0 / bpm
            start, end, bpm, before = starts[-1]
            return before + (offset - start) * 60.0 / bpm

        return seconds


@dataclass
class Passage:
    start: int
    end: int
    score: float
    difficulty: float
    label: str
    description: str
    cue: str
    techniques: dict[str, float]


@dataclass
class ScoreReport:
    measures: int
    duration_sec: float
    quarter_bpm: float
    notes: int
    notes_per_second_peak: float
    measure_scores: dict[int, float]
    techniques: list[tuple[str, float]]
    passages: list[Passage]
    features: dict[str, float]
    estimated_difficulty: float
    key: Optional[str] = None


def tempo_from_words(text: str) -> Optional[float]:
    lowered = text.lower()
    for word, bpm in TEMPO_WORDS:
        if word in lowered:
            return float(bpm)
    return None


def _measure_number(measure) -> int:
    number = getattr(measure, "number", None)
    if isinstance(number, int):
        return number
    digits = re.sub(r"\D", "", str(number or ""))
    return int(digits) if digits else 0


def parse_score(data: bytes, suffix: str) -> ParsedScore:
    from music21 import converter, expressions, stream, tempo

    suffix = suffix.lower()
    if suffix not in SCORE_SUFFIXES:
        raise ValueError(f"unsupported score file {suffix}")
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(data)
        handle.close()
        parsed = converter.parse(handle.name, forceSource=True)
    finally:
        os.unlink(handle.name)

    parts = list(parsed.parts) if hasattr(parsed, "parts") and parsed.parts else [parsed]
    piano_parts = [part for part in parts if "piano" in str(part.getInstrument(returnDefault=True)).lower() or "PartStaff" in type(part).__name__]
    if len(piano_parts) >= 1 and len(piano_parts) < len(parts):
        parts = piano_parts
    split_by_pitch = len(parts) == 1

    bpm = None
    segments: list[tuple[float, float, float]] = []
    try:
        for start, end, mark in parsed.metronomeMarkBoundaries():
            value = mark.getQuarterBPM()
            if value and 20 <= value <= 400 and end > start:
                segments.append((float(start), float(end), float(value)))
    except Exception:
        segments = []
    if segments:
        weights = sum(end - start for start, end, _ in segments)
        bpm = sum((end - start) * value for start, end, value in segments) / max(weights, 1e-6)
        if len(segments) == 1 and segments[0][2] == 120.0:
            segments, bpm = [], None
    if bpm is None:
        words = " ".join(
            str(getattr(item, "content", "") or getattr(item, "text", ""))
            for item in parsed.recurse().getElementsByClass(("TempoText", "TextExpression", "MetronomeMark"))
        )
        bpm = tempo_from_words(words) or 100.0

    events: list[NoteEvent] = []
    measure_starts: dict[int, float] = {}
    measure_lengths: dict[int, float] = {}
    trills: set[tuple[int, int]] = set()
    for hand_index, part in enumerate(parts[:2] if not split_by_pitch else parts[:1]):
        measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            measures = list(part.makeMeasures().getElementsByClass(stream.Measure))
        for measure in measures:
            number = _measure_number(measure)
            start = float(measure.offset)
            if number not in measure_starts or start < measure_starts[number]:
                measure_starts[number] = start
                measure_lengths[number] = float(measure.duration.quarterLength or measure.barDuration.quarterLength)
            for element in measure.recurse().notes:
                length = float(element.duration.quarterLength)
                if length == 0:
                    continue
                if element.tie is not None and element.tie.type in ("stop", "continue"):
                    continue
                onset = start + float(element.getOffsetInHierarchy(measure))
                pitches = [p.midi for p in element.pitches]
                if any(isinstance(expr, expressions.Trill) for expr in element.expressions):
                    trills.add((number, hand_index if not split_by_pitch else 0))
                for midi in pitches:
                    hand = hand_index
                    if split_by_pitch:
                        hand = 0 if midi >= 60 else 1
                    events.append(NoteEvent(onset, length, midi, min(hand, 1), number))
    events.sort(key=lambda e: (e.onset, e.hand, e.midi))
    key_text = None
    try:
        found = parsed.analyze("key")
        key_text = f"{found.tonic.name.replace('-', '-flat').replace('#', '-sharp')} {found.mode}"
    except Exception:
        key_text = None
    return ParsedScore(events, measure_starts, measure_lengths, bpm, trills, segments, key_text)


@dataclass
class Group:
    time: float
    pitches: list[int]
    measure: int


def hand_groups(events: Iterable[NoteEvent], hand: int, seconds) -> list[Group]:
    grouped: dict[tuple[float, int], list[int]] = defaultdict(list)
    for event in events:
        if event.hand == hand:
            grouped[(round(event.onset, 4), event.measure)].append(event.midi)
    groups = [Group(seconds(onset), sorted(set(pitches)), measure) for (onset, measure), pitches in grouped.items()]
    groups.sort(key=lambda g: g.time)
    return groups


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    runs, start = [], None
    for index, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index))
            start = None
    return runs


def hand_features(groups: list[Group], hand: int) -> dict[int, dict[str, float]]:
    found: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    count = len(groups)
    if not count:
        return found
    gaps = [groups[i + 1].time - groups[i].time for i in range(count - 1)] + [1.0]
    prev_gaps = [1.0] + gaps[:-1]

    for i, group in enumerate(groups):
        p = group.pitches
        bucket = found[group.measure]
        bucket["groups"] += 1
        bucket["notes"] += len(p)
        span = p[-1] - p[0]
        quick = min(gaps[i], prev_gaps[i])
        if len(p) >= 2 and span == 12 and len(p) <= 4 and quick <= 0.42:
            bucket[OC] += 1.0 if quick <= 0.25 else 0.6
        if len(p) >= 2 and span >= 15 and not (len(p) == 2 and span in (24, 36)):
            bucket[ST] += 1.0 if span >= 16 else 0.6
        if len(p) >= 3 and i > 0 and groups[i - 1].pitches == p and prev_gaps[i] <= 0.36:
            bucket[RC] += 1.0
        if i > 0 and prev_gaps[i] <= 0.34:
            centre = (p[0] + p[-1]) / 2
            before = groups[i - 1].pitches
            jump = abs(centre - (before[0] + before[-1]) / 2)
            if jump >= 12:
                bucket[LP] += min(jump / 18, 1.6) * (1.0 if prev_gaps[i] <= 0.2 else 0.7)

    def interval_run(lo: int, hi: int, name: str, max_gap: float) -> None:
        flags = []
        for i, group in enumerate(groups):
            p = group.pitches
            ok = len(p) >= 2 and any(lo <= p[j + 1] - p[j] <= hi for j in range(len(p) - 1)) and len(p) <= 3 and p[-1] - p[0] <= hi + 4
            flags.append(ok and min(gaps[i], prev_gaps[i]) <= max_gap)
        for start, end in _runs(flags):
            if end - start >= 3:
                for i in range(start, end):
                    found[groups[i].measure][name] += 1.0

    interval_run(3, 4, T3, 0.26)
    interval_run(8, 9, T6, 0.3)

    singles = [len(g.pitches) == 1 for g in groups]
    melody = [g.pitches[-1] for g in groups]

    def line_run(test, name: str, min_len: int, max_gap: float) -> None:
        flags = [False] * count
        for i in range(1, count):
            flags[i] = singles[i] and singles[i - 1] and prev_gaps[i] <= max_gap and test(melody[i - 1], melody[i], i)
        for start, end in _runs(flags):
            if end - start + 1 >= min_len:
                for i in range(start - 1, end):
                    found[groups[i].measure][name] += 1.0

    line_run(lambda a, b, i: 1 <= abs(b - a) <= 2 and (i < 2 or (b - a) * (melody[i - 1] - melody[i - 2]) > 0), SC, 7, 0.2)
    arpeggio = [False] * count
    for i in range(1, count):
        arpeggio[i] = singles[i] and singles[i - 1] and prev_gaps[i] <= 0.26 and 3 <= abs(melody[i] - melody[i - 1]) <= 9
    for start, end in _runs(arpeggio):
        if end - start + 1 >= 6 and max(melody[start - 1:end]) - min(melody[start - 1:end]) >= 12:
            for i in range(start - 1, end):
                found[groups[i].measure][AR] += 1.0
    line_run(lambda a, b, i: a == b, RN, 3, 0.2)
    line_run(lambda a, b, i: abs(b - a) == 12, BO, 4, 0.2)
    line_run(lambda a, b, i: 1 <= abs(b - a) <= 2 and i >= 2 and melody[i - 2] == b, TR, 5, 0.16)

    for i, group in enumerate(groups):
        if len(group.pitches) >= 1 and gaps[i] >= 0.55 and hand == 0:
            found[group.measure]["held"] += 1
        if len(group.pitches) >= 2 and gaps[i] <= 0.3:
            found[group.measure]["busy_chords"] += 1
    return found


def cross_rhythm(events: list[NoteEvent], beat_quarters: float = 1.0) -> dict[int, dict[str, float]]:
    positions: dict[tuple[int, int], dict[int, set[float]]] = defaultdict(lambda: defaultdict(set))
    for event in events:
        beat = math.floor(event.onset / beat_quarters + 1e-6)
        frac = round((event.onset / beat_quarters) - beat, 3)
        positions[(beat, event.measure)][event.hand].add(frac)
    found: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def has(fracs: set[float], targets: tuple[float, ...]) -> bool:
        return all(any(abs(f - t) < 0.02 for f in fracs) for t in targets)

    for (_beat, measure), hands in positions.items():
        a, b = hands.get(0, set()), hands.get(1, set())
        thirds, halves, quarters = (1 / 3, 2 / 3), (0.5,), (0.25, 0.75)
        for x, y in ((a, b), (b, a)):
            if has(x, thirds) and has(y, halves) and not has(y, thirds):
                found[measure][P32] += 1
            if has(x, thirds) and has(y, quarters) and not has(y, thirds):
                found[measure][P43] += 1
    return found


def technique_intensity(bucket: dict[str, float]) -> dict[str, float]:
    groups = max(bucket.get("groups", 0.0), 1.0)
    scale = {OC: 5, BO: 6, T3: 5, T6: 4, LP: 3, RC: 4, SC: 10, AR: 10, RN: 7, TR: 6, ST: 3, P32: 2, P43: 2}
    out = {}
    for name, per_bar in scale.items():
        value = bucket.get(name, 0.0)
        if value:
            out[name] = min(value / per_bar, 1.0) * (0.6 + 0.4 * min(value / groups, 1.0))
    return out


def analyse(parsed: ParsedScore) -> ScoreReport:
    seconds = parsed.clock()
    measures = sorted(parsed.measure_starts)
    per_hand = [hand_features(hand_groups(parsed.events, hand, seconds), hand) for hand in (0, 1)]
    crossing = cross_rhythm(parsed.events)

    notes_by_measure: dict[int, int] = defaultdict(int)
    for event in parsed.events:
        notes_by_measure[event.measure] += 1

    measure_scores: dict[int, float] = {}
    measure_tech: dict[int, dict[str, float]] = {}
    measure_hand_tech: dict[int, dict[str, int]] = {}
    nps_values: dict[int, float] = {}
    for number in measures:
        start = parsed.measure_starts[number]
        length_sec = max(seconds(start + max(parsed.measure_lengths.get(number, 4.0), 0.25)) - seconds(start), 0.2)
        nps = notes_by_measure.get(number, 0) / length_sec
        nps_values[number] = nps
        combined: dict[str, float] = {}
        dominant: dict[str, int] = {}
        for hand in (0, 1):
            bucket = per_hand[hand].get(number, {})
            for name, value in technique_intensity(bucket).items():
                if value > combined.get(name, 0.0):
                    combined[name] = value
                    dominant[name] = hand
                elif value > 0.2 and abs(value - combined.get(name, 0.0)) < 0.15:
                    dominant[name] = 2
        for name, value in technique_intensity(crossing.get(number, {})).items():
            combined[name] = max(combined.get(name, 0.0), value)
            dominant.setdefault(name, 2)
        if (number, 0) in parsed.trills or (number, 1) in parsed.trills:
            combined[TR] = max(combined.get(TR, 0.0), 0.6)
            dominant.setdefault(TR, 0 if (number, 0) in parsed.trills else 1)
        right, left = per_hand[0].get(number, {}), per_hand[1].get(number, {})
        if right.get("held", 0) >= 1 and left.get("groups", 0) >= 6 and nps >= 5:
            combined[MEL] = min(0.3 + left.get("groups", 0) / 24, 0.8)
            dominant[MEL] = 2
        density = min(nps / 14.0, 1.5)
        chords = min((right.get("busy_chords", 0) + left.get("busy_chords", 0)) / 8.0, 1.0)
        technique_load = sum(LOAD.get(name, 1.0) * value for name, value in combined.items() if name != MEL)
        measure_scores[number] = round(3.2 * density + 1.4 * chords + 1.1 * technique_load, 3)
        measure_tech[number] = combined
        measure_hand_tech[number] = dominant

    passages = pick_passages(measures, measure_scores, measure_tech, measure_hand_tech, nps_values)
    techniques = piece_techniques(measures, measure_tech, measure_scores)
    duration = sum(
        seconds(parsed.measure_starts[n] + max(parsed.measure_lengths.get(n, 4.0), 0.25)) - seconds(parsed.measure_starts[n])
        for n in measures
    )
    values = sorted(measure_scores.values()) or [0.0]
    features = {
        "p90": values[int(0.9 * (len(values) - 1))],
        "p50": statistics.median(values),
        "peak": values[-1],
        "minutes": duration / 60,
        "nps_peak": max(nps_values.values() or [0.0]),
        "tech_peak": max((sum(LOAD.get(k, 1) * v for k, v in t.items()) for t in measure_tech.values()), default=0.0),
    }
    endurance = min(1.0, (features["p50"] / 6.0) * min(features["minutes"] / 6.0, 1.3))
    if endurance >= 0.35:
        techniques.append((END, round(endurance, 2)))
        techniques.sort(key=lambda item: -item[1])
    return ScoreReport(
        measures=len(measures),
        duration_sec=round(duration, 1),
        quarter_bpm=parsed.quarter_bpm,
        notes=len(parsed.events),
        notes_per_second_peak=round(features["nps_peak"], 1),
        measure_scores=measure_scores,
        techniques=techniques[:5],
        passages=passages,
        features=features,
        estimated_difficulty=estimate_from_features(features),
        key=parsed.key,
    )


def estimate_from_features(features: dict[str, float]) -> float:
    raw = 18 + 6.2 * features["p90"] + 1.6 * features["p50"] + 4.0 * math.log1p(features["minutes"]) + 0.8 * features["tech_peak"]
    return round(min(max(raw, 5.0), 97.0), 1)


def pick_passages(measures, scores, techs, hands, nps, limit: Optional[int] = None) -> list[Passage]:
    if not measures:
        return []
    smooth = {}
    for index, number in enumerate(measures):
        window = [scores[measures[j]] for j in range(max(0, index - 1), min(len(measures), index + 2))]
        smooth[number] = 0.5 * scores[number] + 0.5 * (sum(window) / len(window))
    ordered = sorted(smooth.values())
    threshold = max(ordered[int(0.75 * (len(ordered) - 1))], statistics.median(ordered) * 1.25, 2.0)
    flags = [smooth[n] >= threshold for n in measures]
    for i in range(1, len(flags) - 1):
        if not flags[i] and flags[i - 1] and flags[i + 1]:
            flags[i] = True
    candidates = []
    for start, end in _runs(flags):
        span = measures[start:end]
        if len(span) > 10:
            best, best_value = 0, -1.0
            for offset in range(0, len(span) - 7):
                value = sum(scores[n] for n in span[offset:offset + 8])
                if value > best_value:
                    best, best_value = offset, value
            span = span[best:best + 8]
        if len(span) < 2:
            continue
        mean = sum(scores[n] for n in span) / len(span)
        candidates.append((mean * math.sqrt(len(span)), span, mean))
    wanted = limit or max(2, min(5, len(measures) // 22 + 1))
    if len(candidates) < min(2, wanted) and len(measures) >= 4:
        taken: set[int] = {n for _, span, _ in candidates for n in span}
        windows = []
        for index in range(0, len(measures) - 3):
            span = measures[index:index + 4]
            windows.append((sum(scores[n] for n in span) / 4, span))
        windows.sort(key=lambda item: -item[0])
        for mean, span in windows:
            if len(candidates) >= min(3, wanted):
                break
            if taken.intersection(span) or any(abs(span[0] - n) < 6 for n in taken):
                continue
            candidates.append((mean * 2, span, mean))
            taken.update(span)
    candidates.sort(key=lambda item: -item[0])
    top_mean = max((c[2] for c in candidates), default=1.0) or 1.0
    chosen = []
    for rank, span, mean in candidates[:wanted]:
        tech: dict[str, float] = defaultdict(float)
        hand_votes: dict[str, list[int]] = defaultdict(list)
        for number in span:
            for name, value in techs[number].items():
                tech[name] += value / len(span)
                hand_votes[name].append(hands[number].get(name, 2))
        ranked = sorted(((n, round(min(v * 1.4, 1.0), 2)) for n, v in tech.items() if v >= 0.12), key=lambda item: -item[1] * LOAD.get(item[0], 1))
        ranked = ranked[:3]
        peak_nps = max(nps[n] for n in span)
        label, description, cue = describe(span, ranked, hand_votes, peak_nps, measures)
        chosen.append(Passage(span[0], span[-1], round(mean, 2), round(mean / top_mean, 3), label, description, cue, dict(ranked)))
    chosen.sort(key=lambda p: -p.score)
    return chosen


def _hand_phrase(votes: list[int]) -> str:
    if not votes:
        return ""
    right, left = votes.count(0), votes.count(1)
    if right > 2 * max(left, 1) and right > votes.count(2):
        return " in the right hand"
    if left > 2 * max(right, 1) and left > votes.count(2):
        return " in the left hand"
    if votes.count(2) > (right + left):
        return " in both hands"
    return ""


def describe(span, ranked, hand_votes, peak_nps, measures) -> tuple[str, str, str]:
    bars = f"Bars {span[0]}–{span[-1]}" if span[0] != span[-1] else f"Bar {span[0]}"
    if ranked:
        top = ranked[0][0]
        label = LABELS.get(top, "Busiest bars")
        parts = [PHRASES[name] + ("" if name in (P32, P43, MEL) else _hand_phrase(hand_votes[name])) for name, _ in ranked if name in PHRASES]
        body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        cue = CUES.get(top, "Isolate the bars, practise hands separately at half tempo and rebuild gradually.")
    else:
        label = "Busiest bars"
        body = "the thickest, busiest writing in the piece"
        cue = "Isolate the bars, practise hands separately at half tempo and rebuild gradually."
    if span[0] == measures[0] or span[0] - measures[0] <= 1:
        label = f"Opening: {label.lower()}"
    elif span[-1] >= measures[-1] - 1:
        label = f"Closing bars: {label.lower()}"
    speed = f", peaking around {round(peak_nps)} notes a second" if peak_nps >= 8 else ""
    description = f"{bars}: {body}{speed}."
    return label[:120], description[0].upper() + description[1:], cue


def piece_techniques(measures, techs, scores) -> list[tuple[str, float]]:
    if not measures:
        return []
    totals: dict[str, float] = defaultdict(float)
    weight_sum = sum(max(scores[n], 0.1) for n in measures)
    for number in measures:
        for name, value in techs[number].items():
            totals[name] += value * max(scores[number], 0.1)
    ranked = []
    for name, total in totals.items():
        share = total / weight_sum
        peak = max(techs[n].get(name, 0.0) for n in measures)
        weight = min(1.0, 0.25 + 1.6 * share + 0.35 * peak)
        if share >= 0.03 or peak >= 0.8:
            ranked.append((name, round(weight, 2)))
    ranked.sort(key=lambda item: -item[1])
    return ranked[:5]


def analyse_file(data: bytes, filename: str) -> ScoreReport:
    suffix = os.path.splitext(filename.lower())[1]
    return analyse(parse_score(data, suffix))
