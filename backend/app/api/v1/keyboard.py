import asyncio
import uuid
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep, StorageDep
from app.core.rate_limit import enforce
from app.schemas.keyboard import (
    AttemptIn,
    AttemptOut,
    LadderOut,
    PassagePick,
    ReferenceNotesOut,
    ReferenceOut,
)
from app.services.keyboard import (
    NO_REFERENCE_MESSAGE,
    KeyboardService,
    ReferenceService,
    played_notes,
    target_tempo_for,
)
from app.services.keyboard_scoring import (
    MAX_REFERENCE_EVENTS,
    ScoringError,
    group_reference,
    score_free,
    score_timed,
    score_wait,
)

router = APIRouter(prefix="/keyboard", tags=["keyboard"])


async def load_entry(service: ReferenceService, user, entry_id: uuid.UUID):
    try:
        return await service.entry(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def check_range(reference, start_bar: int, end_bar: int) -> list:
    if end_bar < start_bar:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the last bar can't come before the first")
    notes = reference.slice(start_bar, end_bar)
    if not notes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"there are no notes in bars {start_bar} to {end_bar}; this piece runs from bar {reference.first_bar} to bar {reference.last_bar}",
        )
    if len(group_reference(notes)) > MAX_REFERENCE_EVENTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="that passage is too long to score at once; choose fewer bars")
    return notes


@router.get("/entries/{entry_id}/reference", response_model=ReferenceOut)
async def reference_summary(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep) -> ReferenceOut:
    service = ReferenceService(session, storage)
    entry = await load_entry(service, user, entry_id)
    reference = await service.for_entry(user, entry_id)
    passages = [PassagePick(**item) for item in await service.passages(entry, reference)]
    if reference is None:
        return ReferenceOut(available=False, target_tempo_bpm=target_tempo_for(entry, None), passages=[], message=NO_REFERENCE_MESSAGE)
    return ReferenceOut(
        available=True,
        source=reference.source,
        first_bar=reference.first_bar,
        last_bar=reference.last_bar,
        quarter_bpm=reference.quarter_bpm,
        beats_per_bar=reference.beats_per_bar,
        note_count=len(reference.notes),
        target_tempo_bpm=target_tempo_for(entry, reference),
        passages=passages,
    )


@router.get("/entries/{entry_id}/reference/notes", response_model=ReferenceNotesOut)
async def reference_notes(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    start_bar: int = Query(ge=0),
    end_bar: int = Query(ge=0),
) -> ReferenceNotesOut:
    service = ReferenceService(session, storage)
    await load_entry(service, user, entry_id)
    reference = await service.for_entry(user, entry_id)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_REFERENCE_MESSAGE)
    notes = check_range(reference, start_bar, end_bar)
    return ReferenceNotesOut(
        start_bar=start_bar,
        end_bar=end_bar,
        quarter_bpm=reference.quarter_bpm,
        beats_per_bar=reference.beats_per_bar,
        bars=sorted({note.bar for note in notes}),
        notes=[[round(note.onset, 4), note.midi, note.bar] for note in sorted(notes, key=lambda item: (item.onset, item.midi))],
    )


@router.get("/entries/{entry_id}/ladder", response_model=LadderOut)
async def ladder(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    mode: Literal["scored", "wait", "free"] = "scored",
    start_bar: Optional[int] = Query(default=None, ge=0),
    end_bar: Optional[int] = Query(default=None, ge=0),
) -> LadderOut:
    service = ReferenceService(session, storage)
    entry = await load_entry(service, user, entry_id)
    reference = await service.for_entry(user, entry_id) if mode != "free" else None
    state = await KeyboardService(session).ladder(entry, mode, None if mode == "free" else start_bar, None if mode == "free" else end_bar, reference)
    return LadderOut(**asdict(state))


@router.post("/entries/{entry_id}/attempts", response_model=AttemptOut, status_code=status.HTTP_201_CREATED)
async def record_attempt(entry_id: uuid.UUID, payload: AttemptIn, user: CurrentUser, session: SessionDep, storage: StorageDep) -> AttemptOut:
    await enforce("keyboard_attempt", str(user.id))
    service = ReferenceService(session, storage)
    entry = await load_entry(service, user, entry_id)
    played = played_notes(payload.notes)
    reference = None
    start_bar, end_bar = payload.start_bar, payload.end_bar
    try:
        if payload.mode == "free":
            start_bar = end_bar = None
            score = await asyncio.to_thread(score_free, played, payload.tempo_bpm, payload.beats_per_bar, None, payload.latency_ms)
        else:
            reference = await service.for_entry(user, entry_id)
            if reference is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_REFERENCE_MESSAGE)
            notes = check_range(reference, start_bar, end_bar)
            if payload.mode == "wait":
                score = await asyncio.to_thread(score_wait, notes, played)
            else:
                score = await asyncio.to_thread(score_timed, notes, played, payload.tempo_bpm, payload.latency_ms)
    except ScoringError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    keyboard = KeyboardService(session)
    attempt = await keyboard.record(
        user,
        entry,
        score,
        passage_id=payload.passage_id if await passage_belongs(session, payload.passage_id, entry) else None,
        start_bar=start_bar,
        end_bar=end_bar,
        duration_sec=payload.duration_sec,
    )
    state = await keyboard.ladder(entry, payload.mode, start_bar, end_bar, reference) if score.tempo_bpm is not None else None
    return attempt_out(attempt, score, state)


async def passage_belongs(session, passage_id: Optional[int], entry) -> bool:
    if passage_id is None:
        return False
    from sqlalchemy import select

    from app.models.models import Passage

    found = await session.execute(select(Passage.id).where(Passage.id == passage_id, Passage.piece_id == entry.piece_id))
    return found.first() is not None


def attempt_out(attempt, score, state) -> AttemptOut:
    data = asdict(score)
    data.pop("bars")
    return AttemptOut(
        **data,
        id=attempt.id,
        created_at=attempt.created_at,
        passage_id=attempt.passage_id,
        start_bar=attempt.start_bar,
        end_bar=attempt.end_bar,
        duration_sec=float(attempt.duration_sec or 0),
        bars=[asdict(item) for item in score.bars],
        ladder=LadderOut(**asdict(state)) if state is not None else None,
        note_checking=score.mode != "free",
        message=None if score.mode != "free" else "Note checking isn't available for free play. This only measures how evenly you play against the metronome.",
    )
