from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from app.core.config import settings

SOURCE_NAMES = {
    "mutopia": ("Mutopia Project", "https://www.mutopiaproject.org"),
    "openscore-lieder": ("OpenScore Lieder Corpus", "https://musescore.com/openscore-lieder-corpus"),
}


def report_link(piece_id: int, title: str, source_url: Optional[str] = None, base: Optional[str] = None) -> str:
    base = base or settings.report_problem_url
    subject = f"Problem with {title} (piece {piece_id})"
    lines = ["What is wrong with this piece?", "", "", f"Piece: {title}", f"Pedagogue piece id: {piece_id}"]
    if source_url:
        lines.append(f"Source: {source_url}")
    body = "\n".join(lines)
    if base.startswith("mailto:"):
        return f"{base}?subject={quote(subject)}&body={quote(body)}"
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}title={quote(subject)}&body={quote(body)}"


def harvest_credit(piece, record=None) -> Optional[dict]:
    record = record or getattr(piece, "harvest", None)
    if record is None:
        return None
    name, home = SOURCE_NAMES.get(record.source, (record.source, record.source_url))
    composer = getattr(piece, "composer", None)
    return {
        "source": record.source,
        "source_name": name,
        "source_url": record.source_url or home,
        "licence_code": record.licence_code,
        "licence_name": record.licence_name,
        "licence_url": record.licence_url,
        "composer": record.composer_name,
        "composer_lifespan": composer.lifespan if composer is not None and composer.lifespan else None,
        "attribution": record.attribution,
        "report_url": report_link(piece.id, piece.title, record.source_url),
    }


HARVEST_MODEL = "harvest-1"


async def find_counterpart(session, piece, composer_name: Optional[str]):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Composer, Piece, PieceSource
    from app.services.catalog_match import composer_surname, same_work

    if not composer_name:
        return None
    surname = composer_surname(composer_name)
    rows = (
        await session.execute(
            select(Piece)
            .join(PieceSource, PieceSource.piece_id == Piece.id)
            .join(Composer, Composer.id == Piece.composer_id)
            .where(Piece.id != piece.id, Piece.hidden_at.is_(None), Piece.difficulty_score.is_not(None))
            .options(selectinload(Piece.composer), selectinload(Piece.technique_links), selectinload(Piece.passages))
        )
    ).scalars().unique().all()
    wanted = f"{piece.title} {piece.catalog_number or ''}"
    found = [
        other
        for other in rows
        if other.composer is not None
        and composer_surname(other.composer.name) == surname
        and same_work(f"{other.title} {other.catalog_number or ''}", composer_name, wanted, composer_name)
    ]
    return found[0] if len(found) == 1 else None


async def attach_harvest(session, piece, composer_name: Optional[str]) -> bool:
    from sqlalchemy import delete, select

    from app.models.models import Passage, PassageSource, PassageTechnique, Piece, PieceSource, PieceTechnique
    from app.services.difficulty import difficulty_band
    from app.services.metadata_generator import GRADE_BY_BAND
    from app.services.repertoire_reference import lookup
    from app.services.score_library import find_entries

    if await session.get(PieceSource, piece.id) is not None:
        return False
    if lookup(piece.title, composer_name, piece.catalog_number) is not None or find_entries(piece.title, composer_name, piece.catalog_number):
        return False
    lender = await find_counterpart(session, piece, composer_name)
    if lender is None:
        return False
    piece.harvest_piece_id = lender.id
    piece.difficulty_score = lender.difficulty_score
    piece.mechanical_load = lender.mechanical_load
    piece.metadata_generation_model = HARVEST_MODEL
    piece.syllabus_grade = GRADE_BY_BAND.get(difficulty_band(lender.difficulty_score))
    if lender.technique_links:
        await session.execute(delete(PieceTechnique).where(PieceTechnique.piece_id == piece.id))
        for link in lender.technique_links:
            session.add(PieceTechnique(piece_id=piece.id, technique_id=link.technique_id, weight=link.weight))
    has_passages = (await session.execute(select(Passage.id).where(Passage.piece_id == piece.id).limit(1))).first() is not None
    if not has_passages:
        for row in lender.passages:
            if row.source != PassageSource.HARVEST:
                continue
            copy = Passage(
                piece_id=piece.id,
                start_measure=row.start_measure,
                end_measure=row.end_measure,
                label=row.label,
                description=row.description,
                practice_cue=row.practice_cue,
                difficulty_score=row.difficulty_score,
                source=PassageSource.HARVEST,
                image_key=row.image_key,
            )
            session.add(copy)
            copy.technique_links = [PassageTechnique(technique_id=link.technique_id, weight=link.weight) for link in await passage_links(session, row.id)]
    await session.flush()
    await session.refresh(piece, ["technique_links"])
    return True


async def passage_links(session, passage_id: int) -> list:
    from sqlalchemy import select

    from app.models.models import PassageTechnique

    return list((await session.execute(select(PassageTechnique).where(PassageTechnique.passage_id == passage_id))).scalars().all())
