from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Piece, PieceReferenceNotes, PieceSource
from app.services.keyboard_scoring import (
    MAX_REFERENCE_EVENTS,
    MAX_TEMPO,
    MIN_TEMPO,
    PlayedNote,
    RefNote,
    ScoringError,
    group_reference,
    score_timed,
    score_wait,
)

LOWEST_KEY = 21
HIGHEST_KEY = 108
MIN_NOTES = 8
MIN_BARS = 2
CHECK_BARS = 4
WINDOW_BARS = 8
SELF_CHECK_ACCURACY = 0.99


def build_payload(notes: list, bar_starts: dict, bar_lengths: dict, quarter_bpm: float) -> dict:
    ordered = sorted(notes, key=lambda item: (item[0], item[1]))
    return {
        "onsets": [round(float(onset), 4) for onset, _, _ in ordered],
        "midi": [int(midi) for _, midi, _ in ordered],
        "bars": [int(bar) for _, _, bar in ordered],
        "bar_starts": {str(bar): round(float(start), 4) for bar, start in bar_starts.items()},
        "bar_lengths": {str(bar): round(float(length), 4) for bar, length in bar_lengths.items()},
        "quarter_bpm": round(float(quarter_bpm), 2),
    }


def payload_notes(payload: dict) -> list:
    return list(zip(payload["onsets"], payload["midi"], payload["bars"]))


def to_reference(payload: dict, source: str = "harvest"):
    from app.services.keyboard import Reference

    return Reference(
        source=source,
        quarter_bpm=float(payload["quarter_bpm"]),
        notes=[(float(onset), int(midi), int(bar)) for onset, midi, bar in payload_notes(payload)],
        bar_starts={int(bar): float(start) for bar, start in payload["bar_starts"].items()},
        bar_lengths={int(bar): float(length) for bar, length in payload["bar_lengths"].items()},
    )


def structure_issues(payload: dict) -> list:
    issues: list = []
    try:
        onsets, midi, bars = payload["onsets"], payload["midi"], payload["bars"]
        starts = {int(bar): float(value) for bar, value in payload["bar_starts"].items()}
        lengths = {int(bar): float(value) for bar, value in payload["bar_lengths"].items()}
        tempo = float(payload["quarter_bpm"])
    except (KeyError, TypeError, ValueError):
        return ["the note data is incomplete or malformed"]
    if not (len(onsets) == len(midi) == len(bars)):
        return ["the note, onset and bar lists differ in length"]
    if len(onsets) < MIN_NOTES:
        issues.append(f"fewer than {MIN_NOTES} notes")
    if len(set(bars)) < MIN_BARS:
        issues.append(f"fewer than {MIN_BARS} bars")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in onsets):
        issues.append("an onset is negative or not a number")
    if any(not isinstance(value, int) or not LOWEST_KEY <= value <= HIGHEST_KEY for value in midi):
        issues.append(f"a note lies outside the piano's range ({LOWEST_KEY} to {HIGHEST_KEY})")
    if any(later < earlier for earlier, later in zip(onsets, onsets[1:])):
        issues.append("onsets are not in time order")
    if any(later < earlier for earlier, later in zip(bars, bars[1:])):
        issues.append("bar numbers go backwards")
    if not MIN_TEMPO <= tempo <= MAX_TEMPO:
        issues.append(f"the tempo is outside {MIN_TEMPO} to {MAX_TEMPO} bpm")
    missing = {bar for bar in set(bars) if bar not in starts or lengths.get(bar, 0) <= 0}
    if missing:
        issues.append(f"{len(missing)} bar(s) have no start or length")
    else:
        for onset, bar in zip(onsets, bars):
            if onset < starts[bar] - 0.05 or onset > starts[bar] + lengths[bar] + 0.05:
                issues.append("a note lies outside its bar")
                break
    return issues


def density_issues(payload: dict) -> list:
    events = group_reference([RefNote(onset, midi, bar) for onset, midi, bar in payload_notes(payload)])
    per_bar: dict = {}
    for event in events:
        per_bar[event.bar] = per_bar.get(event.bar, 0) + 1
    ordered = sorted(per_bar)
    for index in range(len(ordered)):
        window = [bar for bar in ordered[index : index + WINDOW_BARS] if bar < ordered[index] + WINDOW_BARS]
        if sum(per_bar[bar] for bar in window) > MAX_REFERENCE_EVENTS:
            return [f"{WINDOW_BARS} bars from bar {ordered[index]} hold more than {MAX_REFERENCE_EVENTS} chords, too many to score"]
    return []


def self_check_issues(payload: dict) -> list:
    reference = to_reference(payload)
    bars = reference.bars
    if not bars:
        return ["no bars to check"]
    start = bars[0]
    end = bars[min(CHECK_BARS, len(bars)) - 1]
    notes = reference.slice(start, end)
    if not notes:
        return ["the first bars hold no notes"]
    tempo = int(min(max(round(reference.quarter_bpm), MIN_TEMPO), MAX_TEMPO))
    beat_ms = 60000.0 / tempo
    played = [PlayedNote(note.onset * beat_ms, note.midi) for note in notes]
    try:
        timed = score_timed(notes, played, tempo)
        waited = score_wait(notes, played)
    except ScoringError as error:
        return [f"the scoring engine refused the notes: {error}"]
    problems = []
    if timed.expected == 0 or timed.correct != timed.expected or (timed.accuracy or 0) < SELF_CHECK_ACCURACY:
        problems.append("playing the notes perfectly does not score as perfect in timed mode")
    if waited.expected == 0 or waited.correct != waited.expected:
        problems.append("playing the notes perfectly does not score as perfect in wait mode")
    return problems


def validate(payload: dict) -> list:
    issues = structure_issues(payload)
    if issues:
        return issues
    return density_issues(payload) + self_check_issues(payload)


async def store(session: AsyncSession, piece: Piece, record: PieceSource, payload: dict) -> list:
    issues = validate(payload)
    existing = await session.get(PieceReferenceNotes, piece.id)
    if existing is None:
        existing = PieceReferenceNotes(piece_id=piece.id)
        session.add(existing)
    existing.quarter_bpm = payload["quarter_bpm"]
    existing.note_count = len(payload["midi"])
    existing.bar_count = len(set(payload["bars"]))
    existing.notes = {"onsets": payload["onsets"], "midi": payload["midi"], "bars": payload["bars"]}
    existing.bar_starts = payload["bar_starts"]
    existing.bar_lengths = payload["bar_lengths"]
    record.scoring_ready = not issues
    record.scoring_issues = {"issues": issues} if issues else None
    return issues


async def load_reference(session: AsyncSession, piece_id: int):
    stmt = (
        select(PieceReferenceNotes)
        .join(PieceSource, PieceSource.piece_id == PieceReferenceNotes.piece_id)
        .where(PieceReferenceNotes.piece_id == piece_id, PieceSource.scoring_ready.is_(True))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    payload = {**row.notes, "bar_starts": row.bar_starts, "bar_lengths": row.bar_lengths, "quarter_bpm": float(row.quarter_bpm)}
    return to_reference(payload)
