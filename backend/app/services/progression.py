from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Composer,
    Piece,
    PiecePrerequisite,
    PieceTechnique,
    PrerequisiteSource,
    Recommendation,
    RecommendationStatus,
    RepertoireEntry,
    RepertoireStatus,
    SelfRating,
    Technique,
    User,
    UserTechniqueProfile,
)
from app.services.onboarding import BaseService

IDEAL_GAP = 15.0
GAP_SPREAD = 12.0
OVERLAP_WEIGHT = 0.60
GAP_WEIGHT = 0.25
WEAKNESS_WEIGHT = 0.15
MIN_SCORE = 0.15


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[k] * b[k] for k in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def coverage(target: dict[int, float], candidate: dict[int, float]) -> float:
    if not target:
        return 0.0
    total = sum(target.values())
    if total == 0:
        return 0.0
    covered = sum(weight for tid, weight in target.items() if candidate.get(tid, 0.0) > 0.2)
    return covered / total


def gap_fit(gap: float) -> float:
    if gap <= 0:
        return 0.0
    return math.exp(-((gap - IDEAL_GAP) ** 2) / (2 * GAP_SPREAD**2))


@dataclass
class ScoredPiece:
    piece: Piece
    score: float
    overlap: float
    coverage: float
    gap: float
    shared_techniques: list[str]
    rationale: str


class TechniqueVectorService(BaseService):
    async def vectors_for(self, piece_ids: Iterable[int]) -> dict[int, dict[int, float]]:
        ids = list(piece_ids)
        if not ids:
            return {}
        stmt = select(PieceTechnique).where(PieceTechnique.piece_id.in_(ids))
        result = await self.session.execute(stmt)
        vectors: dict[int, dict[int, float]] = {pid: {} for pid in ids}
        for link in result.scalars().all():
            vectors[link.piece_id][link.technique_id] = float(link.weight)
        return vectors

    async def technique_names(self, technique_ids: Iterable[int]) -> dict[int, str]:
        ids = list(technique_ids)
        if not ids:
            return {}
        result = await self.session.execute(select(Technique).where(Technique.id.in_(ids)))
        return {t.id: t.name for t in result.scalars().all()}

    async def weak_technique_ids(self, user: User) -> set[int]:
        stmt = select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id)
        result = await self.session.execute(stmt)
        return {p.technique_id for p in result.scalars().all() if p.is_weakness}

    async def comfort_ceiling(self, user: User) -> float:
        stmt = (
            select(func.max(Piece.difficulty_score))
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .where(
                RepertoireEntry.user_id == user.id,
                RepertoireEntry.status.in_(
                    [RepertoireStatus.RETIRED, RepertoireStatus.PERFORMANCE_READY]
                ),
            )
        )
        result = await self.session.execute(stmt)
        ceiling = result.scalar_one_or_none()
        return float(ceiling) if ceiling is not None else 30.0


class PrerequisiteRecommender(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.vectors = TechniqueVectorService(session)

    async def candidates(self, target: Piece) -> Sequence[Piece]:
        stmt = (
            select(Piece)
            .options(selectinload(Piece.composer), selectinload(Piece.genre))
            .where(
                Piece.id != target.id,
                Piece.difficulty_score.is_not(None),
                Piece.difficulty_score < target.difficulty_score,
                Piece.parent_piece_id.is_(None) if target.parent_piece_id is None else Piece.id.is_not(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def rank(
        self, target: Piece, user: Optional[User] = None, limit: int = 5
    ) -> list[ScoredPiece]:
        if target.difficulty_score is None:
            return []
        candidates = await self.candidates(target)
        if not candidates:
            return []

        all_ids = [target.id] + [c.id for c in candidates]
        vectors = await self.vectors.vectors_for(all_ids)
        target_vector = vectors.get(target.id, {})
        if not target_vector:
            return []

        weak = await self.vectors.weak_technique_ids(user) if user else set()
        names = await self.vectors.technique_names(target_vector.keys())
        target_difficulty = float(target.difficulty_score)

        scored: list[ScoredPiece] = []
        for candidate in candidates:
            vector = vectors.get(candidate.id, {})
            if not vector:
                continue
            overlap = cosine(target_vector, vector)
            if overlap <= 0:
                continue
            cover = coverage(target_vector, vector)
            gap = target_difficulty - float(candidate.difficulty_score)
            fit = gap_fit(gap)
            weak_hits = [tid for tid in vector if tid in weak and tid in target_vector]
            weak_bonus = min(len(weak_hits) / 3.0, 1.0) if weak else 0.0
            score = (
                OVERLAP_WEIGHT * (0.7 * overlap + 0.3 * cover)
                + GAP_WEIGHT * fit
                + WEAKNESS_WEIGHT * weak_bonus
            )
            if score < MIN_SCORE:
                continue
            shared = sorted(
                (tid for tid in vector if tid in target_vector),
                key=lambda tid: target_vector[tid],
                reverse=True,
            )[:3]
            shared_names = [names[tid] for tid in shared if tid in names]
            scored.append(
                ScoredPiece(
                    piece=candidate,
                    score=round(score, 3),
                    overlap=round(overlap, 3),
                    coverage=round(cover, 3),
                    gap=round(gap, 1),
                    shared_techniques=shared_names,
                    rationale=self.explain(candidate, target, shared_names, gap, weak_hits, names),
                )
            )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    @staticmethod
    def explain(
        candidate: Piece,
        target: Piece,
        shared: list[str],
        gap: float,
        weak_hits: list[int],
        names: dict[int, str],
    ) -> str:
        parts = []
        if shared:
            joined = ", ".join(name.lower() for name in shared)
            parts.append(f"drills the same {joined} that {target.title} demands")
        parts.append(f"sits {gap:.1f} difficulty points lower, a workable step")
        if weak_hits:
            weak_names = ", ".join(names[tid].lower() for tid in weak_hits if tid in names)
            if weak_names:
                parts.append(f"targets {weak_names}, which you rated a struggle")
        return f"{candidate.title} " + "; ".join(parts) + "."

    async def persist(self, user: User, target: Piece, scored: Sequence[ScoredPiece]) -> list[Recommendation]:
        existing = await self.session.execute(
            select(Recommendation).where(
                Recommendation.user_id == user.id, Recommendation.target_piece_id == target.id
            )
        )
        by_piece = {r.recommended_piece_id: r for r in existing.scalars().all()}
        saved: list[Recommendation] = []
        for item in scored:
            row = by_piece.get(item.piece.id)
            if row is None:
                row = Recommendation(
                    user_id=user.id,
                    target_piece_id=target.id,
                    recommended_piece_id=item.piece.id,
                    score=Decimal(str(item.score)),
                    reason=item.rationale,
                )
                self.session.add(row)
            elif row.status == RecommendationStatus.SUGGESTED:
                row.score = Decimal(str(item.score))
                row.reason = item.rationale
            saved.append(row)
        await self.session.flush()
        return saved

    async def seed_catalog_edges(self, target: Piece, scored: Sequence[ScoredPiece]) -> None:
        for item in scored:
            exists = await self.session.execute(
                select(PiecePrerequisite).where(
                    PiecePrerequisite.target_piece_id == target.id,
                    PiecePrerequisite.prerequisite_piece_id == item.piece.id,
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue
            self.session.add(
                PiecePrerequisite(
                    target_piece_id=target.id,
                    prerequisite_piece_id=item.piece.id,
                    overlap_score=Decimal(str(round(item.overlap, 3))),
                    source=PrerequisiteSource.COMPUTED,
                    rationale=item.rationale,
                )
            )
        await self.session.flush()


class PathPlanner(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.recommender = PrerequisiteRecommender(session)
        self.vectors = TechniqueVectorService(session)

    async def stepping_stones(
        self, user: User, target: Piece, max_steps: int = 4
    ) -> list[ScoredPiece]:
        ceiling = await self.vectors.comfort_ceiling(user)
        owned = await self.owned_piece_ids(user)
        path: list[ScoredPiece] = []
        current = target
        seen: set[int] = {target.id}

        for _ in range(max_steps):
            if current.difficulty_score is None or float(current.difficulty_score) <= ceiling + 0.5:
                break
            ranked = await self.recommender.rank(current, user, limit=6)
            nxt = next((s for s in ranked if s.piece.id not in seen and s.piece.id not in owned), None)
            if nxt is None:
                break
            path.append(nxt)
            seen.add(nxt.piece.id)
            current = nxt.piece
        path.reverse()
        return path

    async def owned_piece_ids(self, user: User) -> set[int]:
        result = await self.session.execute(
            select(RepertoireEntry.piece_id).where(
                RepertoireEntry.user_id == user.id,
                RepertoireEntry.status.in_(
                    [RepertoireStatus.RETIRED, RepertoireStatus.PERFORMANCE_READY]
                ),
            )
        )
        return set(result.scalars().all())


class PathwayBuilder(BaseService):
    GAP_TRIGGER = 16.0

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.planner = PathPlanner(session)
        self.vectors = TechniqueVectorService(session)

    async def assess(self, user: User, target: Piece, max_steps: int = 4) -> dict:
        ceiling = await self.vectors.comfort_ceiling(user)
        difficulty = float(target.difficulty_score) if target.difficulty_score is not None else 5.0
        gap = round(difficulty - ceiling, 2)
        path = await self.planner.stepping_stones(user, target, max_steps=max_steps)
        return {
            "comfort_ceiling": ceiling,
            "target_difficulty": difficulty,
            "gap": gap,
            "out_of_reach": gap >= self.GAP_TRIGGER,
            "path": path,
        }

    async def adopt(
        self, user: User, target: Piece, steps: Sequence[int], include_target: bool = True
    ) -> dict:
        from app.models.models import RepertoireStatus
        from app.services.economy import EconomyService
        from app.models.models import LedgerReason

        existing = await self.session.execute(
            select(RepertoireEntry.piece_id).where(RepertoireEntry.user_id == user.id)
        )
        owned = set(existing.scalars().all())

        ordered = list(dict.fromkeys(steps))
        if include_target and target.id not in ordered:
            ordered.append(target.id)

        created: list[RepertoireEntry] = []
        skipped: list[int] = []
        for index, piece_id in enumerate(ordered):
            if piece_id in owned:
                skipped.append(piece_id)
                continue
            piece = await self.session.get(Piece, piece_id)
            if piece is None:
                skipped.append(piece_id)
                continue
            entry = RepertoireEntry(
                user_id=user.id,
                piece_id=piece_id,
                status=RepertoireStatus.LEARNING if index == 0 else RepertoireStatus.WISHLIST,
                notes="Added from the prerequisite pathway.",
            )
            self.session.add(entry)
            created.append(entry)
            owned.add(piece_id)
        await self.session.flush()

        if created:
            economy = EconomyService(self.session)
            await economy.award(
                user,
                len(created) * 25,
                0,
                LedgerReason.PATHWAY_STARTED,
                detail=f"started a {len(created)} step pathway to {target.title}",
                ref_type="piece",
                ref_id=target.id,
            )

        hydrated = []
        for entry in created:
            stmt = (
                select(RepertoireEntry)
                .options(
                    selectinload(RepertoireEntry.piece).selectinload(Piece.composer),
                    selectinload(RepertoireEntry.piece).selectinload(Piece.genre),
                )
                .where(RepertoireEntry.id == entry.id)
            )
            hydrated.append((await self.session.execute(stmt)).scalar_one())
        return {"created": hydrated, "skipped": len(skipped)}


class ConstellationService(BaseService):
    LINK_TYPES = ("composer", "technique", "era_genre")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.vectors = TechniqueVectorService(session)

    async def build(
        self, user: User, link_types: Optional[Sequence[str]] = None, threshold: float = 0.25
    ) -> dict:
        types = [t for t in (link_types or self.LINK_TYPES) if t in self.LINK_TYPES]
        stmt = (
            select(RepertoireEntry)
            .options(
                selectinload(RepertoireEntry.piece).selectinload(Piece.composer).selectinload(Composer.era),
                selectinload(RepertoireEntry.piece).selectinload(Piece.genre),
            )
            .where(RepertoireEntry.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        entries = list(result.scalars().unique().all())
        pieces = [entry.piece for entry in entries]
        vectors = await self.vectors.vectors_for([p.id for p in pieces])

        nodes = []
        for entry in entries:
            piece = entry.piece
            difficulty = float(piece.difficulty_score) if piece.difficulty_score is not None else 50.0
            nodes.append(
                {
                    "id": piece.id,
                    "entry_id": str(entry.id),
                    "title": piece.title,
                    "composer": piece.composer.name if piece.composer else None,
                    "composer_id": piece.composer_id,
                    "genre": piece.genre.name if piece.genre else None,
                    "era": piece.composer.era.name if piece.composer and piece.composer.era else None,
                    "difficulty": difficulty,
                    "radius": round(4 + (difficulty / 10.0) * 2.2, 2),
                    "status": entry.status.value,
                    "is_top_ten": entry.is_top_ten,
                    "is_verified": entry.is_verified or not entry.needs_verification,
                    "is_custom": piece.is_custom,
                    "decay": entry.decay_level,
                }
            )

        links = []
        for i, a in enumerate(pieces):
            for b in pieces[i + 1 :]:
                if "composer" in types and a.composer_id and a.composer_id == b.composer_id:
                    links.append(self.link(a.id, b.id, "composer", 1.0, a.composer.name if a.composer else ""))
                if "technique" in types:
                    strength = cosine(vectors.get(a.id, {}), vectors.get(b.id, {}))
                    if strength >= threshold:
                        links.append(self.link(a.id, b.id, "technique", round(strength, 3), "shared techniques"))
                if "era_genre" in types:
                    era_a = a.composer.era_id if a.composer else None
                    era_b = b.composer.era_id if b.composer else None
                    if era_a and era_a == era_b:
                        label = a.composer.era.name if a.composer and a.composer.era else "same era"
                        links.append(self.link(a.id, b.id, "era_genre", 0.7, label))
                    elif a.genre_id and a.genre_id == b.genre_id:
                        links.append(
                            self.link(a.id, b.id, "era_genre", 0.5, a.genre.name if a.genre else "same genre")
                        )

        return {
            "nodes": nodes,
            "links": links,
            "link_types": types,
            "counts": {
                "nodes": len(nodes),
                "links": len(links),
                **{t: sum(1 for l in links if l["link_type"] == t) for t in types},
            },
        }

    @staticmethod
    def link(source: int, target: int, link_type: str, strength: float, label: str) -> dict:
        return {
            "source": source,
            "target": target,
            "link_type": link_type,
            "strength": strength,
            "label": label,
        }

    async def friend_visible(self, viewer: User, owner: User) -> bool:
        from app.models.models import Friendship, FriendshipStatus, ProfileVisibility

        if owner.id == viewer.id or owner.profile_visibility == ProfileVisibility.PUBLIC:
            return True
        if owner.profile_visibility == ProfileVisibility.PRIVATE:
            return False
        stmt = select(Friendship).where(
            Friendship.status == FriendshipStatus.ACCEPTED,
            (
                (Friendship.requester_id == viewer.id) & (Friendship.addressee_id == owner.id)
            )
            | ((Friendship.requester_id == owner.id) & (Friendship.addressee_id == viewer.id)),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
