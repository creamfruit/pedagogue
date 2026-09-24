import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.schemas import (
    PerformanceCreate,
    PerformanceReadiness,
    PerformanceRead,
    PerformanceUpdate,
    ProgramSet,
    ReadinessOutcome,
    ReadinessScoreRead,
)
from app.services.performance import PerformanceService, ReadinessScorer

router = APIRouter(tags=["performance"])


@router.get("/performances", response_model=list[PerformanceRead])
async def list_performances(
    user: CurrentUser, session: SessionDep, upcoming: bool = Query(default=False)
) -> list[PerformanceRead]:
    performances = await PerformanceService(session).list(user, upcoming_only=upcoming)
    return [PerformanceRead.model_validate(p) for p in performances]


@router.post("/performances", response_model=PerformanceRead, status_code=status.HTTP_201_CREATED)
async def create_performance(
    payload: PerformanceCreate, user: CurrentUser, session: SessionDep
) -> PerformanceRead:
    performance = await PerformanceService(session).create(
        user, payload.title, payload.event_date, payload.venue
    )
    return PerformanceRead.model_validate(performance)


@router.get("/performances/{performance_id}", response_model=PerformanceRead)
async def get_performance(
    performance_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PerformanceRead:
    try:
        performance = await PerformanceService(session).get(user, performance_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PerformanceRead.model_validate(performance)


@router.patch("/performances/{performance_id}", response_model=PerformanceRead)
async def update_performance(
    performance_id: uuid.UUID,
    payload: PerformanceUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> PerformanceRead:
    try:
        performance = await PerformanceService(session).update(
            user, performance_id, payload.model_dump(exclude_unset=True)
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PerformanceRead.model_validate(performance)


@router.delete("/performances/{performance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_performance(
    performance_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    try:
        await PerformanceService(session).delete(user, performance_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/performances/{performance_id}/program", response_model=PerformanceRead)
async def set_program(
    performance_id: uuid.UUID, payload: ProgramSet, user: CurrentUser, session: SessionDep
) -> PerformanceRead:
    try:
        performance = await PerformanceService(session).set_program(
            user, performance_id, payload.repertoire_entry_ids
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PerformanceRead.model_validate(performance)


@router.get("/performances/{performance_id}/readiness", response_model=PerformanceReadiness)
async def performance_readiness(
    performance_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PerformanceReadiness:
    try:
        report = await PerformanceService(session).readiness_report(user, performance_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PerformanceReadiness(**report)


@router.post(
    "/repertoire/{entry_id}/readiness", response_model=ReadinessOutcome, status_code=status.HTTP_201_CREATED
)
async def score_readiness(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ReadinessOutcome:
    scorer = ReadinessScorer(session)
    try:
        score = await scorer.score_entry(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return ReadinessOutcome.model_validate(score)


@router.get("/repertoire/{entry_id}/readiness", response_model=list[ReadinessScoreRead])
async def readiness_history(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[ReadinessScoreRead]:
    scores = await ReadinessScorer(session).history(user, entry_id)
    return [ReadinessScoreRead.model_validate(s) for s in scores]
