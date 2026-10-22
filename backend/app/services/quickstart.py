from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import (
    Passage,
    Piece,
    PieceTechnique,
    RepertoireEntry,
    RepertoireStatus,
    SelfLevel,
    SelfRating,
    Technique,
    User,
    UserTechniqueProfile,
)
from app.services.onboarding import BaseService, OnboardingService

BANDS = {
    SelfLevel.BEGINNER: (0, 38),
    SelfLevel.INTERMEDIATE: (35, 58),
    SelfLevel.ADVANCED: (55, 78),
    SelfLevel.PROFESSIONAL: (72, 100),
}
YEARS = {SelfLevel.BEGINNER: 1, SelfLevel.INTERMEDIATE: 4, SelfLevel.ADVANCED: 8, SelfLevel.PROFESSIONAL: 15}
PROFICIENCY = {
    SelfLevel.BEGINNER: Decimal("3.50"),
    SelfLevel.INTERMEDIATE: Decimal("5.50"),
    SelfLevel.ADVANCED: Decimal("7.00"),
    SelfLevel.PROFESSIONAL: Decimal("8.50"),
}
SUGGESTIONS = 6
POOL = 80
RATED_TECHNIQUES = 3


def spread(pieces: list[Piece], count: int) -> list[Piece]:
    seen: set[Optional[int]] = set()
    distinct = []
    for piece in sorted(pieces, key=lambda item: (float(item.difficulty_score or 0), item.id)):
        if piece.composer_id in seen:
            continue
        seen.add(piece.composer_id)
        distinct.append(piece)
    if len(distinct) <= count:
        return distinct
    step = (len(distinct) - 1) / (count - 1)
    return [distinct[round(index * step)] for index in range(count)]


class QuickStartService(BaseService):
    async def starter_pieces(self, level: SelfLevel) -> list[Piece]:
        low, high = BANDS[level]
        has_passages = select(Passage.piece_id).where(Passage.piece_id == Piece.id).exists()
        stmt = (
            select(Piece)
            .options(selectinload(Piece.composer))
            .where(
                Piece.difficulty_score.is_not(None),
                Piece.difficulty_score >= low,
                Piece.difficulty_score <= high,
                Piece.is_user_created.is_(False),
                Piece.parent_piece_id.is_(None),
                has_passages,
            )
            .order_by(Piece.id)
            .limit(POOL)
        )
        found = list((await self.session.execute(stmt)).scalars().all())
        return spread(found, SUGGESTIONS)

    async def rate_techniques(self, user: User, piece_id: int, level: SelfLevel) -> int:
        links = (
            await self.session.execute(
                select(PieceTechnique.technique_id)
                .where(PieceTechnique.piece_id == piece_id)
                .order_by(PieceTechnique.weight.desc(), PieceTechnique.technique_id)
                .limit(RATED_TECHNIQUES)
            )
        ).scalars().all()
        ids = list(links)
        if not ids:
            fallback = (await self.session.execute(select(Technique.id).order_by(Technique.id).limit(1))).scalar_one_or_none()
            ids = [fallback] if fallback is not None else []
        proficiency = PROFICIENCY[level]
        rating = SelfRating.STRUGGLE if level == SelfLevel.BEGINNER else SelfRating.NEUTRAL
        for technique_id in ids:
            existing = await self.session.get(UserTechniqueProfile, (user.id, technique_id))
            if existing is None:
                self.session.add(UserTechniqueProfile(user_id=user.id, technique_id=technique_id, self_rating=rating, proficiency_score=proficiency))
        await self.session.flush()
        return len(ids)

    async def start(self, user: User, level: SelfLevel, piece_id: int) -> RepertoireEntry:
        piece = await self.session.get(Piece, piece_id)
        if piece is None:
            raise LookupError("that piece isn't in the catalogue")
        user.self_level = level
        if user.years_playing is None:
            user.years_playing = YEARS[level]
        moment = datetime.now(timezone.utc)
        user.tier_quiz_completed_at = user.tier_quiz_completed_at or moment
        user.tastes_completed_at = user.tastes_completed_at or moment
        existing = await OnboardingService(self.session).find_entry(user, piece.id)
        if existing is None:
            existing = RepertoireEntry(user_id=user.id, piece_id=piece.id, status=RepertoireStatus.LEARNING, started_on=date.today())
            self.session.add(existing)
        elif existing.status not in (RepertoireStatus.LEARNING, RepertoireStatus.POLISHING):
            existing.status = RepertoireStatus.LEARNING
        await self.session.flush()
        await self.rate_techniques(user, piece.id, level)
        return existing
