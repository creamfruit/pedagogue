from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.models.models import Passage, PassageTechnique, Piece
from app.schemas.schemas import (
    ComposerPreferenceUpdate,
    ComposerRead,
    ExternalCandidate,
    ExternalImportRequest,
    GenrePreferenceUpdate,
    GenreRead,
    LinkSummary,
    OnboardingStatus,
    OnboardingSummary,
    PieceCreate,
    PieceDetail,
    PieceOverview,
    ProfileUpdate,
    RepertoireEntryRead,
    TechniqueProfileRead,
    TechniqueProfileUpdate,
    TechniqueRead,
    TierListSubmit,
    TopTenSubmit,
    UserRead,
)
from app.services.catalog import LinkExplainer, PieceOverviewService
from app.services.external_catalog import OpenOpusClient
from app.services.notation import SightReadingForge
from app.services.onboarding import CatalogService, OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status(user: CurrentUser, session: SessionDep) -> OnboardingStatus:
    return await OnboardingService(session).status(user)


@router.get("/summary", response_model=OnboardingSummary)
async def onboarding_summary(user: CurrentUser, session: SessionDep) -> OnboardingSummary:
    service = OnboardingService(session)
    return OnboardingSummary(
        user=UserRead.model_validate(user),
        status=await service.status(user),
        genres=[GenreRead.model_validate(g) for g in await service.list_genres(user)],
        composers=[ComposerRead.model_validate(c) for c in await service.list_composers(user)],
        techniques=[TechniqueProfileRead.model_validate(t) for t in await service.list_technique_profiles(user)],
        top_ten=[RepertoireEntryRead.model_validate(e) for e in await service.list_top_ten(user)],
    )


@router.put("/profile", response_model=UserRead)
async def update_profile(payload: ProfileUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    updated = await OnboardingService(session).update_profile(user, payload)
    return UserRead.model_validate(updated)


@router.put("/genres", response_model=list[GenreRead])
async def update_genres(
    payload: GenrePreferenceUpdate, user: CurrentUser, session: SessionDep
) -> list[GenreRead]:
    genres = await OnboardingService(session).set_genres(user, payload.genre_ids)
    return [GenreRead.model_validate(g) for g in genres]


@router.put("/composers", response_model=list[ComposerRead])
async def update_composers(
    payload: ComposerPreferenceUpdate, user: CurrentUser, session: SessionDep
) -> list[ComposerRead]:
    composers = await OnboardingService(session).set_composers(user, payload.composers)
    return [ComposerRead.model_validate(c) for c in composers]


@router.put("/techniques", response_model=list[TechniqueProfileRead])
async def update_techniques(
    payload: TechniqueProfileUpdate, user: CurrentUser, session: SessionDep
) -> list[TechniqueProfileRead]:
    profiles = await OnboardingService(session).set_techniques(user, payload.techniques)
    return [TechniqueProfileRead.model_validate(p) for p in profiles]


@router.put("/tier-list", response_model=list[TechniqueProfileRead])
async def update_tier_list(
    payload: TierListSubmit, user: CurrentUser, session: SessionDep
) -> list[TechniqueProfileRead]:
    try:
        profiles = await OnboardingService(session).set_tier_list(user, payload.tiers)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return [TechniqueProfileRead.model_validate(p) for p in profiles]


@router.put("/top-ten", response_model=list[RepertoireEntryRead])
async def update_top_ten(
    payload: TopTenSubmit, user: CurrentUser, session: SessionDep
) -> list[RepertoireEntryRead]:
    try:
        entries = await OnboardingService(session).set_top_ten(user, payload.pieces)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return [RepertoireEntryRead.model_validate(e) for e in entries]


@catalog_router.get("/pieces", response_model=list[PieceDetail])
async def search_pieces(
    session: SessionDep,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[PieceDetail]:
    pieces = await CatalogService(session).search_pieces(q, limit)
    return [PieceDetail.model_validate(p) for p in pieces]


@catalog_router.get("/composers", response_model=list[ComposerRead])
async def search_composers(
    session: SessionDep,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ComposerRead]:
    composers = await CatalogService(session).search_composers(q, limit)
    return [ComposerRead.model_validate(c) for c in composers]


@catalog_router.get("/genres", response_model=list[GenreRead])
async def list_genres(session: SessionDep) -> list[GenreRead]:
    genres = await CatalogService(session).list_genres()
    return [GenreRead.model_validate(g) for g in genres]


@catalog_router.get("/techniques", response_model=list[TechniqueRead])
async def list_techniques(session: SessionDep) -> list[TechniqueRead]:
    techniques = await CatalogService(session).list_techniques()
    return [TechniqueRead.model_validate(t) for t in techniques]


@catalog_router.get("/external/search", response_model=list[ExternalCandidate])
async def search_external_catalog(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=15, ge=1, le=30),
) -> list[ExternalCandidate]:
    try:
        results = await OpenOpusClient().search(q, limit)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="could not reach the external catalog")
    return [ExternalCandidate(**item) for item in results]


@catalog_router.post("/external/import", response_model=PieceDetail, status_code=status.HTTP_201_CREATED)
async def import_external_piece(
    payload: ExternalImportRequest, user: CurrentUser, session: SessionDep
) -> PieceDetail:
    piece = await CatalogService(session).import_external(payload, user)
    stmt = (
        select(Piece)
        .options(selectinload(Piece.composer), selectinload(Piece.genre))
        .where(Piece.id == piece.id)
    )
    loaded = (await session.execute(stmt)).scalars().one()
    return PieceDetail.model_validate(loaded)


@catalog_router.post("/pieces", response_model=PieceDetail, status_code=status.HTTP_201_CREATED)
async def create_piece(payload: PieceCreate, user: CurrentUser, session: SessionDep) -> PieceDetail:
    piece = await CatalogService(session).create_user_piece(payload, user)
    stmt = (
        select(Piece)
        .options(selectinload(Piece.composer), selectinload(Piece.genre))
        .where(Piece.id == piece.id)
    )
    loaded = (await session.execute(stmt)).scalars().one()
    return PieceDetail.model_validate(loaded)


@catalog_router.get("/pieces/{piece_id}", response_model=PieceDetail)
async def get_piece(piece_id: int, session: SessionDep) -> PieceDetail:
    stmt = (
        select(Piece)
        .options(selectinload(Piece.composer), selectinload(Piece.genre))
        .where(Piece.id == piece_id)
    )
    piece = (await session.execute(stmt)).scalars().one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="piece not found")
    return PieceDetail.model_validate(piece)


@catalog_router.get("/pieces/{piece_id}/overview", response_model=PieceOverview)
async def piece_overview(piece_id: int, session: SessionDep, user: OptionalUser) -> PieceOverview:
    try:
        data = await PieceOverviewService(session).overview(piece_id, user=user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PieceOverview(**data)


@catalog_router.get("/passages/{passage_id}/sight-reading")
async def passage_sight_reading(passage_id: int, session: SessionDep) -> dict:
    stmt = (
        select(Passage)
        .options(selectinload(Passage.technique_links).selectinload(PassageTechnique.technique))
        .where(Passage.id == passage_id)
    )
    passage = (await session.execute(stmt)).scalars().one_or_none()
    if passage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="passage not found")
    ranked = sorted(passage.technique_links, key=lambda link: float(link.weight), reverse=True)
    category = ranked[0].technique.category.value if ranked else None
    difficulty = float(passage.difficulty_score) if passage.difficulty_score is not None else 5.0
    seed = (passage_id * 2654435761) & 0xFFFFFFFFFFFF
    return SightReadingForge(seed).generate(category, difficulty)


@catalog_router.get("/links/{source_id}/{target_id}", response_model=LinkSummary)
async def link_summary(
    source_id: int,
    target_id: int,
    session: SessionDep,
    link_type: str = Query(default="technique"),
) -> LinkSummary:
    try:
        data = await LinkExplainer(session).explain(source_id, target_id, link_type)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return LinkSummary(**data)
