from __future__ import annotations

from typing import Callable, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.models import Composer, Era, Piece, RepertoireEntry, User
from app.services.onboarding import BaseService
from app.services.progression import SAME_ERA, SAME_GENRE, TechniqueVectorService, cosine

ADJACENT_ERA = SAME_ERA / 2
GENRE_BONUS = SAME_GENRE * 0.6
TECHNIQUE_WEIGHT = 0.6
CONTEXT_WEIGHT = 0.4
PARENT_FLOOR = 0.3
SHARED_FLOOR = 0.2
MAX_NODES = 240


def placed_year(piece: Piece) -> Optional[int]:
    if piece.year_composed:
        return piece.year_composed
    composer = piece.composer
    if composer and composer.birth_year:
        return composer.birth_year + 30
    if composer and composer.era and composer.era.start_year:
        return composer.era.start_year + 50
    return None


def context(a: Piece, b: Piece, era_rank: dict[int, int]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    era_a = a.composer.era if a.composer else None
    era_b = b.composer.era if b.composer else None
    if era_a and era_b:
        if era_a.id == era_b.id:
            score += SAME_ERA
            reasons.append(era_a.name)
        elif abs(era_rank.get(era_a.id, 0) - era_rank.get(era_b.id, 99)) == 1:
            score += ADJACENT_ERA
            reasons.append(f"{era_a.name} to {era_b.name}")
    if a.genre_id and a.genre_id == b.genre_id:
        score += GENRE_BONUS
        reasons.append(a.genre.name if a.genre else "same genre")
    return min(1.0, score), reasons


def affinity(technique: float, context_score: float) -> float:
    return TECHNIQUE_WEIGHT * technique + CONTEXT_WEIGHT * context_score


def shared_techniques(a: dict[int, float], b: dict[int, float], names: dict[int, str], limit: int = 3) -> list[str]:
    shared = [t for t in set(a) & set(b) if a[t] > SHARED_FLOOR and b[t] > SHARED_FLOOR]
    shared.sort(key=lambda t: -min(a[t], b[t]))
    return [names[t] for t in shared[:limit] if t in names]


def assign_parents(
    order: Sequence[int], score: Callable[[int, int], float], floor: float = PARENT_FLOOR
) -> dict[int, Optional[tuple[int, float]]]:
    parents: dict[int, Optional[tuple[int, float]]] = {}
    for index, child in enumerate(order):
        best: Optional[tuple[int, float]] = None
        for candidate in order[:index]:
            value = score(candidate, child)
            if value >= floor and (best is None or value >= best[1]):
                best = (candidate, value)
        parents[child] = best
    return parents


class FamilyTreeService(BaseService):
    async def build(self, user: User) -> dict:
        owned = {
            entry.piece_id: entry
            for entry in (
                await self.session.execute(select(RepertoireEntry).where(RepertoireEntry.user_id == user.id))
            ).scalars().all()
        }
        pieces = (
            await self.session.execute(
                select(Piece)
                .options(selectinload(Piece.composer).selectinload(Composer.era), selectinload(Piece.genre))
                .where(
                    Piece.parent_piece_id.is_(None),
                    or_(Piece.is_user_created.is_(False), Piece.id.in_(list(owned) or [0])),
                )
            )
        ).scalars().all()
        eras = (await self.session.execute(select(Era).order_by(Era.start_year))).scalars().all()
        era_rank = {era.id: rank for rank, era in enumerate(eras)}
        vectors = await TechniqueVectorService(self.session).vectors_for([piece.id for piece in pieces])
        names = await TechniqueVectorService(self.session).technique_names(
            {t for vector in vectors.values() for t in vector}
        )

        placed = [(placed_year(piece), piece) for piece in pieces]
        placed = [(year, piece) for year, piece in placed if year is not None and vectors.get(piece.id)]
        placed.sort(key=lambda item: (item[0], float(item[1].difficulty_score or 0), item[1].id))
        placed = placed[:MAX_NODES]
        by_id = {piece.id: piece for _, piece in placed}
        years = {piece.id: year for year, piece in placed}

        def score(parent_id: int, child_id: int) -> float:
            technique = cosine(vectors[parent_id], vectors[child_id])
            shared_context, _ = context(by_id[parent_id], by_id[child_id], era_rank)
            return affinity(technique, shared_context)

        parents = assign_parents([piece.id for _, piece in placed], score)
        nodes = []
        for year, piece in placed:
            parent = parents.get(piece.id)
            link = None
            if parent:
                parent_piece = by_id[parent[0]]
                _, reasons = context(parent_piece, piece, era_rank)
                if parent_piece.composer_id and parent_piece.composer_id == piece.composer_id:
                    reasons = ["same composer", *reasons]
                link = {
                    "parent": parent[0],
                    "affinity": round(parent[1], 3),
                    "technique": round(cosine(vectors[parent[0]], vectors[piece.id]), 3),
                    "shared_techniques": shared_techniques(vectors[parent[0]], vectors[piece.id], names),
                    "reasons": reasons,
                }
            entry = owned.get(piece.id)
            nodes.append(
                {
                    "id": piece.id,
                    "title": piece.title,
                    "composer": piece.composer.name if piece.composer else None,
                    "era": piece.composer.era.name if piece.composer and piece.composer.era else None,
                    "genre": piece.genre.name if piece.genre else None,
                    "year": year,
                    "year_estimated": not piece.year_composed,
                    "difficulty": float(piece.difficulty_score) if piece.difficulty_score is not None else None,
                    "in_repertoire": entry is not None,
                    "status": entry.status.value if entry else None,
                    "link": link,
                }
            )
        return {
            "nodes": nodes,
            "roots": sum(1 for node in nodes if node["link"] is None),
            "floor": PARENT_FLOOR,
            "weights": {"technique": TECHNIQUE_WEIGHT, "era_genre": CONTEXT_WEIGHT},
        }
