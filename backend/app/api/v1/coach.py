import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.schemas import (
    DrillForgeRequest,
    DrillRead,
    PolyrhythmAttemptRead,
    PolyrhythmRecord,
    PracticePlanRead,
    SightReadingRead,
    SightReadingRequest,
    SightReadingScore,
)
from app.services.coach import DrillForge, PlanBuilder, PolyrhythmTrainer, SightReadingGenerator
from app.services.repertoire import RepertoireService

router = APIRouter(tags=["coach"])


@router.get("/drills", response_model=list[DrillRead])
async def list_drills(user: CurrentUser, session: SessionDep) -> list[DrillRead]:
    drills = await DrillForge(session).list(user)
    return [DrillRead.model_validate(d) for d in drills]


@router.post("/drills/forge", response_model=list[DrillRead], status_code=status.HTTP_201_CREATED)
async def forge_drills(
    payload: DrillForgeRequest, user: CurrentUser, session: SessionDep
) -> list[DrillRead]:
    forge = DrillForge(session)
    try:
        if payload.passage_id is not None:
            created = await forge.forge(user, payload.passage_id, payload.count)
        else:
            created = await forge.forge_from_weaknesses(user, limit=payload.count)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not created:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no new drills to forge, submit a recording or notes to surface weak passages first",
        )
    hydrated = [await forge.get(user, drill.id) for drill in created]
    return [DrillRead.model_validate(d) for d in hydrated]


@router.get("/drills/{drill_id}", response_model=DrillRead)
async def get_drill(drill_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> DrillRead:
    try:
        drill = await DrillForge(session).get(user, drill_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return DrillRead.model_validate(drill)


@router.delete("/drills/{drill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drill(drill_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    try:
        await DrillForge(session).delete(user, drill_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/repertoire/{entry_id}/plans", response_model=PracticePlanRead, status_code=status.HTTP_201_CREATED
)
async def build_plan(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PracticePlanRead:
    try:
        entry = await RepertoireService(session).get(user, entry_id)
        plan = await PlanBuilder(session).build(user, entry)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PracticePlanRead.model_validate(plan)


@router.get("/repertoire/{entry_id}/plans", response_model=list[PracticePlanRead])
async def list_plans(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[PracticePlanRead]:
    plans = await PlanBuilder(session).list_for_entry(user, entry_id)
    return [PracticePlanRead.model_validate(p) for p in plans]


@router.get("/plans/{plan_id}", response_model=PracticePlanRead)
async def get_plan(plan_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> PracticePlanRead:
    try:
        plan = await PlanBuilder(session).get(user, plan_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PracticePlanRead.model_validate(plan)


@router.post("/plans/{plan_id}/steps/{step_id}/advance", response_model=PracticePlanRead)
async def advance_step(
    plan_id: uuid.UUID, step_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PracticePlanRead:
    try:
        plan = await PlanBuilder(session).advance_step(user, plan_id, step_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PracticePlanRead.model_validate(plan)


@router.post("/sight-reading", response_model=SightReadingRead, status_code=status.HTTP_201_CREATED)
async def generate_sight_reading(
    payload: SightReadingRequest, user: CurrentUser, session: SessionDep
) -> SightReadingRead:
    exercise = await SightReadingGenerator(session).generate(
        user,
        style_composer_id=payload.style_composer_id,
        target_piece_id=payload.target_piece_id,
        technique_id=payload.technique_id,
        difficulty=payload.difficulty,
    )
    return SightReadingRead.model_validate(exercise)


@router.get("/sight-reading", response_model=list[SightReadingRead])
async def list_sight_reading(user: CurrentUser, session: SessionDep) -> list[SightReadingRead]:
    exercises = await SightReadingGenerator(session).list(user)
    return [SightReadingRead.model_validate(e) for e in exercises]


@router.post("/sight-reading/{exercise_id}/score", response_model=SightReadingRead)
async def score_sight_reading(
    exercise_id: uuid.UUID, payload: SightReadingScore, user: CurrentUser, session: SessionDep
) -> SightReadingRead:
    try:
        exercise = await SightReadingGenerator(session).score(user, exercise_id, payload.self_score)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return SightReadingRead.model_validate(exercise)


@router.post("/polyrhythm/attempts", response_model=PolyrhythmAttemptRead, status_code=status.HTTP_201_CREATED)
async def record_polyrhythm(
    payload: PolyrhythmRecord, user: CurrentUser, session: SessionDep
) -> PolyrhythmAttemptRead:
    attempt = await PolyrhythmTrainer(session).record(
        user, payload.ratio_left, payload.ratio_right, payload.bpm, payload.offsets_ms
    )
    return PolyrhythmAttemptRead.model_validate(attempt)


@router.get("/polyrhythm/attempts", response_model=list[PolyrhythmAttemptRead])
async def list_polyrhythm(
    user: CurrentUser, session: SessionDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[PolyrhythmAttemptRead]:
    attempts = await PolyrhythmTrainer(session).list(user, limit)
    return [PolyrhythmAttemptRead.model_validate(a) for a in attempts]


@router.get("/polyrhythm/stats")
async def polyrhythm_stats(user: CurrentUser, session: SessionDep) -> dict:
    return await PolyrhythmTrainer(session).stats(user)
