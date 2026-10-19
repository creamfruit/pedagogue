from __future__ import annotations

import asyncio
import uuid
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.storage import Storage, storage as default_storage
from app.models.models import (
    KeyboardAttempt,
    KeyboardAttemptBar,
    Passage,
    PdfSubmission,
    RepertoireEntry,
    User,
)
from app.services.keyboard_scoring import (
    DEFAULT_TARGET_TEMPO,
    AttemptScore,
    LadderState,
    PlayedNote,
    RefNote,
    ladder_state,
)
from app.services.onboarding import BaseService

DIGITAL_SUFFIXES = {".musicxml": ".musicxml", ".xml": ".xml", ".mxl": ".mxl", ".mid": ".mid", ".midi": ".midi", ".kar": ".mid"}
REFERENCE_CACHE_SIZE = 8
HISTORY_LENGTH = 12

NO_REFERENCE_MESSAGE = (
    "Note checking isn't available for this piece because it has no MusicXML or MIDI reference. "
    "Upload a MusicXML or MIDI score, or attach a MIDI file, to turn it on. Free play still records "
    "how evenly you play against the metronome."
)


@dataclass
class Reference:
    source: str
    quarter_bpm: float
    notes: list = field(default_factory=list)
    bar_starts: dict = field(default_factory=dict)
    bar_lengths: dict = field(default_factory=dict)

    @property
    def bars(self) -> list:
        return sorted({bar for _, _, bar in self.notes})

    @property
    def first_bar(self) -> Optional[int]:
        bars = self.bars
        return bars[0] if bars else None

    @property
    def last_bar(self) -> Optional[int]:
        bars = self.bars
        return bars[-1] if bars else None

    @property
    def beats_per_bar(self) -> int:
        lengths = Counter(round(length) for length in self.bar_lengths.values() if length >= 1.0)
        if not lengths:
            return 4
        return min(max(lengths.most_common(1)[0][0], 1), 16)

    def slice(self, start: int, end: int) -> list:
        chosen = [(onset, midi, bar) for onset, midi, bar in self.notes if start <= bar <= end]
        if not chosen:
            return []
        origin = self.bar_starts.get(start, min(onset for onset, _, _ in chosen))
        return [RefNote(onset - origin, midi, bar) for onset, midi, bar in chosen]


def reference_from_parsed(parsed, source: str) -> Reference:
    return Reference(
        source=source,
        quarter_bpm=float(parsed.quarter_bpm),
        notes=[(float(event.onset), int(event.midi), int(event.measure)) for event in parsed.events],
        bar_starts={int(number): float(start) for number, start in parsed.measure_starts.items()},
        bar_lengths={int(number): float(length) for number, length in parsed.measure_lengths.items()},
    )


_cache: "OrderedDict[str, Reference]" = OrderedDict()


def remember(key: str, reference: Reference) -> Reference:
    _cache[key] = reference
    _cache.move_to_end(key)
    while len(_cache) > REFERENCE_CACHE_SIZE:
        _cache.popitem(last=False)
    return reference


def forget(key: str) -> None:
    _cache.pop(key, None)


def source_of(suffix: str) -> str:
    return "midi" if suffix in {".mid", ".midi"} else "musicxml"


def parse_reference(data: bytes, suffix: str) -> Reference:
    from app.services.score_analysis import parse_score

    return reference_from_parsed(parse_score(data, DIGITAL_SUFFIXES[suffix]), source_of(DIGITAL_SUFFIXES[suffix]))


def suffix_of(key: str) -> str:
    return "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""


class ReferenceService(BaseService):
    def __init__(self, session, storage: Optional[Storage] = None) -> None:
        super().__init__(session)
        self.storage = storage or default_storage

    async def entry(self, user: User, entry_id: uuid.UUID) -> RepertoireEntry:
        stmt = (
            select(RepertoireEntry)
            .options(selectinload(RepertoireEntry.piece))
            .where(RepertoireEntry.id == entry_id, RepertoireEntry.user_id == user.id)
        )
        entry = (await self.session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            raise LookupError("repertoire entry not found")
        return entry

    async def for_entry(self, user: User, entry_id: uuid.UUID) -> Optional[Reference]:
        stmt = (
            select(PdfSubmission)
            .join(RepertoireEntry, RepertoireEntry.id == PdfSubmission.repertoire_entry_id)
            .where(RepertoireEntry.id == entry_id, RepertoireEntry.user_id == user.id)
            .order_by(PdfSubmission.created_at.desc())
        )
        for submission in (await self.session.execute(stmt)).scalars().all():
            key = submission.storage_key
            if suffix_of(key) not in DIGITAL_SUFFIXES:
                continue
            if key in _cache:
                _cache.move_to_end(key)
                return _cache[key]
            if not self.storage.exists(key):
                continue
            with self.storage.open(key) as handle:
                data = handle.read()
            try:
                reference = await asyncio.to_thread(parse_reference, data, suffix_of(key))
            except Exception:
                continue
            if reference.notes:
                return remember(key, reference)
        return None

    async def passages(self, entry: RepertoireEntry, reference: Optional[Reference]) -> list:
        stmt = select(Passage).where(Passage.piece_id == entry.piece_id).order_by(Passage.difficulty_score.desc().nulls_last(), Passage.start_measure)
        rows = (await self.session.execute(stmt)).scalars().all()
        picks = []
        for passage in rows[:12]:
            if reference is not None and (passage.start_measure < (reference.first_bar or 0) or passage.end_measure > (reference.last_bar or 0)):
                continue
            picks.append({"id": passage.id, "label": passage.label or passage.measure_span, "start_bar": passage.start_measure, "end_bar": passage.end_measure})
        return picks


def target_tempo_for(entry: RepertoireEntry, reference: Optional[Reference]) -> int:
    if entry.target_tempo_bpm:
        return int(entry.target_tempo_bpm)
    if reference is not None and reference.quarter_bpm:
        return int(round(min(max(reference.quarter_bpm, 30), 240)))
    return DEFAULT_TARGET_TEMPO


def to_decimal(value, places: int = 1) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(round(float(value), places)))


class KeyboardService(BaseService):
    async def history(self, entry_id: uuid.UUID, mode: str, start_bar: Optional[int], end_bar: Optional[int], limit: int = HISTORY_LENGTH) -> list:
        stmt = select(KeyboardAttempt.tempo_bpm, KeyboardAttempt.clean).where(
            KeyboardAttempt.repertoire_entry_id == entry_id,
            KeyboardAttempt.mode == mode,
            KeyboardAttempt.start_bar.is_(None) if start_bar is None else KeyboardAttempt.start_bar == start_bar,
            KeyboardAttempt.end_bar.is_(None) if end_bar is None else KeyboardAttempt.end_bar == end_bar,
        ).order_by(KeyboardAttempt.created_at.desc()).limit(limit)
        return [(int(tempo), bool(clean)) for tempo, clean in (await self.session.execute(stmt)).all() if tempo is not None]

    async def ladder(self, entry: RepertoireEntry, mode: str, start_bar: Optional[int], end_bar: Optional[int], reference: Optional[Reference]) -> LadderState:
        history = await self.history(entry.id, "free" if mode == "free" else mode, start_bar, end_bar)
        return ladder_state(history, target_tempo_for(entry, reference))

    async def record(
        self,
        user: User,
        entry: RepertoireEntry,
        score: AttemptScore,
        *,
        passage_id: Optional[int],
        start_bar: Optional[int],
        end_bar: Optional[int],
        duration_sec: float,
    ) -> KeyboardAttempt:
        attempt = KeyboardAttempt(
            user_id=user.id,
            repertoire_entry_id=entry.id,
            passage_id=passage_id,
            mode=score.mode,
            start_bar=start_bar,
            end_bar=end_bar,
            tempo_bpm=score.tempo_bpm,
            achieved_tempo_bpm=to_decimal(score.achieved_tempo_bpm),
            expected=score.expected,
            correct=score.correct,
            wrong=score.wrong,
            missing=score.missing,
            played=score.played,
            accuracy=to_decimal(score.accuracy, 4),
            timing=to_decimal(score.timing),
            evenness=to_decimal(score.evenness),
            overall=to_decimal(score.overall) or Decimal("0"),
            clean=score.clean,
            late=score.late,
            early=score.early,
            duration_sec=to_decimal(duration_sec) or Decimal("0"),
            bars=[
                KeyboardAttemptBar(
                    bar=item.bar,
                    expected=item.expected,
                    correct=item.correct,
                    wrong=item.wrong,
                    missing=item.missing,
                    accuracy=to_decimal(item.accuracy, 4),
                    tempo_bpm=to_decimal(item.tempo_bpm),
                    timing_error_ms=to_decimal(item.timing_error_ms),
                    timing_score=to_decimal(item.timing_score),
                    late=item.late,
                    early=item.early,
                )
                for item in score.bars
            ],
        )
        self.session.add(attempt)
        await self.session.flush()
        await self.session.refresh(attempt, ["created_at"])
        return attempt


def played_notes(payload) -> list:
    return [PlayedNote(float(note.t), int(note.midi)) for note in payload]
