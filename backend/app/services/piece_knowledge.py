from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import session_scope
from app.models.models import Composer, Era, Passage, PassageSource, Piece, PieceTechnique, Technique
from app.services.difficulty import compute_mechanical_load, difficulty_band
from app.services.metadata_generator import GRADE_BY_BAND, METADATA_MODEL_HEURISTIC, PLACEHOLDER_FACT
from app.services.repertoire_reference import (
    LADDER_VERSION,
    composer_facts,
    Reference,
    estimate_difficulty,
    heuristic_techniques,
    lookup,
)
from app.services.work_titles import parse_work_title

logger = logging.getLogger("piano.knowledge")

HARD_BAR_LABEL = "Hard bar"
TEMPLATE_HISTORY = re.compile(r"sits within the .* repertoire.*rewards patient, hands-separate study", re.DOTALL)
OLD_GRADE_LABELS = {
    "RCM 1-3 / ABRSM 1-2", "RCM 4-5 / ABRSM 3-4", "RCM 6-7 / ABRSM 5-6", "RCM 8-9 / ABRSM 7-8",
    "RCM 10 / ARCT / ABRSM 8+", "Professional / Concert repertoire", "Unrated",
}
GENERATED_GRADES = OLD_GRADE_LABELS | set(GRADE_BY_BAND.values())


def is_filler(text: Optional[str]) -> bool:
    if not text:
        return False
    return text.strip() == PLACEHOLDER_FACT or bool(TEMPLATE_HISTORY.search(text))


def is_offline_generated(piece: Piece) -> bool:
    model = piece.metadata_generation_model or ""
    return model.startswith("heuristic") or model.startswith("reference-ladder")


def apply_title_facts(piece: Piece, composer_name: Optional[str], *, rename: bool) -> Optional[Reference]:
    parsed = parse_work_title(piece.title)
    if not piece.catalog_number and parsed.catalog_number:
        piece.catalog_number = parsed.catalog_number
    if not piece.key_signature and parsed.key_signature:
        piece.key_signature = parsed.key_signature
    reference = lookup(piece.title, composer_name, piece.catalog_number)
    if rename:
        if reference and reference.title:
            piece.title = reference.title
        elif parsed.title != piece.title:
            piece.title = parsed.title
    if reference:
        if reference.key and not piece.key_signature:
            piece.key_signature = reference.key
        if reference.year and not piece.year_composed:
            piece.year_composed = reference.year
    return reference


def fill_story(piece: Piece, reference: Optional[Reference]) -> None:
    if is_filler(piece.fun_fact):
        piece.fun_fact = None
    if is_filler(piece.historical_note):
        piece.historical_note = None
    if reference:
        piece.historical_note = piece.historical_note or reference.history
        piece.fun_fact = piece.fun_fact or reference.fact


def grade_for(piece: Piece) -> None:
    if piece.syllabus_grade is None or piece.syllabus_grade in GENERATED_GRADES:
        piece.syllabus_grade = GRADE_BY_BAND.get(difficulty_band(piece.difficulty_score), "Unrated") if piece.difficulty_score is not None else None


async def replace_techniques(
    session: AsyncSession, piece: Piece, links: list[tuple[str, float]], techniques: dict[str, Technique]
) -> None:
    usable = [(name, weight) for name, weight in links if name in techniques]
    if not usable:
        return
    await session.execute(delete(PieceTechnique).where(PieceTechnique.piece_id == piece.id))
    for name, weight in usable:
        session.add(PieceTechnique(piece_id=piece.id, technique_id=techniques[name].id, weight=weight))
    piece.mechanical_load = compute_mechanical_load(
        usable, {name: float(t.load_factor) for name, t in techniques.items()}, piece.difficulty_score
    )


async def drop_invented_bars(session: AsyncSession, piece: Piece) -> None:
    await session.execute(
        delete(Passage).where(
            Passage.piece_id == piece.id,
            Passage.source == PassageSource.CATALOG,
            Passage.label == HARD_BAR_LABEL,
        )
    )


async def fill_composer(session: AsyncSession, composer: Composer, eras: Optional[dict[str, Era]] = None) -> bool:
    facts = composer_facts(composer.name)
    if facts is None:
        return False
    birth, death, nationality, era_name = facts
    if eras is None:
        eras = {era.name: era for era in (await session.execute(select(Era))).scalars().all()}
    changed = False
    if composer.birth_year is None:
        composer.birth_year, changed = birth, True
    if composer.death_year is None and death is not None:
        composer.death_year, changed = death, True
    if not composer.nationality:
        composer.nationality, changed = nationality, True
    if composer.era_id is None and era_name in eras:
        composer.era_id, changed = eras[era_name].id, True
    return changed


async def refresh_catalog_knowledge(session: AsyncSession) -> dict[str, int]:
    eras = {era.name: era for era in (await session.execute(select(Era))).scalars().all()}
    for composer in (await session.execute(select(Composer))).scalars().all():
        await fill_composer(session, composer, eras)
    techniques = {t.name: t for t in (await session.execute(select(Technique))).scalars().all()}
    pieces = (
        await session.execute(
            select(Piece).options(selectinload(Piece.composer), selectinload(Piece.technique_links))
        )
    ).scalars().all()
    names_by_id = {technique.id: name for name, technique in techniques.items()}
    factors = {name: float(technique.load_factor) for name, technique in techniques.items()}
    counts = {"ladder": 0, "estimated": 0, "cleaned": 0}
    for piece in pieces:
        if piece.is_user_created and piece.external_source is None:
            continue
        composer_name = piece.composer.name if piece.composer else None
        imported = piece.external_source is not None
        offline = is_offline_generated(piece)
        reference = apply_title_facts(piece, composer_name, rename=imported and offline)
        if reference:
            piece.difficulty_score = reference.score
            counts["ladder"] += 1
            if offline:
                await replace_techniques(session, piece, list(reference.techniques), techniques)
                piece.metadata_generation_model = LADDER_VERSION
        elif offline:
            piece.difficulty_score = estimate_difficulty(piece.title, composer_name)
            await replace_techniques(session, piece, heuristic_techniques(piece.title, composer_name), techniques)
            piece.metadata_generation_model = METADATA_MODEL_HEURISTIC
            counts["estimated"] += 1
        if offline:
            await drop_invented_bars(session, piece)
        elif piece.difficulty_score is not None:
            links = [(names_by_id.get(link.technique_id, ""), float(link.weight)) for link in piece.technique_links]
            piece.mechanical_load = compute_mechanical_load(links, factors, piece.difficulty_score)
        before = (piece.historical_note, piece.fun_fact)
        fill_story(piece, reference)
        if before != (piece.historical_note, piece.fun_fact):
            counts["cleaned"] += 1
        grade_for(piece)
    await session.flush()
    return counts


async def enrich_piece_facts(piece_id: int) -> Optional[str]:
    from app.services.wiki_facts import WikiFactsClient, looks_like_same_subject

    async with session_scope() as session:
        stmt = select(Piece).options(selectinload(Piece.composer)).where(Piece.id == piece_id)
        piece = (await session.execute(stmt)).scalars().one_or_none()
        if piece is None or piece.facts_checked_at is not None:
            return None
        title, composer_name, external_ref = piece.title, piece.composer.name if piece.composer else None, piece.external_ref
        piece.facts_checked_at = datetime.now(timezone.utc)
        await session.commit()

    if not settings.wiki_facts_enabled:
        return "disabled"
    try:
        fact = await WikiFactsClient().lookup(title=title, composer_name=composer_name, external_ref=external_ref)
    except Exception:
        logger.exception("wiki facts lookup failed for piece %s", piece_id)
        return "failed"
    if fact is None or not looks_like_same_subject(fact, composer_name):
        return "not found"

    async with session_scope() as session:
        piece = await session.get(Piece, piece_id)
        if piece is None:
            return None
        if not piece.historical_note or is_filler(piece.historical_note):
            piece.historical_note = fact.summary
            piece.reference_url = fact.url[:300]
            piece.reference_label = f"Wikipedia: {fact.title}"[:60]
        if fact.year and not piece.year_composed and 1500 < fact.year < 2100:
            piece.year_composed = fact.year
    return fact.url
