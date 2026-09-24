import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models.models import Piece, Recommendation, RecommendationStatus, RepertoireEntry, User
from app.schemas.schemas import (
    ConstellationGraph,
    PathwayAdopt,
    PathwayAdopted,
    PathwayResponse,
    PathwayStep,
    RepertoireEntryRead,
    PieceDetail,
    PrerequisiteResponse,
    RecommendationDecision,
    RecommendationRead,
    ScoredPieceRead,
    SteppingStoneResponse,
)
from app.services.progression import (
    ConstellationService,
    PathPlanner,
    PathwayBuilder,
    PrerequisiteRecommender,
    TechniqueVectorService,
)

router = APIRouter(prefix="/progression", tags=["progression"])


def to_scored(items) -> list[ScoredPieceRead]:
    return [
        ScoredPieceRead(
            piece=PieceDetail.model_validate(item.piece),
            score=item.score,
            overlap=item.overlap,
            coverage=item.coverage,
            gap=item.gap,
            shared_techniques=item.shared_techniques,
            rationale=item.rationale,
        )
        for item in items
    ]


async def load_piece(session, piece_id: int) -> Piece:
    stmt = (
        select(Piece)
        .options(selectinload(Piece.composer), selectinload(Piece.genre))
        .where(Piece.id == piece_id)
    )
    piece = (await session.execute(stmt)).scalar_one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="piece not found")
    return piece


@router.get("/pieces/{piece_id}/prerequisites", response_model=PrerequisiteResponse)
async def prerequisites(
    piece_id: int,
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=5, ge=1, le=10),
    persist: bool = Query(default=False),
) -> PrerequisiteResponse:
    piece = await load_piece(session, piece_id)
    recommender = PrerequisiteRecommender(session)
    scored = await recommender.rank(piece, user, limit=limit)
    if persist and scored:
        await recommender.persist(user, piece, scored)
        await recommender.seed_catalog_edges(piece, scored)
    return PrerequisiteResponse(
        target=PieceDetail.model_validate(piece),
        prerequisites=to_scored(scored),
        persisted=bool(persist and scored),
    )


@router.get("/pieces/{piece_id}/path", response_model=SteppingStoneResponse)
async def stepping_stones(
    piece_id: int,
    user: CurrentUser,
    session: SessionDep,
    max_steps: int = Query(default=4, ge=1, le=6),
) -> SteppingStoneResponse:
    piece = await load_piece(session, piece_id)
    planner = PathPlanner(session)
    path = await planner.stepping_stones(user, piece, max_steps=max_steps)
    ceiling = await TechniqueVectorService(session).comfort_ceiling(user)
    return SteppingStoneResponse(
        target=PieceDetail.model_validate(piece),
        comfort_ceiling=ceiling,
        path=to_scored(path),
        total_steps=len(path),
    )


@router.get("/pieces/{piece_id}/pathway", response_model=PathwayResponse)
async def pathway(
    piece_id: int,
    user: CurrentUser,
    session: SessionDep,
    max_steps: int = Query(default=4, ge=1, le=6),
) -> PathwayResponse:
    piece = await load_piece(session, piece_id)
    builder = PathwayBuilder(session)
    assessment = await builder.assess(user, piece, max_steps=max_steps)

    owned = await session.execute(
        select(RepertoireEntry.piece_id).where(RepertoireEntry.user_id == user.id)
    )
    owned_ids = set(owned.scalars().all())

    steps = [
        PathwayStep(
            order=index + 1,
            piece=PieceDetail.model_validate(item.piece),
            score=item.score,
            gap=item.gap,
            shared_techniques=item.shared_techniques,
            rationale=item.rationale,
            owned=item.piece.id in owned_ids,
        )
        for index, item in enumerate(assessment["path"])
    ]
    return PathwayResponse(
        target=PieceDetail.model_validate(piece),
        comfort_ceiling=assessment["comfort_ceiling"],
        target_difficulty=assessment["target_difficulty"],
        gap=assessment["gap"],
        out_of_reach=assessment["out_of_reach"],
        steps=steps,
    )


@router.post(
    "/pieces/{piece_id}/pathway/adopt",
    response_model=PathwayAdopted,
    status_code=status.HTTP_201_CREATED,
)
async def adopt_pathway(
    piece_id: int, payload: PathwayAdopt, user: CurrentUser, session: SessionDep
) -> PathwayAdopted:
    piece = await load_piece(session, piece_id)
    builder = PathwayBuilder(session)
    ids = payload.piece_ids
    if not ids:
        assessment = await builder.assess(user, piece)
        ids = [item.piece.id for item in assessment["path"]]
    result = await builder.adopt(user, piece, ids, payload.include_target)
    created = [RepertoireEntryRead.model_validate(entry) for entry in result["created"]]
    if not created:
        message = "Everything on that pathway is already in your repertoire."
    else:
        message = f"Added {len(created)} piece(s). The first step is set to learning, the rest to wishlist."
    return PathwayAdopted(created=created, skipped=result["skipped"], message=message)


@router.get("/recommendations", response_model=list[RecommendationRead])
async def list_recommendations(
    user: CurrentUser,
    session: SessionDep,
    status_filter: Optional[RecommendationStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RecommendationRead]:
    stmt = (
        select(Recommendation)
        .options(
            selectinload(Recommendation.recommended_piece).selectinload(Piece.composer),
            selectinload(Recommendation.recommended_piece).selectinload(Piece.genre),
        )
        .where(Recommendation.user_id == user.id)
        .order_by(Recommendation.score.desc().nulls_last())
        .limit(limit)
    )
    if status_filter is not None:
        stmt = stmt.where(Recommendation.status == status_filter)
    result = await session.execute(stmt)
    return [RecommendationRead.model_validate(r) for r in result.scalars().unique().all()]


@router.patch("/recommendations/{recommendation_id}", response_model=RecommendationRead)
async def decide_recommendation(
    recommendation_id: uuid.UUID,
    payload: RecommendationDecision,
    user: CurrentUser,
    session: SessionDep,
) -> RecommendationRead:
    stmt = (
        select(Recommendation)
        .options(
            selectinload(Recommendation.recommended_piece).selectinload(Piece.composer),
            selectinload(Recommendation.recommended_piece).selectinload(Piece.genre),
        )
        .where(Recommendation.id == recommendation_id, Recommendation.user_id == user.id)
    )
    recommendation = (await session.execute(stmt)).scalar_one_or_none()
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recommendation not found")
    recommendation.status = payload.status
    await session.flush()
    return RecommendationRead.model_validate(recommendation)


@router.get("/constellation", response_model=ConstellationGraph)
async def constellation(
    user: CurrentUser,
    session: SessionDep,
    link_types: Optional[str] = Query(default=None, description="comma separated: composer,technique,era_genre"),
    threshold: float = Query(default=0.25, ge=0.0, le=1.0),
) -> ConstellationGraph:
    types = [t.strip() for t in link_types.split(",")] if link_types else None
    graph = await ConstellationService(session).build(user, types, threshold)
    return ConstellationGraph(**graph)


@router.get("/constellation/{friend_id}", response_model=ConstellationGraph)
async def friend_constellation(
    friend_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    link_types: Optional[str] = Query(default=None),
    threshold: float = Query(default=0.25, ge=0.0, le=1.0),
) -> ConstellationGraph:
    owner = await session.get(User, friend_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pianist not found")
    service = ConstellationService(session)
    if not await service.friend_visible(user, owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="that constellation is not shared with you"
        )
    types = [t.strip() for t in link_types.split(",")] if link_types else None
    graph = await service.build(owner, types, threshold)
    return ConstellationGraph(**graph)
