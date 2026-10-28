import math
from collections import Counter
from typing import Optional

import numpy as np

from .scoredata import ScoreData, tempo_word

FEATURE_VERSION = 2
VECTOR_DIM = 64
JOIN_GAP = 1.0
RUN_GAP = 0.26
RUN_STEP = 4
RUN_MIN = 6
BROKEN_OCTAVE_MIN = 4
OCTAVE_RUN_MIN = 3
WINDOW = 1.0
MIN_HITS = 8
MIN_BARS = 2

BAR_KEYS = ("notes", "onsets", "span", "leap", "octave", "tuplet", "run", "window")


def round3(value: float) -> float:
    return round(float(value), 3)


def percentile(values: list, q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0


def is_octave(pitches: tuple) -> bool:
    return 2 <= len(pitches) <= 3 and pitches[-1] - pitches[0] in (12, 24) and pitches[0] % 12 == pitches[-1] % 12


def centre(pitches: tuple) -> float:
    return sum(pitches) / len(pitches)


def hand_pass(hits: list, per_bar: dict, found: dict) -> None:
    previous = None
    octave_streak = 0
    broken_streak = 1
    run: list = []

    def close_run() -> None:
        if len(run) >= RUN_MIN:
            found["runs"].append(len(run))
            for hit in run:
                per_bar[hit.bar]["run"] += len(hit.pitches)
        run.clear()

    for index, hit in enumerate(hits):
        bar = per_bar[hit.bar]
        pitches = hit.pitches
        bar["notes"] += len(pitches)
        bar["onsets"] += 1
        found["notes"] += len(pitches)
        found["hits"] += 1
        found["low"] = min(found["low"], pitches[0])
        found["high"] = max(found["high"], pitches[-1])
        if len(pitches) >= 2:
            span = pitches[-1] - pitches[0]
            found["spans"].append(span)
            bar["span"] = max(bar["span"], span)
        if hit.tuplet and hit.tuplet != "irregular":
            bar["tuplet"] += len(pitches)
            found["tuplet_notes"] += len(pitches)
            found["tuplet_kinds"][hit.tuplet] += len(pitches)

        octave = is_octave(pitches)
        if octave:
            bar["octave"] += 1
            found["octave_events"] += 1
        gap = hit.onset - previous.onset if previous is not None else math.inf
        if octave and previous is not None and is_octave(previous.pitches) and gap <= JOIN_GAP:
            octave_streak += 1
        else:
            if octave_streak >= OCTAVE_RUN_MIN:
                found["octave_runs"].append(octave_streak)
            octave_streak = 1 if octave else 0
        if len(pitches) == 1 and previous is not None and len(previous.pitches) == 1 and gap <= 0.5 and abs(pitches[0] - previous.pitches[0]) == 12:
            broken_streak += 1
        else:
            if broken_streak >= BROKEN_OCTAVE_MIN:
                found["broken_octaves"] += broken_streak
            broken_streak = 1

        if previous is not None and gap <= JOIN_GAP:
            jump = abs(centre(pitches) - centre(previous.pitches))
            found["leaps"].append(jump)
            bar["leap"] = max(bar["leap"], jump)
        if previous is not None and gap <= RUN_GAP and 0 < abs(centre(pitches) - centre(previous.pitches)) <= RUN_STEP:
            if not run:
                run.append(previous)
            run.append(hit)
        else:
            close_run()
        previous = hit

        reach = [pitch for other in hits[index : index + 24] if other.onset < hit.onset + WINDOW for pitch in other.pitches]
        if len(reach) >= 2:
            width = max(reach) - min(reach)
            found["windows"].append(width)
            bar["window"] = max(bar["window"], width)
    close_run()
    if octave_streak >= OCTAVE_RUN_MIN:
        found["octave_runs"].append(octave_streak)
    if broken_streak >= BROKEN_OCTAVE_MIN:
        found["broken_octaves"] += broken_streak


def extract(data: ScoreData) -> dict:
    hits = sorted(data.hits, key=lambda hit: (hit.onset, hit.hand))
    if len(hits) < MIN_HITS:
        raise ValueError("the score has too few notes to measure")
    last_bar = max(hit.bar for hit in hits)
    bars = [bar for bar in data.bars if bar[0] <= last_bar]
    if len(bars) < MIN_BARS:
        raise ValueError("the score has too few bars to measure")
    per_bar = {number: dict.fromkeys(BAR_KEYS, 0.0) for number, _, _ in bars}
    per_hand = {}
    for hand in (0, 1):
        found = {
            "notes": 0, "hits": 0, "low": 127, "high": 0, "spans": [], "leaps": [], "windows": [], "runs": [],
            "tuplet_notes": 0, "tuplet_kinds": Counter(), "octave_events": 0, "octave_runs": [], "broken_octaves": 0,
        }
        hand_pass([hit for hit in hits if hit.hand == hand], per_bar, found)
        per_hand[hand] = found

    clock = data.clock()
    ends = {number: (start, start + length) for number, start, length in bars}
    seconds = {number: max(clock(end) - clock(start), 1e-3) for number, (start, end) in ends.items()}
    order = [number for number, _, _ in bars]
    notes_per_bar = [per_bar[number]["notes"] for number in order]
    nps = [per_bar[number]["notes"] / seconds[number] for number in order]
    onsets = [per_bar[number]["onsets"] for number in order]

    def both(key: str) -> list:
        return per_hand[0][key] + per_hand[1][key]

    spans, leaps, windows = both("spans"), both("leaps"), both("windows")
    total_notes = sum(found["notes"] for found in per_hand.values())
    total_hits = sum(found["hits"] for found in per_hand.values())
    runs = both("runs")
    octave_runs = both("octave_runs")
    kinds = per_hand[0]["tuplet_kinds"] + per_hand[1]["tuplet_kinds"]
    tuplet_notes = sum(kinds.values())
    complex_notes = sum(count for kind, count in kinds.items() if kind not in ("3:2", "6:4"))
    by_onset: Counter = Counter()
    for hit in hits:
        by_onset[hit.onset] += len(hit.pitches)
    simultaneous = list(by_onset.values())

    end_offset = max(hit.onset + hit.duration for hit in hits)
    total_seconds = max(clock(end_offset) - clock(0.0), 0.0)
    segments = data.segments
    weights = [(end - start) if math.isfinite(end) else max(end_offset - start, 1.0) for start, end, _ in segments]
    bpm_mean = sum(weight * bpm for weight, (_, _, bpm) in zip(weights, segments)) / max(sum(weights), 1e-6)
    tempo_words = []
    for word in data.words:
        found_word = tempo_word(word)
        if found_word and found_word[0] not in tempo_words:
            tempo_words.append(found_word[0])

    metre_labels = [label for _, label in data.metres]
    key_labels = [label for _, label in data.keys]
    leaps_sorted = sorted(leaps, reverse=True)
    bar_count = len(order)

    return {
        "version": FEATURE_VERSION,
        "bars": bar_count,
        "pickup": data.pickup > 0 or bars[0][0] == 0,
        "length": {"seconds": round3(total_seconds), "minutes": round3(total_seconds / 60.0), "quarters": round3(end_offset)},
        "notes": {
            "total": total_notes,
            "hits": total_hits,
            "mean_per_bar": round3(np.mean(notes_per_bar)),
            "p90_per_bar": round3(percentile(notes_per_bar, 90)),
            "max_per_bar": int(max(notes_per_bar)),
            "onsets_mean_per_bar": round3(np.mean(onsets)),
            "nps_mean": round3(np.mean(nps)),
            "nps_p90": round3(percentile(nps, 90)),
            "nps_peak": round3(max(nps)),
            "lowest": int(min(found["low"] for found in per_hand.values())),
            "highest": int(max(found["high"] for found in per_hand.values())),
            "left_share": round3(per_hand[1]["notes"] / max(total_notes, 1)),
            "polyphony_mean": round3(np.mean(simultaneous)),
            "polyphony_max": int(max(simultaneous)),
        },
        "span": {
            "max": int(max(spans)) if spans else 0,
            "p95": round3(percentile(spans, 95)),
            "ge_octave": sum(1 for value in spans if value >= 12),
            "ge_ninth": sum(1 for value in spans if value >= 14),
            "ge_tenth": sum(1 for value in spans if value >= 16),
            "window_max": int(max(windows)) if windows else 0,
            "window_p95": round3(percentile(windows, 95)),
            "right_max": int(max(per_hand[0]["spans"])) if per_hand[0]["spans"] else 0,
            "left_max": int(max(per_hand[1]["spans"])) if per_hand[1]["spans"] else 0,
        },
        "leaps": {
            "max": round3(leaps_sorted[0]) if leaps_sorted else 0.0,
            "top5_mean": round3(np.mean(leaps_sorted[:5])) if leaps_sorted else 0.0,
            "ge_octave": sum(1 for value in leaps if value >= 12),
            "ge_tenth": sum(1 for value in leaps if value >= 16),
            "ge_two_octaves": sum(1 for value in leaps if value >= 24),
        },
        "octaves": {
            "events": per_hand[0]["octave_events"] + per_hand[1]["octave_events"],
            "repeated": sum(octave_runs) + per_hand[0]["broken_octaves"] + per_hand[1]["broken_octaves"],
            "longest_run": int(max(octave_runs)) if octave_runs else 0,
            "broken": per_hand[0]["broken_octaves"] + per_hand[1]["broken_octaves"],
            "fraction": round3((per_hand[0]["octave_events"] + per_hand[1]["octave_events"]) / max(total_hits, 1)),
        },
        "tuplets": {
            "notes": tuplet_notes,
            "fraction": round3(tuplet_notes / max(total_notes, 1)),
            "complex_notes": complex_notes,
            "complex_fraction": round3(complex_notes / max(total_notes, 1)),
            "kinds": dict(kinds),
        },
        "runs": {
            "count": len(runs),
            "notes": int(sum(runs)),
            "fraction": round3(sum(runs) / max(total_hits, 1)),
            "longest": int(max(runs)) if runs else 0,
        },
        "tempo": {
            "first_bpm": round3(segments[0][2]),
            "mean_bpm": round3(bpm_mean),
            "changes": max(len(segments) - 1, 0),
            "marks": [{"bar": mark["bar"], "bpm": round3(mark["bpm"]) if mark["bpm"] else None, "text": mark["text"]} for mark in data.marks[:24]],
            "words": tempo_words,
            "guessed": bool(data.tempo_guessed),
        },
        "metre": {
            "signatures": [{"bar": bar, "sig": label} for bar, label in data.metres[:24]],
            "changes": sum(1 for a, b in zip(metre_labels, metre_labels[1:]) if a != b),
        },
        "key": {
            "signatures": [{"bar": bar, "key": label} for bar, label in data.keys[:24]],
            "changes": sum(1 for a, b in zip(key_labels, key_labels[1:]) if a != b),
        },
        "per_bar": {
            "numbers": order,
            "seconds": [round3(seconds[number]) for number in order],
            **{key: [round3(per_bar[number][key]) for number in order] for key in BAR_KEYS},
            "nps": [round3(value) for value in nps],
        },
    }


def clip(value: float) -> float:
    return float(min(max(value, 0.0), 1.0))


def vector_fields(features: dict) -> list:
    notes, span, leaps, octaves = features["notes"], features["span"], features["leaps"], features["octaves"]
    tuplets, runs, tempo = features["tuplets"], features["runs"], features["tempo"]
    bars = max(features["bars"], 1)
    return [
        ("density_mean", notes["mean_per_bar"] / 40.0),
        ("density_p90", notes["p90_per_bar"] / 60.0),
        ("density_max", notes["max_per_bar"] / 120.0),
        ("onsets_mean", notes["onsets_mean_per_bar"] / 30.0),
        ("nps_mean", notes["nps_mean"] / 12.0),
        ("nps_p90", notes["nps_p90"] / 20.0),
        ("nps_peak", notes["nps_peak"] / 35.0),
        ("span_max", span["max"] / 24.0),
        ("span_p95", span["p95"] / 24.0),
        ("span_octave_rate", span["ge_octave"] / bars / 3.0),
        ("span_tenth_rate", span["ge_tenth"] / bars),
        ("window_p95", span["window_p95"] / 36.0),
        ("right_span_max", span["right_max"] / 24.0),
        ("left_span_max", span["left_max"] / 24.0),
        ("leap_max", leaps["max"] / 48.0),
        ("leap_top5", leaps["top5_mean"] / 48.0),
        ("leap_octave_rate", leaps["ge_octave"] / bars / 4.0),
        ("leap_tenth_rate", leaps["ge_tenth"] / bars / 2.0),
        ("octave_rate", octaves["events"] / bars / 8.0),
        ("octave_repeated_rate", octaves["repeated"] / bars / 8.0),
        ("octave_longest", octaves["longest_run"] / 24.0),
        ("octave_fraction", octaves["fraction"]),
        ("tuplet_fraction", tuplets["fraction"]),
        ("tuplet_complex", tuplets["complex_fraction"]),
        ("run_fraction", runs["fraction"]),
        ("run_rate", runs["count"] / bars / 2.0),
        ("run_longest", runs["longest"] / 48.0),
        ("metre_changes", math.log1p(features["metre"]["changes"]) / math.log(8)),
        ("key_changes", math.log1p(features["key"]["changes"]) / math.log(8)),
        ("tempo_changes", math.log1p(tempo["changes"]) / math.log(8)),
        ("tempo_first", tempo["first_bpm"] / 200.0),
        ("tempo_mean", tempo["mean_bpm"] / 200.0),
        ("minutes", math.log1p(features["length"]["minutes"]) / math.log(31)),
        ("bars", math.log1p(features["bars"]) / math.log(1000)),
        ("range", (notes["highest"] - notes["lowest"]) / 88.0),
        ("lowest", notes["lowest"] / 88.0),
        ("highest", notes["highest"] / 88.0),
        ("polyphony_mean", notes["polyphony_mean"] / 6.0),
        ("polyphony_max", notes["polyphony_max"] / 12.0),
        ("left_share", notes["left_share"]),
    ]


VECTOR_NAMES = [name for name, _ in vector_fields(
    {
        "bars": 1, "length": {"minutes": 0}, "metre": {"changes": 0}, "key": {"changes": 0},
        "notes": {"mean_per_bar": 0, "p90_per_bar": 0, "max_per_bar": 0, "onsets_mean_per_bar": 0, "nps_mean": 0, "nps_p90": 0, "nps_peak": 0, "highest": 0, "lowest": 0, "polyphony_mean": 0, "polyphony_max": 0, "left_share": 0},
        "span": {"max": 0, "p95": 0, "ge_octave": 0, "ge_tenth": 0, "window_p95": 0, "right_max": 0, "left_max": 0},
        "leaps": {"max": 0, "top5_mean": 0, "ge_octave": 0, "ge_tenth": 0},
        "octaves": {"events": 0, "repeated": 0, "longest_run": 0, "fraction": 0},
        "tuplets": {"fraction": 0, "complex_fraction": 0},
        "runs": {"fraction": 0, "count": 0, "longest": 0},
        "tempo": {"changes": 0, "first_bpm": 0, "mean_bpm": 0},
    }
)]


def to_vector(features: dict) -> list:
    values = [clip(value) for _, value in vector_fields(features)]
    return [round(value, 5) for value in values] + [0.0] * (VECTOR_DIM - len(values))
