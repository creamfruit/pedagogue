from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Composer,
    Genre,
    Passage,
    PassageSource,
    Piece,
    PieceTechnique,
    RepertoireEntry,
    RepertoireStatus,
    Technique,
    User,
    UserComposerPreference,
    UserGenrePreference,
    UserTechniqueProfile,
)
from app.schemas.schemas import (
    ComposerPreferenceItem,
    ExternalImportRequest,
    OnboardingStatus,
    PieceCreate,
    ProfileUpdate,
    TechniqueProfileItem,
    TierAssignment,
    TopTenItem,
)
from app.services.catalog_match import composer_initial, composer_surname, same_work
from app.services.difficulty import (
    compute_difficulty_score,
    compute_mechanical_load,
    tier_to_profile_values,
)


EXTERNAL_SOURCES = {"openopus", "musicbrainz"}


class BaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def flush(self) -> None:
        await self.session.flush()


class CatalogService(BaseService):
    async def search_pieces(self, query: str, limit: int = 20) -> Sequence[Piece]:
        stmt = (
            select(Piece)
            .options(selectinload(Piece.composer), selectinload(Piece.genre))
            .where(Piece.title.ilike(f"%{query}%"))
            .order_by(Piece.title)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_composers(self, query: str, limit: int = 20) -> Sequence[Composer]:
        stmt = select(Composer).where(Composer.name.ilike(f"%{query}%")).order_by(Composer.name).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_genres(self) -> Sequence[Genre]:
        result = await self.session.execute(select(Genre).order_by(Genre.name))
        return result.scalars().all()

    async def list_techniques(self) -> Sequence[Technique]:
        result = await self.session.execute(select(Technique).order_by(Technique.category, Technique.name))
        return result.scalars().all()

    async def find_composer(self, name: str) -> Optional[Composer]:
        result = await self.session.execute(select(Composer).where(func.lower(Composer.name) == name.lower()))
        composer = result.scalars().first()
        if composer is not None:
            return composer
        surname, initial = composer_surname(name), composer_initial(name)
        if not surname:
            return None
        candidates = (await self.session.execute(select(Composer).where(Composer.name.ilike(f"%{surname[:4]}%")))).scalars().all()
        for candidate in candidates:
            if composer_surname(candidate.name) == surname and composer_initial(candidate.name) == initial:
                return candidate
        return None

    async def get_or_create_composer(self, name: str) -> Composer:
        composer = await self.find_composer(name)
        if composer is None:
            composer = Composer(name=name)
            self.session.add(composer)
            await self.session.flush()
        return composer

    async def find_same_work(self, title: str, composer: Optional[Composer]) -> Optional[Piece]:
        if composer is None:
            return None
        stmt = select(Piece).where(Piece.composer_id == composer.id, Piece.parent_piece_id.is_(None))
        for piece in (await self.session.execute(stmt)).scalars().all():
            if same_work(piece.title, composer.name, title, composer.name):
                return piece
        return None

    async def create_user_piece(self, payload: PieceCreate, user: User) -> Piece:
        composer_id = payload.composer_id
        if composer_id is None and payload.composer_name:
            composer = await self.get_or_create_composer(payload.composer_name)
            composer_id = composer.id
        techniques_by_id: dict[int, Technique] = {}
        if payload.techniques:
            technique_ids = [item.technique_id for item in payload.techniques]
            result = await self.session.execute(select(Technique).where(Technique.id.in_(technique_ids)))
            techniques_by_id = {t.id: t for t in result.scalars().all()}
        mechanical_load = payload.mechanical_load
        if mechanical_load is None:
            load_factors = {t.name: float(t.load_factor) for t in techniques_by_id.values()}
            links = [
                (techniques_by_id[item.technique_id].name, float(item.weight))
                for item in payload.techniques
                if item.technique_id in techniques_by_id
            ]
            mechanical_load = compute_mechanical_load(links, load_factors)
        difficulty_score = payload.difficulty_score
        if difficulty_score is None:
            difficulty_score = compute_difficulty_score(
                mechanical_load, payload.duration_sec, len(payload.techniques)
            )
        piece = Piece(
            title=payload.title,
            composer_id=composer_id,
            genre_id=payload.genre_id,
            catalog_number=payload.catalog_number,
            key_signature=payload.key_signature,
            difficulty_score=difficulty_score,
            mechanical_load=mechanical_load,
            duration_sec=payload.duration_sec,
            custom_style=payload.custom_style,
            is_user_created=True,
            created_by=user.id,
        )
        self.session.add(piece)
        await self.session.flush()
        for item in payload.techniques:
            self.session.add(
                PieceTechnique(piece_id=piece.id, technique_id=item.technique_id, weight=item.weight)
            )
        if payload.techniques:
            await self.session.flush()
        return piece

    async def import_external(self, payload: ExternalImportRequest, user: User) -> Piece:
        source = payload.external_ref.split(":", 1)[0]
        if source not in EXTERNAL_SOURCES:
            raise ValueError(f"unknown external source {source!r}")
        existing = await self.session.execute(
            select(Piece).where(Piece.external_source == source, Piece.external_ref == payload.external_ref)
        )
        found = existing.scalars().first()
        if found is not None:
            return found

        composer = await self.get_or_create_composer(payload.composer_name) if payload.composer_name else None
        same = await self.find_same_work(payload.title, composer)
        if same is not None:
            return same

        piece = Piece(
            title=payload.title,
            composer_id=composer.id if composer else None,
            genre_id=payload.genre_id,
            duration_sec=payload.duration_sec,
            external_source=source,
            external_ref=payload.external_ref,
        )
        self.session.add(piece)
        await self.session.flush()
        return piece

    async def resolve_piece(self, user: User, piece_id: Optional[int], payload: Optional[PieceCreate]) -> Piece:
        if piece_id is not None:
            piece = await self.session.get(Piece, piece_id)
            if piece is None:
                raise LookupError(f"piece {piece_id} not found")
            return piece
        if payload is None:
            raise ValueError("provide either piece_id or piece")
        return await self.create_user_piece(payload, user)


class OnboardingService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.catalog = CatalogService(session)

    async def update_profile(self, user: User, payload: ProfileUpdate) -> User:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.session.flush()
        return user

    async def set_genres(self, user: User, genre_ids: list[int]) -> list[Genre]:
        await self.session.execute(delete(UserGenrePreference).where(UserGenrePreference.user_id == user.id))
        unique_ids = list(dict.fromkeys(genre_ids))
        for genre_id in unique_ids:
            self.session.add(UserGenrePreference(user_id=user.id, genre_id=genre_id))
        await self.session.flush()
        return await self.list_genres(user)

    async def set_composers(self, user: User, items: list[ComposerPreferenceItem]) -> list[Composer]:
        await self.session.execute(delete(UserComposerPreference).where(UserComposerPreference.user_id == user.id))
        seen: set[int] = set()
        for item in items:
            if item.composer_id in seen:
                continue
            seen.add(item.composer_id)
            self.session.add(
                UserComposerPreference(user_id=user.id, composer_id=item.composer_id, rank=item.rank)
            )
        await self.session.flush()
        return await self.list_composers(user)

    async def set_techniques(self, user: User, items: list[TechniqueProfileItem]) -> list[UserTechniqueProfile]:
        for item in items:
            existing = await self.session.get(UserTechniqueProfile, (user.id, item.technique_id))
            if existing is None:
                self.session.add(
                    UserTechniqueProfile(
                        user_id=user.id,
                        technique_id=item.technique_id,
                        self_rating=item.self_rating,
                        proficiency_score=item.proficiency_score,
                    )
                )
            else:
                existing.self_rating = item.self_rating
                existing.proficiency_score = item.proficiency_score
        await self.session.flush()
        return await self.list_technique_profiles(user)

    async def set_tier_list(self, user: User, assignments: list[TierAssignment]) -> list[UserTechniqueProfile]:
        for assignment in assignments:
            self_rating, proficiency_score = tier_to_profile_values(assignment.tier)
            existing = await self.session.get(UserTechniqueProfile, (user.id, assignment.technique_id))
            if existing is None:
                self.session.add(
                    UserTechniqueProfile(
                        user_id=user.id,
                        technique_id=assignment.technique_id,
                        self_rating=self_rating,
                        proficiency_score=proficiency_score,
                    )
                )
            else:
                existing.self_rating = self_rating
                existing.proficiency_score = proficiency_score
        user.tier_quiz_completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return await self.list_technique_profiles(user)

    async def set_top_ten(self, user: User, items: list[TopTenItem]) -> list[RepertoireEntry]:
        await self.session.execute(
            delete(RepertoireEntry).where(
                RepertoireEntry.user_id == user.id, RepertoireEntry.is_top_ten.is_(True)
            )
        )
        await self.session.flush()
        for item in items:
            piece = await self.catalog.resolve_piece(user, item.piece_id, item.piece)
            existing = await self.find_entry(user, piece.id)
            if existing is None:
                self.session.add(
                    RepertoireEntry(
                        user_id=user.id,
                        piece_id=piece.id,
                        status=RepertoireStatus.RETIRED,
                        is_top_ten=True,
                        top_ten_rank=item.rank,
                    )
                )
            else:
                existing.is_top_ten = True
                existing.top_ten_rank = item.rank
        await self.session.flush()
        return await self.list_top_ten(user)

    async def find_entry(self, user: User, piece_id: int) -> Optional[RepertoireEntry]:
        stmt = select(RepertoireEntry).where(
            RepertoireEntry.user_id == user.id, RepertoireEntry.piece_id == piece_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_genres(self, user: User) -> list[Genre]:
        stmt = (
            select(Genre)
            .join(UserGenrePreference, UserGenrePreference.genre_id == Genre.id)
            .where(UserGenrePreference.user_id == user.id)
            .order_by(Genre.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_composers(self, user: User) -> list[Composer]:
        stmt = (
            select(Composer)
            .join(UserComposerPreference, UserComposerPreference.composer_id == Composer.id)
            .where(UserComposerPreference.user_id == user.id)
            .order_by(UserComposerPreference.rank.nulls_last(), Composer.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_technique_profiles(self, user: User) -> list[UserTechniqueProfile]:
        stmt = (
            select(UserTechniqueProfile)
            .options(selectinload(UserTechniqueProfile.technique))
            .where(UserTechniqueProfile.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_top_ten(self, user: User) -> list[RepertoireEntry]:
        stmt = (
            select(RepertoireEntry)
            .options(
                selectinload(RepertoireEntry.piece).selectinload(Piece.composer),
                selectinload(RepertoireEntry.piece).selectinload(Piece.genre),
            )
            .where(RepertoireEntry.user_id == user.id, RepertoireEntry.is_top_ten.is_(True))
            .order_by(RepertoireEntry.top_ten_rank)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, model, *conditions) -> int:
        stmt = select(func.count()).select_from(model).where(*conditions)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def status(self, user: User) -> OnboardingStatus:
        genres = await self.count(UserGenrePreference, UserGenrePreference.user_id == user.id)
        composers = await self.count(UserComposerPreference, UserComposerPreference.user_id == user.id)
        techniques = await self.count(UserTechniqueProfile, UserTechniqueProfile.user_id == user.id)
        top_ten = await self.count(
            RepertoireEntry, RepertoireEntry.user_id == user.id, RepertoireEntry.is_top_ten.is_(True)
        )
        profile_complete = user.self_level is not None and user.years_playing is not None
        tier_quiz_complete = user.tier_quiz_completed_at is not None
        return OnboardingStatus(
            profile_complete=profile_complete,
            genres_chosen=genres,
            composers_chosen=composers,
            techniques_rated=techniques,
            top_ten_logged=top_ten,
            tier_quiz_complete=tier_quiz_complete,
            complete=profile_complete and top_ten > 0 and techniques > 0 and tier_quiz_complete,
        )
