from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Composer, Piece
from app.services.difficulty import difficulty_band
from app.services.public_pages import full_title, piece_slug_for

CACHE_SECONDS = 600
DEFAULT_LIMIT = 5
MAX_LIMIT = 12
MIN_GAP = 3.0
PER_COMPOSER = 2
DIRECTIONS = ("easier", "harder", "both")


@dataclass
class Matrix:
    built_at: float
    ids: list
    vectors: np.ndarray
    difficulty: np.ndarray
    pieces: dict

    def index_of(self, piece_id: int) -> Optional[int]:
        try:
            return self.ids.index(piece_id)
        except ValueError:
            return None


_cache: dict = {}


def forget_vectors() -> None:
    _cache.clear()


async def load_matrix(session: AsyncSession, *, fresh: bool = False) -> Matrix:
    held = _cache.get("matrix")
    if held is not None and not fresh and time.monotonic() - held.built_at < CACHE_SECONDS:
        return held
    rows = (
        await session.execute(
            select(Piece)
            .options(selectinload(Piece.composer))
            .where(
                Piece.technique_vector.is_not(None),
                Piece.difficulty_score.is_not(None),
                Piece.is_user_created.is_(False),
                Piece.hidden_at.is_(None),
            )
            .order_by(Piece.id)
        )
    ).scalars().all()
    matrix = Matrix(
        built_at=time.monotonic(),
        ids=[piece.id for piece in rows],
        vectors=np.array([np.asarray(piece.technique_vector, dtype=float) for piece in rows]) if rows else np.zeros((0, 1)),
        difficulty=np.array([float(piece.difficulty_score) for piece in rows]),
        pieces={piece.id: piece for piece in rows},
    )
    _cache["matrix"] = matrix
    return matrix


def describe(piece: Piece, target_difficulty: float, distance: float) -> dict:
    value = float(piece.difficulty_score)
    return {
        "id": piece.id,
        "slug": piece_slug_for(piece, piece.composer),
        "title": piece.title,
        "full_title": full_title(piece),
        "composer": piece.composer.name if piece.composer else None,
        "difficulty": round(value, 1),
        "band": difficulty_band(piece.difficulty_score),
        "difference": round(value - target_difficulty, 1),
        "similarity": round(1.0 / (1.0 + distance), 3),
    }


def related(piece: Piece, other: Piece) -> bool:
    if other.id == piece.id:
        return True
    if piece.parent_piece_id is not None and (other.parent_piece_id == piece.parent_piece_id or other.id == piece.parent_piece_id):
        return True
    return other.parent_piece_id == piece.id


def pick(matrix: Matrix, order: np.ndarray, target: Piece, wanted, limit: int, distances: np.ndarray, target_difficulty: float) -> list:
    chosen: list = []
    per_composer: dict = {}
    for index in order:
        other = matrix.pieces[matrix.ids[index]]
        if related(target, other) or not wanted(matrix.difficulty[index]):
            continue
        key = other.composer_id
        if per_composer.get(key, 0) >= PER_COMPOSER:
            continue
        per_composer[key] = per_composer.get(key, 0) + 1
        chosen.append(describe(other, target_difficulty, float(distances[index])))
        if len(chosen) >= limit:
            break
    return chosen


async def similar_by_vector(session: AsyncSession, piece: Piece, *, direction: str = "easier", limit: int = DEFAULT_LIMIT, gap: float = MIN_GAP) -> Optional[dict]:
    matrix = await load_matrix(session)
    here = matrix.index_of(piece.id)
    if here is None or piece.difficulty_score is None:
        return None
    target = float(piece.difficulty_score)
    distances = np.linalg.norm(matrix.vectors - matrix.vectors[here], axis=1)
    order = np.argsort(distances, kind="stable")
    result = {"basis": "vectors", "piece_id": piece.id, "difficulty": round(target, 1)}
    if direction in ("easier", "both"):
        result["easier"] = pick(matrix, order, piece, lambda value: value <= target - gap, limit, distances, target)
    if direction in ("harder", "both"):
        result["harder"] = pick(matrix, order, piece, lambda value: value >= target + gap, limit, distances, target)
    return result


async def similar_by_techniques(session: AsyncSession, piece: Piece, *, direction: str = "easier", limit: int = DEFAULT_LIMIT, gap: float = MIN_GAP) -> dict:
    from app.services.public_pages import load_catalogue, similar_pieces as technique_neighbours

    catalogue = await load_catalogue(session)
    listed = catalogue.pieces.get(piece.id)
    result = {"basis": "techniques", "piece_id": piece.id, "difficulty": round(float(piece.difficulty_score), 1) if piece.difficulty_score is not None else None}
    if listed is None or piece.difficulty_score is None:
        result.update({"easier": [], "harder": []} if direction == "both" else {direction: []})
        return result
    target = float(piece.difficulty_score)
    ranked = technique_neighbours(listed, catalogue, limit=60)
    for side, test in (("easier", lambda value: value <= target - gap), ("harder", lambda value: value >= target + gap)):
        if direction in (side, "both"):
            rows = [{**item, "difference": round(item["difficulty"] - target, 1)} for item in ranked if test(item["difficulty"])]
            result[side] = rows[:limit]
    return result


async def similar_pieces(session: AsyncSession, piece_id: int, *, direction: str = "easier", limit: int = DEFAULT_LIMIT) -> dict:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
    limit = min(max(limit, 1), MAX_LIMIT)
    piece = (
        await session.execute(select(Piece).options(selectinload(Piece.composer)).where(Piece.id == piece_id, Piece.hidden_at.is_(None)))
    ).scalar_one_or_none()
    if piece is None:
        raise LookupError("piece not found")
    found = await similar_by_vector(session, piece, direction=direction, limit=limit)
    if found is None:
        found = await similar_by_techniques(session, piece, direction=direction, limit=limit)
    return await without_hidden(session, found)


async def without_hidden(session: AsyncSession, found: dict) -> dict:
    ids = [item["id"] for side in ("easier", "harder") for item in found.get(side, [])]
    if not ids:
        return found
    hidden = set((await session.execute(select(Piece.id).where(Piece.id.in_(ids), Piece.hidden_at.is_not(None)))).scalars().all())
    for side in ("easier", "harder"):
        if side in found:
            found[side] = [item for item in found[side] if item["id"] not in hidden]
    return found
