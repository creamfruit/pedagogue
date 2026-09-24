from __future__ import annotations

import random
from typing import Any, Optional

TEMPO_TABLE = {
    "largo": 50.0,
    "lento": 56.0,
    "adagio": 66.0,
    "andante": 84.0,
    "andantino": 92.0,
    "moderato": 104.0,
    "allegretto": 112.0,
    "allegro": 132.0,
    "vivace": 160.0,
    "presto": 180.0,
}


def bpm_from_marking(marking: Optional[str]) -> float:
    if not marking:
        return 100.0
    lowered = marking.lower()
    for key, value in TEMPO_TABLE.items():
        if key in lowered:
            return value
    return 100.0


def reference_curve(piece_id: int, duration_sec: Optional[int], tempo_marking: Optional[str]) -> list[dict]:
    rng = random.Random(piece_id)
    total = duration_sec or 180
    base = bpm_from_marking(tempo_marking)
    steps = max(int(total / 8), 6)
    points = []
    for index in range(steps + 1):
        t = (index / steps) * total
        phrase_phase = (index % 4) / 4
        rubato = 1.0
        if phrase_phase > 0.75:
            rubato = 0.88 - rng.uniform(0.0, 0.05)
        elif 0 < phrase_phase < 0.15:
            rubato = 1.05 + rng.uniform(0.0, 0.04)
        points.append({"t": round(t, 1), "bpm": round(base * rubato, 1)})
    return points


def _interpolate(reference: list[tuple[float, float]], t: float) -> float:
    if t <= reference[0][0]:
        return reference[0][1]
    if t >= reference[-1][0]:
        return reference[-1][1]
    for (t0, b0), (t1, b1) in zip(reference, reference[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return b0
            ratio = (t - t0) / (t1 - t0)
            return b0 + (b1 - b0) * ratio
    return reference[-1][1]


def compare_curves(user_points: list[dict], reference: list[dict]) -> dict[str, Any]:
    reference_pairs = [(p["t"], p["bpm"]) for p in reference if "t" in p and "bpm" in p]
    if not reference_pairs:
        return {"available": False, "reason": "reference curve unavailable"}
    if not user_points:
        return {"available": False, "reason": "no tempo data was captured in this recording"}

    deviations = []
    worst = None
    for point in user_points:
        t = point.get("t")
        bpm = point.get("bpm")
        if t is None or bpm is None:
            continue
        expected = _interpolate(reference_pairs, float(t))
        deviation = float(bpm) - expected
        deviations.append(deviation)
        if worst is None or abs(deviation) > abs(worst["deviation_bpm"]):
            worst = {"t": t, "deviation_bpm": round(deviation, 1)}

    if not deviations:
        return {"available": False, "reason": "the tempo curve had no usable points"}

    mean_abs = sum(abs(d) for d in deviations) / len(deviations)
    mean = sum(deviations) / len(deviations)
    variance = sum((d - mean) ** 2 for d in deviations) / len(deviations)
    match_score = max(0.0, min(100.0, round(100.0 - mean_abs * 2.2, 1)))

    return {
        "available": True,
        "match_score": match_score,
        "mean_absolute_deviation_bpm": round(mean_abs, 1),
        "rubato_variance": round(variance, 1),
        "sample_count": len(deviations),
        "biggest_deviation": worst,
        "reference_curve": reference,
    }
