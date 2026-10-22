import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, OptionalUser, SessionDep, StorageDep
from app.models.models import Passage, PassageTechnique, Piece, SelfLevel
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
    SimilarPieces,
    ProfileUpdate,
    QuickStartIn,
    QuickStartOut,
    StarterPiece,
    RepertoireEntryRead,
    TechniqueProfileRead,
    TechniqueExample,
    TechniqueProfileUpdate,
    TechniqueRead,
    TierListSubmit,
    TopTenSubmit,
    UserRead,
)
from app.services.catalog import LinkExplainer, PieceOverviewService, TechniqueExampleService
from app.services.catalog_match import merge_candidates
from app.services.external_catalog import OpenOpusClient
from app.services.musicbrainz_catalog import MusicBrainzClient
from app.services.notation import SightReadingForge, forge_key
from app.services.onboarding import CatalogService, OnboardingService
from app.services.quickstart import QuickStartService
from app.workers.queue import get_queue

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status(user: CurrentUser, session: SessionDep) -> OnboardingStatus:
    return await OnboardingService(session).status(user)


@router.get("/starter-pieces", response_model=list[StarterPiece])
async def starter_pieces(user: CurrentUser, session: SessionDep, level: SelfLevel = Query()) -> list[StarterPiece]:
    pieces = await QuickStartService(session).starter_pieces(level)
    return [
        StarterPiece(id=piece.id, title=piece.display_title, composer=piece.composer.name if piece.composer else None, difficulty_score=piece.difficulty_score)
        for piece in pieces
    ]


@router.post("/quick", response_model=QuickStartOut)
async def quick_start(payload: QuickStartIn, user: CurrentUser, session: SessionDep) -> QuickStartOut:
    try:
        entry = await QuickStartService(session).start(user, payload.self_level, payload.piece_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    piece = (await session.execute(select(Piece).options(selectinload(Piece.composer)).where(Piece.id == entry.piece_id))).scalar_one()
    return QuickStartOut(status=await OnboardingService(session).status(user), entry_id=entry.id, piece_title=piece.display_title)


@router.post("/finish", response_model=OnboardingStatus)
async def finish_onboarding(user: CurrentUser, session: SessionDep) -> OnboardingStatus:
    return await OnboardingService(session).finish(user)


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


@catalog_router.get("/techniques/examples", response_model=list[TechniqueExample])
async def technique_examples(session: SessionDep) -> list[TechniqueExample]:
    rows = await TechniqueExampleService(session).examples()
    return [TechniqueExample(**row) for row in rows]


@catalog_router.get("/external/search", response_model=list[ExternalCandidate])
async def search_external_catalog(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=15, ge=1, le=30),
) -> list[ExternalCandidate]:
    openopus, musicbrainz = await asyncio.gather(
        OpenOpusClient().search(q, limit), MusicBrainzClient().search(q, limit), return_exceptions=True
    )
    groups = [group for group in (openopus, musicbrainz) if not isinstance(group, BaseException)]
    if not groups:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="could not reach the external catalogs")
    return [ExternalCandidate(**item) for item in merge_candidates(*groups, limit=limit)]


@catalog_router.post("/external/import", response_model=PieceDetail, status_code=status.HTTP_201_CREATED)
async def import_external_piece(
    payload: ExternalImportRequest, user: CurrentUser, session: SessionDep, background_tasks: BackgroundTasks
) -> PieceDetail:
    try:
        piece = await CatalogService(session).import_external(payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if piece.metadata_generated_at is None:
        await session.commit()
        await get_queue(background_tasks).enqueue("generate_piece_metadata", piece.id)
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
        .where(Piece.id == piece_id, Piece.hidden_at.is_(None))
    )
    piece = (await session.execute(stmt)).scalars().one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="piece not found")
    return PieceDetail.model_validate(piece)


@catalog_router.get("/pieces/{piece_id}/overview", response_model=PieceOverview)
async def piece_overview(
    piece_id: int, session: SessionDep, user: OptionalUser, background_tasks: BackgroundTasks
) -> PieceOverview:
    try:
        data = await PieceOverviewService(session).overview(piece_id, user=user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if data.pop("wants_facts", False):
        await get_queue(background_tasks).enqueue("enrich_piece_facts", piece_id)
    if user is not None and data.get("sections"):
        await attach_score_crops(session, user, piece_id, data["sections"])
    return PieceOverview(**data)


@catalog_router.get("/passages/{passage_id}/image")
async def passage_image(passage_id: int, session: SessionDep, storage: StorageDep) -> Response:
    passage = (
        await session.execute(select(Passage).join(Piece, Piece.id == Passage.piece_id).where(Passage.id == passage_id, Piece.hidden_at.is_(None)))
    ).scalar_one_or_none()
    if passage is None or not passage.image_key or not storage.exists(passage.image_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no image for this passage")
    with storage.open(passage.image_key) as handle:
        body = handle.read()
    return Response(body, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@catalog_router.get("/pieces/{piece_id}/similar", response_model=SimilarPieces)
async def similar_pieces_route(
    piece_id: int,
    session: SessionDep,
    direction: str = Query(default="easier", pattern="^(easier|harder|both)$"),
    limit: int = Query(default=5, ge=1, le=12),
) -> SimilarPieces:
    from app.services.similar import similar_pieces

    try:
        found = await similar_pieces(session, piece_id, direction=direction, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return SimilarPieces(**found)


async def attach_score_crops(session, user, piece_id: int, sections: list[dict]) -> None:
    from app.models.models import Analysis, PdfSubmission, RepertoireEntry

    rows = (
        await session.execute(
            select(Analysis.submission_id, Analysis.raw_result)
            .join(PdfSubmission, PdfSubmission.id == Analysis.submission_id)
            .join(RepertoireEntry, RepertoireEntry.id == PdfSubmission.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id, RepertoireEntry.piece_id == piece_id)
            .order_by(Analysis.created_at.desc())
        )
    ).all()
    for submission_id, raw in rows:
        crops = (raw or {}).get("crops") or []
        if not crops:
            continue
        by_span = {(crop["start"], crop["end"]): (index, crop) for index, crop in enumerate(crops)}
        for section in sections:
            found = by_span.get((section["start_measure"], section["end_measure"]))
            if found and not section.get("score_crop"):
                index, crop = found
                section["score_crop"] = f"/submissions/{submission_id}/crops/{index}"
                section["score_page"] = crop.get("page")
        break


@catalog_router.get("/passages/{passage_id}/sight-reading")
async def passage_sight_reading(
    passage_id: int, session: SessionDep, technique_id: Optional[int] = Query(default=None)
) -> dict:
    stmt = (
        select(Passage)
        .options(
            selectinload(Passage.technique_links).selectinload(PassageTechnique.technique),
            selectinload(Passage.piece),
        )
        .where(Passage.id == passage_id)
    )
    passage = (await session.execute(stmt)).scalars().one_or_none()
    if passage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="passage not found")
    ranked = sorted(passage.technique_links, key=lambda link: float(link.weight), reverse=True)
    if technique_id is not None:
        ranked = sorted(ranked, key=lambda link: link.technique_id != technique_id)
    top = ranked[0].technique if ranked else None
    category = top.category.value if top else None
    difficulty = float(passage.difficulty_score) if passage.difficulty_score is not None else 5.0
    seed = (passage_id * 2654435761) & 0xFFFFFFFFFFFF
    key = forge_key(passage.piece.key_signature) if passage.piece else None
    return SightReadingForge(seed).generate(category, difficulty, top.name if top else None, key)


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
