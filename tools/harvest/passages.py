from typing import Optional

import numpy as np

from app.services.score_analysis import CUES, LABELS, PHRASES

MAX_PASSAGES = 5
MIN_BARS = 2
MAX_BARS = 8
KEEP_RATIO = 0.7
FLOOR = 0.18
MARGIN = 1.15
PLAIN_FLOOR = 0.4

OCTAVES = "Blocked octaves"
LEAPS = "Wide leaps"
RUNS = "Rapid scales"
STRETCHES = "Tenth stretches"
TUPLETS = "Three against two"
ENDURANCE = "Sustained endurance"

WEIGHTS = {"speed": 0.34, "stretch": 0.14, "leap": 0.16, "octave": 0.14, "run": 0.1, "tuplet": 0.05, "density": 0.07}


def bar_signals(per_bar: dict) -> list[dict]:
    rows = []
    for index in range(len(per_bar["numbers"])):
        notes = per_bar["notes"][index]
        rows.append(
            {
                "bar": per_bar["numbers"][index],
                "speed": min(per_bar["nps"][index] / 20.0, 1.4),
                "stretch": min(max(per_bar["span"][index] - 8, 0) / 10.0, 1.2),
                "leap": min(max(per_bar["leap"][index] - 7, 0) / 17.0, 1.2),
                "octave": min(per_bar["octave"][index] / 12.0, 1.2),
                "run": min(per_bar["run"][index] / max(notes, 1) * 1.5, 1.0) if notes else 0.0,
                "tuplet": min(per_bar["tuplet"][index] / max(notes, 1) * 2.0, 1.0) if notes else 0.0,
                "density": min(notes / 60.0, 1.2),
            }
        )
    return rows


def bar_scores(signals: list[dict]) -> np.ndarray:
    return np.array([sum(WEIGHTS[name] * row[name] for name in WEIGHTS) for row in signals])


def technique_intensity(row: dict) -> dict:
    found = {
        OCTAVES: row["octave"],
        LEAPS: row["leap"],
        RUNS: row["run"],
        STRETCHES: row["stretch"],
        TUPLETS: row["tuplet"],
    }
    return {name: min(value, 1.0) for name, value in found.items() if value >= 0.2}


def piece_techniques(signals: list[dict], minutes: float) -> list[tuple[str, float]]:
    names = (OCTAVES, LEAPS, RUNS, STRETCHES, TUPLETS)
    per_name: dict = {name: [] for name in names}
    for row in signals:
        for name, value in technique_intensity(row).items():
            per_name[name].append(value)
    total = max(len(signals), 1)
    weights = []
    for name, values in per_name.items():
        if not values:
            continue
        share = min(len(values) / total * 4.0, 1.0)
        weight = 0.6 * float(np.percentile(values, 90)) + 0.4 * share
        weights.append((name, round(min(weight, 1.0), 2)))
    endurance = min(minutes / 8.0, 1.0) * 0.6 + min(float(np.mean([row["speed"] for row in signals])) / 0.7, 1.0) * 0.4
    if endurance >= 0.45:
        weights.append((ENDURANCE, round(min(endurance, 1.0), 2)))
    return sorted((item for item in weights if item[1] >= 0.15), key=lambda item: -item[1])[:5]


def grow(scores: np.ndarray, peak: int, taken: np.ndarray) -> tuple[int, int]:
    start = end = peak
    threshold = scores[peak] * KEEP_RATIO
    while end - start + 1 < MAX_BARS:
        left = scores[start - 1] if start > 0 and not taken[start - 1] else -1.0
        right = scores[end + 1] if end + 1 < len(scores) and not taken[end + 1] else -1.0
        best = max(left, right)
        if best < threshold:
            break
        if left >= right:
            start -= 1
        else:
            end += 1
    while end - start + 1 < MIN_BARS:
        if end + 1 < len(scores) and not taken[end + 1]:
            end += 1
        elif start > 0 and not taken[start - 1]:
            start -= 1
        else:
            break
    return start, end


def describe(signals: list[dict], start: int, end: int, techniques: dict, peak_nps: float, hardest: int) -> tuple[str, str, str]:
    ranked = sorted(techniques.items(), key=lambda item: -item[1])
    first = bar_label(signals[start]["bar"], signals[end]["bar"])
    if not ranked:
        label = "Busy passage"
        text = f"{first}: the densest writing in the piece, up to about {peak_nps:.0f} notes a second."
        return label, text, "Practise hands separately at half tempo, then join them in short groups."
    names = [PHRASES.get(name, name.lower()) for name, _ in ranked[:2]]
    label = LABELS.get(ranked[0][0], ranked[0][0])
    text = f"{first}: {' and '.join(names)}, peaking around {peak_nps:.0f} notes a second. The hardest bar is {signals[hardest]['bar']}."
    return label, text, CUES.get(ranked[0][0], "Practise hands separately at half tempo, then join them in short groups.")


def bar_label(first: int, last: int) -> str:
    return f"Bar {first}" if first == last else f"Bars {first}–{last}"


def detect(features: dict, *, limit: int = MAX_PASSAGES) -> list[dict]:
    per_bar = features["per_bar"]
    signals = bar_signals(per_bar)
    if len(signals) < MIN_BARS:
        return []
    scores = bar_scores(signals)
    smooth = np.convolve(scores, np.ones(3) / 3.0, mode="same") if len(scores) >= 3 else scores
    median = float(np.median(scores))
    taken = np.zeros(len(scores), dtype=bool)
    found = []
    order = np.argsort(-smooth)
    for index in order:
        if len(found) >= limit:
            break
        if taken[index] or smooth[index] < max(FLOOR, median * MARGIN):
            continue
        start, end = grow(smooth, int(index), taken)
        window = range(start, end + 1)
        if any(taken[i] for i in window):
            continue
        hardest = max(window, key=lambda i: scores[i])
        techniques: dict = {}
        for i in window:
            for name, value in technique_intensity(signals[i]).items():
                techniques[name] = max(techniques.get(name, 0.0), value)
        if not techniques and smooth[index] < PLAIN_FLOOR:
            continue
        peak_nps = max(per_bar["nps"][i] for i in window)
        label, text, cue = describe(signals, start, end, techniques, peak_nps, hardest)
        taken[start : end + 1] = True
        found.append(
            {
                "start": signals[start]["bar"],
                "end": signals[end]["bar"],
                "hardest_bar": signals[hardest]["bar"],
                "label": label,
                "description": text,
                "cue": cue,
                "techniques": {name: round(value, 2) for name, value in techniques.items()},
                "score": round(float(np.max(smooth[start : end + 1])), 3),
            }
        )
    top = max((item["score"] for item in found), default=1.0)
    for item in found:
        item["relative"] = round(item["score"] / top, 3) if top else 1.0
    return sorted(found, key=lambda item: -item["score"])


def hardest_bars(features: dict, count: int = 5) -> list[int]:
    per_bar = features["per_bar"]
    scores = bar_scores(bar_signals(per_bar))
    ranked = np.argsort(-scores)[:count]
    return [int(per_bar["numbers"][index]) for index in ranked]


def passage_difficulty(piece_difficulty: Optional[float], relative: float) -> float:
    base = float(piece_difficulty if piece_difficulty is not None else 50.0) / 10.0
    return round(min(10.0, base * (0.82 + 0.22 * relative)), 1)
