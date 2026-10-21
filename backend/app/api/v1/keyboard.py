import asyncio
import uuid
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, SessionDep, StorageDep
from app.core.plans import Plan
from app.core.rate_limit import enforce
from app.core.storage import FileTooLarge, QuotaExceeded, UnsupportedMediaType
from app.schemas.keyboard import (
    AttachedOut,
    AttemptIn,
    AttemptOut,
    BarOut,
    HeatOut,
    LadderOut,
    PassagePick,
    ReferenceNotesOut,
    ReferenceOut,
)
from app.services.billing import PlanService
from app.services.keyboard import (
    NO_REFERENCE_MESSAGE,
    KeyboardService,
    ReferenceService,
    counted_seconds,
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
    return await summary(service, user, entry)


async def summary(service: ReferenceService, user, entry) -> ReferenceOut:
    reference = await service.for_entry(user, entry.id)
    track = await service.track(entry.id)
    attached = AttachedOut(filename=track.filename, source=track.source_kind, created_at=track.created_at) if track is not None else None
    passages = [PassagePick(**item) for item in await service.passages(entry, reference)]
    if reference is None:
        return ReferenceOut(available=False, piece_id=entry.piece_id, attached=attached, target_tempo_bpm=target_tempo_for(entry, None), passages=[], message=NO_REFERENCE_MESSAGE)
    return ReferenceOut(
        available=True,
        piece_id=entry.piece_id,
        attached=attached,
        source=reference.source,
        first_bar=reference.first_bar,
        last_bar=reference.last_bar,
        quarter_bpm=reference.quarter_bpm,
        beats_per_bar=reference.beats_per_bar,
        note_count=len(reference.notes),
        target_tempo_bpm=target_tempo_for(entry, reference),
        passages=passages,
    )


@router.post("/entries/{entry_id}/reference", response_model=ReferenceOut, status_code=status.HTTP_201_CREATED)
async def attach_reference(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep, file: UploadFile = File(...)) -> ReferenceOut:
    await enforce("upload", str(user.id))
    service = ReferenceService(session, storage)
    entry = await load_entry(service, user, entry_id)
    try:
        await service.attach(user, entry, file.filename or "", file.file)
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except (FileTooLarge, QuotaExceeded) as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return await summary(service, user, entry)


@router.delete("/entries/{entry_id}/reference", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def detach_reference(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep) -> Response:
    service = ReferenceService(session, storage)
    await load_entry(service, user, entry_id)
    if not await service.detach(entry_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no reference file is attached to this piece")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    plan = await PlanService(session).plan_for(user.id)
    state = await KeyboardService(session).ladder(entry, mode, None if mode == "free" else start_bar, None if mode == "free" else end_bar, reference, plan)
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
    count_in_sec = payload.count_in_beats * 60.0 / payload.tempo_bpm if payload.tempo_bpm else 0.0
    attempt = await keyboard.record(
        user,
        entry,
        score,
        passage_id=payload.passage_id if await passage_belongs(session, payload.passage_id, entry) else None,
        start_bar=start_bar,
        end_bar=end_bar,
        duration_sec=counted_seconds(played, payload.duration_sec, count_in_sec),
    )
    plan = await PlanService(session).plan_for(user.id)
    state = await keyboard.ladder(entry, payload.mode, start_bar, end_bar, reference, plan) if score.tempo_bpm is not None else None
    fed = await keyboard.feed(user, entry, attempt, score, state, reference)
    return attempt_out(attempt, score, state, fed)


@router.get("/entries/{entry_id}/attempts", response_model=list[AttemptOut])
async def recent_attempts(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[AttemptOut]:
    await load_entry(ReferenceService(session, storage), user, entry_id)
    plan = await PlanService(session).plan_for(user.id)
    attempts = await KeyboardService(session).recent(entry_id, plan, limit)
    return [stored_attempt_out(attempt) for attempt in attempts]


@router.get("/entries/{entry_id}/heat", response_model=HeatOut)
async def heat(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    start_bar: int = Query(ge=0),
    end_bar: int = Query(ge=0),
) -> HeatOut:
    await load_entry(ReferenceService(session, storage), user, entry_id)
    if end_bar < start_bar:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the last bar can't come before the first")
    plan = await PlanService(session).plan_for(user.id)
    return HeatOut(**await KeyboardService(session).heat(entry_id, start_bar, end_bar, plan))


async def passage_belongs(session, passage_id: Optional[int], entry) -> bool:
    if passage_id is None:
        return False
    from sqlalchemy import select

    from app.models.models import Passage

    found = await session.execute(select(Passage.id).where(Passage.id == passage_id, Passage.piece_id == entry.piece_id))
    return found.first() is not None


def stored_attempt_out(attempt) -> AttemptOut:
    free = attempt.mode == "free"
    return AttemptOut(
        id=attempt.id,
        created_at=attempt.created_at,
        mode=attempt.mode,
        passage_id=attempt.passage_id,
        start_bar=attempt.start_bar,
        end_bar=attempt.end_bar,
        tempo_bpm=attempt.tempo_bpm,
        achieved_tempo_bpm=float(attempt.achieved_tempo_bpm) if attempt.achieved_tempo_bpm is not None else None,
        expected=attempt.expected,
        correct=attempt.correct,
        wrong=attempt.wrong,
        missing=attempt.missing,
        played=attempt.played,
        accuracy=float(attempt.accuracy) if attempt.accuracy is not None else None,
        timing=float(attempt.timing) if attempt.timing is not None else None,
        evenness=float(attempt.evenness) if attempt.evenness is not None else None,
        overall=float(attempt.overall),
        clean=attempt.clean,
        late=attempt.late,
        early=attempt.early,
        duration_sec=float(attempt.duration_sec or 0),
        bars=[
            BarOut(
                bar=row.bar,
                expected=row.expected,
                correct=row.correct,
                wrong=row.wrong,
                missing=row.missing,
                accuracy=float(row.accuracy) if row.accuracy is not None else None,
                tempo_bpm=float(row.tempo_bpm) if row.tempo_bpm is not None else None,
                timing_error_ms=float(row.timing_error_ms) if row.timing_error_ms is not None else None,
                timing_score=float(row.timing_score) if row.timing_score is not None else None,
                late=row.late,
                early=row.early,
            )
            for row in attempt.bars
        ],
        session_id=attempt.session_id,
        note_checking=not free,
    )


def attempt_out(attempt, score, state, fed=None) -> AttemptOut:
    fed = fed or {}
    data = asdict(score)
    data.pop("bars")
    return AttemptOut(
        **data,
        session_id=fed.get("session_id"),
        session_minutes=fed.get("session_minutes"),
        xp_awarded=fed.get("xp_awarded", 0),
        next_review_at=fed.get("next_review_at"),
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
