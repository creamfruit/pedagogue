from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import session_scope
from app.models.models import (
    GenerationStatus,
    Passage,
    PassageSource,
    Piece,
    PieceTechnique,
    Technique,
)
from app.services import ai
from app.services.difficulty import compute_difficulty_score, compute_mechanical_load
from app.services.metadata_generator import MetadataGenerator

logger = logging.getLogger("piano.metadata")

PURPOSE = "piece_metadata"
HARD_BAR_LABEL = "Hard bar"


def subject_key(piece_id: int) -> str:
    return f"piece:{piece_id}"


async def load_piece(session: AsyncSession, piece_id: int) -> Optional[Piece]:
    stmt = (
        select(Piece)
        .options(selectinload(Piece.composer), selectinload(Piece.genre))
        .where(Piece.id == piece_id)
    )
    return (await session.execute(stmt)).scalars().one_or_none()


async def lock_unapplied(session: AsyncSession, piece_id: int) -> Optional[Piece]:
    stmt = select(Piece).where(Piece.id == piece_id).with_for_update().execution_options(populate_existing=True)
    piece = (await session.execute(stmt)).scalar_one_or_none()
    if piece is None or piece.metadata_generated_at is not None:
        return None
    return piece


async def apply_metadata(session: AsyncSession, piece_id: int, generated: dict, techniques: list[Technique]) -> bool:
    piece = await lock_unapplied(session, piece_id)
    if piece is None:
        return False
    by_id = {technique.id: technique for technique in techniques}
    links = [item for item in generated["techniques"] if item["technique_id"] in by_id]
    await session.execute(delete(PieceTechnique).where(PieceTechnique.piece_id == piece.id))
    for item in links:
        session.add(PieceTechnique(piece_id=piece.id, technique_id=item["technique_id"], weight=item["weight"]))

    await session.execute(
        delete(Passage).where(
            Passage.piece_id == piece.id,
            Passage.source == PassageSource.CATALOG,
            Passage.label == HARD_BAR_LABEL,
        )
    )
    for bar in sorted(set(generated["hard_bars"]))[:6]:
        if bar > 0:
            session.add(
                Passage(
                    piece_id=piece.id,
                    start_measure=bar,
                    end_measure=bar,
                    label=HARD_BAR_LABEL,
                    source=PassageSource.CATALOG,
                )
            )

    mechanical_load = compute_mechanical_load(
        [(by_id[item["technique_id"]].name, item["weight"]) for item in links],
        {technique.name: float(technique.load_factor) for technique in techniques},
    )
    piece.mechanical_load = mechanical_load
    piece.difficulty_score = compute_difficulty_score(mechanical_load, piece.duration_sec, len(links))
    for field in ("historical_note", "fun_fact", "syllabus_grade", "mood", "scene"):
        if generated.get(field):
            setattr(piece, field, generated[field])
    piece.metadata_generated_at = datetime.now(timezone.utc)
    piece.metadata_generation_model = generated.get("model")
    return True


async def generate_piece_metadata(piece_id: int) -> Optional[str]:
    async with session_scope() as session:
        piece = await load_piece(session, piece_id)
        if piece is None:
            logger.warning("piece %s vanished before metadata generation", piece_id)
            return None
        if piece.metadata_generated_at is not None:
            return "already generated"

        techniques = list((await session.execute(select(Technique))).scalars().all())
        generator = MetadataGenerator(techniques)
        args = (
            piece.title,
            piece.composer.name if piece.composer else None,
            piece.genre.name if piece.genre else None,
            piece.duration_sec,
        )

        generation = await ai.claim(session, PURPOSE, subject_key(piece_id))
        if generation is None:
            prior = await ai.existing(session, PURPOSE, subject_key(piece_id))
            if prior is not None and prior.status == GenerationStatus.DONE and prior.output is not None:
                generated = generator.normalize(prior.output)
                generated["model"] = prior.model
                await apply_metadata(session, piece_id, generated, techniques)
                return "re-applied stored output"
            return "claimed elsewhere"

        if not ai.ai_enabled():
            generated = generator.generate_heuristic(*args)
            ai.finish(generation, output=None, model=generated["model"])
            await apply_metadata(session, piece_id, generated, techniques)
            return generated["model"]

        try:
            generated, completion = await generator.generate_with_claude(*args)
        except Exception as error:
            logger.exception("metadata generation failed for piece %s", piece_id)
            ai.fail(generation, error)
            fallback = generator.generate_heuristic(*args)
            for field in ("historical_note", "fun_fact", "syllabus_grade", "mood", "scene"):
                fallback[field] = None
            await apply_metadata(session, piece_id, fallback, techniques)
            return "failed"
        ai.finish(generation, completion)
        await apply_metadata(session, piece_id, generated, techniques)
        return completion.model
