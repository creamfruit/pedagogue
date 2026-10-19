from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

CHORD_WINDOW_MS = 40.0
REFERENCE_CHORD_QUARTERS = 1.0 / 32.0
MAX_REFERENCE_EVENTS = 800
MAX_PLAYED_NOTES = 3000
MIN_TEMPO = 20
MAX_TEMPO = 400
TIME_WEIGHT = 0.3
GAP_COST = 1.0

CLEAN_ACCURACY = 0.95
CLEAN_TIMING = 75.0
CLEAN_EVENNESS = 65.0
EVENNESS_SIGMA = 0.30
FREE_EVENNESS_SIGMA = 0.20

SCORED_WEIGHTS = {"accuracy": 0.5, "timing": 0.3, "evenness": 0.2}
FREE_WEIGHTS = {"timing": 0.6, "evenness": 0.4}

LADDER_CLEAN_RUNS = 2
LADDER_STEP_PCT = 0.05
LADDER_MIN_STEP = 2
LADDER_START_RATIO = 0.6
DEFAULT_TARGET_TEMPO = 100
SUBDIVISIONS = (1, 2, 3, 4)


class ScoringError(ValueError):
    pass


@dataclass(frozen=True)
class RefNote:
    onset: float
    midi: int
    bar: int


@dataclass(frozen=True)
class PlayedNote:
    time_ms: float
    midi: int


@dataclass
class RefEvent:
    onset: float
    bar: int
    pitches: frozenset


@dataclass
class PlayedEvent:
    time_ms: float
    pitches: frozenset


@dataclass
class BarResult:
    bar: int
    expected: int = 0
    correct: int = 0
    wrong: int = 0
    missing: int = 0
    accuracy: Optional[float] = None
    tempo_bpm: Optional[float] = None
    timing_error_ms: Optional[float] = None
    timing_score: Optional[float] = None
    late: int = 0
    early: int = 0


@dataclass
class AttemptScore:
    mode: str
    tempo_bpm: Optional[int]
    expected: int = 0
    correct: int = 0
    wrong: int = 0
    missing: int = 0
    played: int = 0
    accuracy: Optional[float] = None
    timing: Optional[float] = None
    evenness: Optional[float] = None
    overall: float = 0.0
    clean: bool = False
    achieved_tempo_bpm: Optional[float] = None
    late: int = 0
    early: int = 0
    bars: list = field(default_factory=list)


@dataclass
class LadderState:
    recommended_tempo: int
    current_tempo: Optional[int]
    clean_streak: int
    runs_needed: int
    target_tempo: int
    raised: bool
    reached_target: bool


def group_reference(notes: Sequence[RefNote]) -> list:
    events: list[RefEvent] = []
    for note in sorted(notes, key=lambda item: (item.onset, item.midi)):
        if events and note.onset - events[-1].onset <= REFERENCE_CHORD_QUARTERS:
            events[-1].pitches = events[-1].pitches | {note.midi}
        else:
            events.append(RefEvent(note.onset, note.bar, frozenset({note.midi})))
    return events


def group_played(notes: Sequence[PlayedNote], latency_ms: float = 0.0, window_ms: float = CHORD_WINDOW_MS) -> list:
    ordered = sorted((note.time_ms - latency_ms, note.midi) for note in notes)
    clusters: list[tuple[float, list]] = []
    for time_ms, midi in ordered:
        if clusters and time_ms - clusters[-1][0] <= window_ms:
            clusters[-1][1].append((time_ms, midi))
        else:
            clusters.append((time_ms, [(time_ms, midi)]))
    return [
        PlayedEvent(sum(time for time, _ in members) / len(members), frozenset(midi for _, midi in members))
        for _, members in clusters
    ]


def timing_credit(error_ms: float, beat_ms: float) -> float:
    tolerance = max(45.0, 0.10 * beat_ms)
    failure = max(180.0, 0.5 * beat_ms)
    miss = abs(error_ms)
    if miss <= tolerance:
        return 1.0
    if miss >= failure:
        return 0.0
    return 1.0 - (miss - tolerance) / (failure - tolerance)


def timing_tolerance(beat_ms: float) -> float:
    return max(45.0, 0.10 * beat_ms)


def grid_tolerance(step_ms: float) -> float:
    return min(40.0, 0.10 * step_ms)


def grid_credit(error_ms: float, step_ms: float) -> float:
    tolerance = grid_tolerance(step_ms)
    limit = 0.30 * step_ms
    miss = abs(error_ms)
    if miss <= tolerance:
        return 1.0
    if miss >= limit:
        return 0.0
    return 1.0 - (miss - tolerance) / (limit - tolerance)


def evenness_from_ratios(ratios: Sequence[float], sigma_limit: float) -> Optional[float]:
    usable = [value for value in ratios if value > 0 and math.isfinite(value)]
    if len(usable) < 3:
        return None
    logs = [math.log(value) for value in usable]
    mean = sum(logs) / len(logs)
    sigma = math.sqrt(sum((value - mean) ** 2 for value in logs) / len(logs))
    return round(100.0 * min(max(1.0 - sigma / sigma_limit, 0.0), 1.0), 1)


def pitch_matrix(events: Sequence) -> np.ndarray:
    matrix = np.zeros((len(events), 128), dtype=np.float64)
    for row, event in enumerate(events):
        for midi in event.pitches:
            if 0 <= midi < 128:
                matrix[row, midi] = 1.0
    return matrix


def align(reference: Sequence[RefEvent], played: Sequence[PlayedEvent], beat_ms: Optional[float]) -> list:
    n, m = len(reference), len(played)
    if n == 0 or m == 0:
        return []
    ref_matrix, played_matrix = pitch_matrix(reference), pitch_matrix(played)
    shared = ref_matrix @ played_matrix.T
    union = ref_matrix.sum(axis=1)[:, None] + played_matrix.sum(axis=1)[None, :] - shared
    cost = 1.0 - shared / np.maximum(union, 1.0)
    if beat_ms:
        expected = np.array([event.onset for event in reference]) * beat_ms
        actual = np.array([event.time_ms for event in played])
        cost = cost + TIME_WEIGHT * np.clip(np.abs(actual[None, :] - expected[:, None]) / (2.0 * beat_ms), 0.0, 1.0)
    offsets = np.arange(m + 1) * GAP_COST
    table = np.zeros((n + 1, m + 1))
    table[0] = offsets
    for i in range(1, n + 1):
        row = np.empty(m + 1)
        row[0] = table[i - 1, 0] + GAP_COST
        row[1:] = np.minimum(table[i - 1, :-1] + cost[i - 1], table[i - 1, 1:] + GAP_COST)
        table[i] = np.minimum.accumulate(row - offsets) + offsets
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        if abs(table[i, j] - (table[i - 1, j - 1] + cost[i - 1, j - 1])) < 1e-9:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif abs(table[i, j] - (table[i - 1, j] + GAP_COST)) < 1e-9:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def slope_tempo(points: Sequence[tuple]) -> Optional[float]:
    if len(points) < 2:
        return None
    onsets = [point[0] for point in points]
    if max(onsets) - min(onsets) < 0.25:
        return None
    mean_x = sum(onsets) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    variance = sum((x - mean_x) ** 2 for x in onsets)
    if variance <= 0:
        return None
    ms_per_quarter = sum((x - mean_x) * (y - mean_y) for x, y in points) / variance
    if ms_per_quarter <= 0:
        return None
    return round(60000.0 / ms_per_quarter, 1)


def check_tempo(tempo_bpm: float) -> None:
    if not MIN_TEMPO <= tempo_bpm <= MAX_TEMPO:
        raise ScoringError(f"tempo must be between {MIN_TEMPO} and {MAX_TEMPO} bpm")


def check_sizes(played: Sequence, reference: Optional[Sequence] = None) -> None:
    if len(played) > MAX_PLAYED_NOTES:
        raise ScoringError(f"too many notes in one attempt (the limit is {MAX_PLAYED_NOTES})")
    if reference is not None and len(reference) > MAX_REFERENCE_EVENTS:
        raise ScoringError(f"that passage is too long to score in one attempt (the limit is {MAX_REFERENCE_EVENTS} chords or notes)")


def combine(parts: dict, weights: dict) -> float:
    active = {key: value for key, value in parts.items() if value is not None}
    total = sum(weights[key] for key in active)
    if total <= 0:
        return 0.0
    return round(sum(weights[key] * value for key, value in active.items()) / total, 1)


def finish_bars(bars: dict) -> list:
    out = []
    for bar in sorted(bars):
        item = bars[bar]
        item.accuracy = round(item.correct / (item.expected + item.wrong), 4) if item.expected + item.wrong else None
        out.append(item)
    return out


def start_bars(events: Sequence[RefEvent]) -> dict:
    bars: dict[int, BarResult] = {}
    for event in events:
        item = bars.setdefault(event.bar, BarResult(event.bar))
        item.expected += len(event.pitches)
    return bars


def nearest_bar(events: Sequence[RefEvent], time_ms: float, beat_ms: float) -> int:
    return min(events, key=lambda event: abs(event.onset * beat_ms - time_ms)).bar


def score_timed(reference_notes: Sequence[RefNote], played_notes: Sequence[PlayedNote], tempo_bpm: float, latency_ms: float = 0.0) -> AttemptScore:
    check_tempo(tempo_bpm)
    reference = group_reference(reference_notes)
    if not reference:
        raise ScoringError("there are no reference notes to score against")
    check_sizes(played_notes, reference)
    beat_ms = 60000.0 / tempo_bpm
    played = group_played(played_notes, latency_ms)
    pairs = align(reference, played, beat_ms)
    bars = start_bars(reference)
    matched_ref = {i for i, _ in pairs}
    matched_played = {j for _, j in pairs}
    correct = wrong = missing = 0
    bar_points: dict[int, list] = {bar: [] for bar in bars}
    bar_errors: dict[int, list] = {bar: [] for bar in bars}
    bar_credits: dict[int, list] = {bar: [] for bar in bars}
    timed_pairs = []
    tolerance = timing_tolerance(beat_ms)
    for i, j in pairs:
        event, hit = reference[i], played[j]
        shared = len(event.pitches & hit.pitches)
        item = bars[event.bar]
        item.correct += shared
        item.missing += len(event.pitches - hit.pitches)
        item.wrong += len(hit.pitches - event.pitches)
        correct += shared
        missing += len(event.pitches - hit.pitches)
        wrong += len(hit.pitches - event.pitches)
        if shared:
            error = hit.time_ms - event.onset * beat_ms
            timed_pairs.append((event, hit, error))
            bar_points[event.bar].append((event.onset, hit.time_ms))
            bar_errors[event.bar].append(error)
            bar_credits[event.bar].append(timing_credit(error, beat_ms))
            if error > tolerance:
                item.late += 1
            elif error < -tolerance:
                item.early += 1
    for i, event in enumerate(reference):
        if i not in matched_ref:
            bars[event.bar].missing += len(event.pitches)
            missing += len(event.pitches)
    for j, hit in enumerate(played):
        if j not in matched_played:
            bars[nearest_bar(reference, hit.time_ms, beat_ms)].wrong += len(hit.pitches)
            wrong += len(hit.pitches)
    expected = sum(len(event.pitches) for event in reference)
    accuracy = round(correct / (expected + wrong), 4) if expected + wrong else 0.0
    credits = [timing_credit(error, beat_ms) for _, _, error in timed_pairs]
    timing = round(100.0 * sum(credits) / len(credits), 1) if credits else None
    ratios = []
    for (ref_a, hit_a, _), (ref_b, hit_b, _) in zip(timed_pairs, timed_pairs[1:]):
        gap = (ref_b.onset - ref_a.onset) * beat_ms
        if gap >= 30.0:
            ratios.append((hit_b.time_ms - hit_a.time_ms) / gap)
    evenness = evenness_from_ratios(ratios, EVENNESS_SIGMA)
    for bar, item in bars.items():
        item.tempo_bpm = slope_tempo(bar_points[bar])
        if bar_errors[bar]:
            item.timing_error_ms = round(sum(bar_errors[bar]) / len(bar_errors[bar]), 1)
            item.timing_score = round(100.0 * sum(bar_credits[bar]) / len(bar_credits[bar]), 1)
    overall = combine({"accuracy": accuracy * 100.0, "timing": timing, "evenness": evenness}, SCORED_WEIGHTS)
    clean = accuracy >= CLEAN_ACCURACY and (timing is None or timing >= CLEAN_TIMING) and (evenness is None or evenness >= CLEAN_EVENNESS) and missing == 0
    return AttemptScore(
        mode="scored",
        tempo_bpm=int(round(tempo_bpm)),
        expected=expected,
        correct=correct,
        wrong=wrong,
        missing=missing,
        played=len(played_notes),
        accuracy=accuracy,
        timing=timing,
        evenness=evenness,
        overall=overall,
        clean=bool(clean),
        achieved_tempo_bpm=slope_tempo([(event.onset, hit.time_ms) for event, hit, _ in timed_pairs]),
        late=sum(item.late for item in bars.values()),
        early=sum(item.early for item in bars.values()),
        bars=finish_bars(bars),
    )


def score_wait(reference_notes: Sequence[RefNote], played_notes: Sequence[PlayedNote]) -> AttemptScore:
    reference = group_reference(reference_notes)
    if not reference:
        raise ScoringError("there are no reference notes to score against")
    check_sizes(played_notes, reference)
    bars = start_bars(reference)
    index = 0
    remaining = set(reference[0].pitches)
    correct = wrong = 0
    for note in sorted(played_notes, key=lambda item: item.time_ms):
        if index >= len(reference):
            break
        item = bars[reference[index].bar]
        if note.midi in remaining:
            remaining.discard(note.midi)
            item.correct += 1
            correct += 1
        else:
            item.wrong += 1
            wrong += 1
        if not remaining:
            index += 1
            remaining = set(reference[index].pitches) if index < len(reference) else set()
    missing = 0
    if index < len(reference):
        for position in range(index, len(reference)):
            event = reference[position]
            left = len(remaining) if position == index else len(event.pitches)
            bars[event.bar].missing += left
            missing += left
    expected = sum(len(event.pitches) for event in reference)
    accuracy = round(correct / (expected + wrong), 4) if expected + wrong else 0.0
    return AttemptScore(
        mode="wait",
        tempo_bpm=None,
        expected=expected,
        correct=correct,
        wrong=wrong,
        missing=missing,
        played=len(played_notes),
        accuracy=accuracy,
        overall=round(accuracy * 100.0, 1),
        clean=accuracy >= CLEAN_ACCURACY and missing == 0,
        bars=finish_bars(bars),
    )


def best_subdivision(times: Sequence[float], beat_ms: float) -> int:
    scored = []
    for subdivision in SUBDIVISIONS:
        step = beat_ms / subdivision
        error = sum(abs(time - round(time / step) * step) for time in times) / len(times) / step
        scored.append((subdivision, error))
    best = min(error for _, error in scored)
    return next(subdivision for subdivision, error in scored if error <= best + 0.03)


def score_free(
    played_notes: Sequence[PlayedNote],
    tempo_bpm: float,
    beats_per_bar: int = 4,
    subdivision: Optional[int] = None,
    latency_ms: float = 0.0,
) -> AttemptScore:
    check_tempo(tempo_bpm)
    check_sizes(played_notes)
    if not 1 <= beats_per_bar <= 16:
        raise ScoringError("beats per bar must be between 1 and 16")
    beat_ms = 60000.0 / tempo_bpm
    events = group_played(played_notes, latency_ms)
    base = AttemptScore(mode="free", tempo_bpm=int(round(tempo_bpm)), played=len(played_notes))
    if len(events) < 2:
        return base
    times = [event.time_ms for event in events]
    chosen = subdivision if subdivision in SUBDIVISIONS else best_subdivision(times, beat_ms)
    step = beat_ms / chosen
    errors = [time - round(time / step) * step for time in times]
    credits = [grid_credit(error, step) for error in errors]
    tolerance = grid_tolerance(step)
    timing = round(100.0 * sum(credits) / len(credits), 1)
    ratios = []
    for first, second in zip(times, times[1:]):
        units = round((second - first) / step)
        if units >= 1:
            ratios.append((second - first) / (units * step))
    evenness = evenness_from_ratios(ratios, FREE_EVENNESS_SIGMA)
    bar_ms = beats_per_bar * beat_ms
    bars: dict[int, BarResult] = {}
    bar_errors: dict[int, list] = {}
    for time, error in zip(times, errors):
        number = int(max(time, 0.0) // bar_ms) + 1
        item = bars.setdefault(number, BarResult(number))
        bar_errors.setdefault(number, []).append(error)
        if error > tolerance:
            item.late += 1
        elif error < -tolerance:
            item.early += 1
    for number, item in bars.items():
        values = bar_errors[number]
        item.timing_error_ms = round(sum(values) / len(values), 1)
        item.timing_score = round(100.0 * sum(grid_credit(value, step) for value in values) / len(values), 1)
    base.timing = timing
    base.evenness = evenness
    base.overall = combine({"timing": timing, "evenness": evenness}, FREE_WEIGHTS)
    base.clean = timing >= CLEAN_TIMING and (evenness is None or evenness >= CLEAN_EVENNESS)
    base.late = sum(item.late for item in bars.values())
    base.early = sum(item.early for item in bars.values())
    base.bars = [bars[number] for number in sorted(bars)]
    return base


def default_start_tempo(target_tempo: int) -> int:
    return int(min(target_tempo, max(40, round(target_tempo * LADDER_START_RATIO / 2) * 2)))


def next_tempo(current: int, target: int) -> int:
    step = max(LADDER_MIN_STEP, round(current * LADDER_STEP_PCT))
    return int(min(target, current + step))


def ladder_state(history: Sequence[tuple], target_tempo: Optional[int], runs_needed: int = LADDER_CLEAN_RUNS) -> LadderState:
    target = int(target_tempo or DEFAULT_TARGET_TEMPO)
    if not history:
        return LadderState(default_start_tempo(target), None, 0, runs_needed, target, False, False)
    current = int(history[0][0])
    streak = 0
    for tempo, clean in history:
        if int(tempo) != current or not clean:
            break
        streak += 1
    reached = current >= target
    raised = streak >= runs_needed and not reached
    recommended = next_tempo(current, target) if raised else current
    return LadderState(recommended, current, streak, runs_needed, target, raised, reached and streak >= runs_needed)


def refreshed_practice_time(previous, now, overall: float):
    if previous is None or overall >= 60.0:
        return now
    return previous + (now - previous) * 0.5
