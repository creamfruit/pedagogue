import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.models.models import RepertoireStatus
from app.schemas.schemas import (
    GradingGate,
    PageMeta,
    RepertoireEntryCreate,
    RepertoireEntryRead,
    RepertoireEntryUpdate,
    RepertoirePage,
    RepertoireStats,
)
from app.services.repertoire import RepertoireService

router = APIRouter(prefix="/repertoire", tags=["repertoire"])


@router.get("", response_model=RepertoirePage)
async def list_repertoire(
    user: CurrentUser,
    session: SessionDep,
    status_filter: Optional[RepertoireStatus] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=100),
    top_ten: bool = Query(default=False),
    genre_id: Optional[int] = Query(default=None),
    composer_id: Optional[int] = Query(default=None),
    min_difficulty: Optional[Decimal] = Query(default=None, ge=0, le=100),
    max_difficulty: Optional[Decimal] = Query(default=None, ge=0, le=100),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RepertoirePage:
    entries, meta = await RepertoireService(session).list(
        user,
        status=status_filter,
        query=q,
        top_ten_only=top_ten,
        genre_id=genre_id,
        composer_id=composer_id,
        min_difficulty=min_difficulty,
        max_difficulty=max_difficulty,
        limit=limit,
        offset=offset,
    )
    return RepertoirePage(
        meta=meta, items=[RepertoireEntryRead.model_validate(entry) for entry in entries]
    )


@router.get("/stats", response_model=RepertoireStats)
async def repertoire_stats(user: CurrentUser, session: SessionDep) -> RepertoireStats:
    return await RepertoireService(session).stats(user)


@router.post("", response_model=RepertoireEntryRead, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: RepertoireEntryCreate, user: CurrentUser, session: SessionDep
) -> RepertoireEntryRead:
    service = RepertoireService(session)
    try:
        entry = await service.create(user, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return RepertoireEntryRead.model_validate(entry)


@router.get("/{entry_id}", response_model=RepertoireEntryRead)
async def get_entry(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RepertoireEntryRead:
    try:
        entry = await RepertoireService(session).get(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return RepertoireEntryRead.model_validate(entry)


@router.get("/{entry_id}/gate", response_model=GradingGate)
async def grading_gate(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> GradingGate:
    service = RepertoireService(session)
    try:
        entry = await service.get(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return GradingGate(**await service.gate(entry))


@router.patch("/{entry_id}", response_model=RepertoireEntryRead)
async def update_entry(
    entry_id: uuid.UUID, payload: RepertoireEntryUpdate, user: CurrentUser, session: SessionDep
) -> RepertoireEntryRead:
    try:
        entry = await RepertoireService(session).update(user, entry_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc))
    return RepertoireEntryRead.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    try:
        await RepertoireService(session).delete(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{entry_id}/maintenance-run", response_model=RepertoireEntryRead)
async def maintenance_run(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RepertoireEntryRead:
    try:
        entry = await RepertoireService(session).maintenance_run(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return RepertoireEntryRead.model_validate(entry)
