from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Composer, PassageSource, Piece, PieceTechnique
from app.services.catalog import PieceOverviewService, borrowed_record, difficulty_basis
from app.services.difficulty import difficulty_band
from app.services.family_tree import affinity, context, shared_techniques
from app.services.harvest_library import harvest_credit
from app.services.onboarding import BaseService
from app.services.progression import cosine

INDEX_SECONDS = 600
SIMILAR_LIMIT = 5
STEP_LIMIT = 4
SIMILAR_PER_COMPOSER = 2
SIMILAR_FLOOR = 0.25
SECTION_LIMIT = 5
TECHNIQUE_LIMIT = 6
SLUG_LENGTH = 70

BASIS_WORDS = {
    "reference": "Pedagogue's reference ladder, a hand-written ranking of well-known pieces.",
    "library": "measurements taken from the first-edition score: bar counts, note density, hand stretch and the hardest bars.",
    "harvest": "measurements taken from an open score of the piece (note density, hand span, leaps, octaves and fast runs), calibrated against Pedagogue's reference ladder.",
    "estimate": "an estimate from the piece's title and composer. It has not been measured against the score, so treat it as a guide.",
    "generated": "a generated estimate from the piece's details. It has not been measured against the score, so treat it as a guide.",
    "catalogue": "Pedagogue's catalogue entry for the piece.",
}

BAND_WORDS = {
    "beginner": "a beginner piece",
    "early intermediate": "an early intermediate piece",
    "intermediate": "an intermediate piece",
    "late intermediate": "a late intermediate piece",
    "advanced": "an advanced piece",
    "virtuoso": "a virtuoso piece",
    "unrated": "not yet rated",
}

PUBLIC_PIECE = and_(
    Piece.is_user_created.is_(False),
    Piece.hidden_at.is_(None),
    Piece.difficulty_score.is_not(None),
    Piece.composer_id.is_not(None),
)


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def slugify(text: str, limit: int = SLUG_LENGTH) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(text).lower()).strip("-")
    return slug[:limit].strip("-")


def piece_slug(piece: Piece) -> str:
    return piece_slug_for(piece, piece.composer)


def composer_slug(composer: Composer) -> str:
    return f"{composer.id}-{slugify(composer.name)}".rstrip("-")


def parse_slug(value: str) -> Optional[int]:
    found = re.match(r"^(\d{1,9})(?:-|$)", value or "")
    return int(found.group(1)) if found else None


def short_name(composer_name: str) -> str:
    return composer_name.split(",")[0].split()[-1] if composer_name else ""


def trimmed(text: Optional[str], limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:.")
    return f"{cut}…"


def full_title(piece: Piece) -> str:
    label = piece.title if not piece.catalog_number or piece.catalog_number in piece.title else f"{piece.title}, {piece.catalog_number}"
    return f"{piece.composer.name}: {label}" if piece.composer else label


def is_wikipedia(piece: Piece) -> bool:
    return bool(piece.reference_url and (piece.reference_label or "").lower().startswith("wikipedia"))


@dataclass
class Catalogue:
    built_at: float
    pieces: dict[int, Piece]
    vectors: dict[int, dict[int, float]]
    technique_names: dict[int, str]
    era_rank: dict[int, int]
    difficulties: list[float]
    composers: dict[int, Composer] = field(default_factory=dict)

    def percentile(self, score: float) -> int:
        if not self.difficulties:
            return 0
        below = sum(1 for value in self.difficulties if value < score)
        return round(100 * below / len(self.difficulties))

    def by_composer(self, composer_id: int) -> list[Piece]:
        found = [piece for piece in self.pieces.values() if piece.composer_id == composer_id and piece.parent_piece_id is None]
        return sorted(found, key=lambda piece: (float(piece.difficulty_score), piece.title))


_cache: dict[str, Catalogue] = {}


def forget_catalogue() -> None:
    _cache.clear()


async def load_catalogue(session: AsyncSession, *, fresh: bool = False) -> Catalogue:
    held = _cache.get("catalogue")
    if held and not fresh and time.monotonic() - held.built_at < INDEX_SECONDS:
        return held
    from app.models.models import Era

    rows = (
        await session.execute(
            select(Piece)
            .options(
                selectinload(Piece.composer).selectinload(Composer.era),
                selectinload(Piece.genre),
                selectinload(Piece.technique_links).selectinload(PieceTechnique.technique),
                selectinload(Piece.load_profile),
            )
            .where(PUBLIC_PIECE)
            .order_by(Piece.id)
        )
    ).scalars().unique().all()
    eras = (await session.execute(select(Era).order_by(Era.start_year))).scalars().all()
    pieces = {piece.id: piece for piece in rows}
    vectors = {piece.id: {link.technique_id: float(link.weight) for link in piece.technique_links} for piece in rows}
    names = {link.technique_id: link.technique.name for piece in rows for link in piece.technique_links}
    composers = {piece.composer.id: piece.composer for piece in rows if piece.composer}
    built = Catalogue(
        built_at=time.monotonic(),
        pieces=pieces,
        vectors=vectors,
        technique_names=names,
        era_rank={era.id: rank for rank, era in enumerate(eras)},
        difficulties=sorted(float(piece.difficulty_score) for piece in rows),
        composers=composers,
    )
    _cache["catalogue"] = built
    return built


def similar_pieces(piece: Piece, catalogue: Catalogue, limit: int = SIMILAR_LIMIT) -> list[dict]:
    mine = catalogue.vectors.get(piece.id, {})
    ranked = []
    for other in catalogue.pieces.values():
        if other.id == piece.id or other.parent_piece_id is not None and other.parent_piece_id == piece.parent_piece_id:
            continue
        if other.id == piece.parent_piece_id or other.parent_piece_id == piece.id:
            continue
        technique = cosine(mine, catalogue.vectors.get(other.id, {}))
        shared_context, reasons = context(piece, other, catalogue.era_rank)
        score = affinity(technique, shared_context)
        if score >= SIMILAR_FLOOR:
            ranked.append((score, other, reasons))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    chosen: list[dict] = []
    per_composer: dict[Optional[int], int] = {}
    for score, other, reasons in ranked:
        if per_composer.get(other.composer_id, 0) >= SIMILAR_PER_COMPOSER:
            continue
        per_composer[other.composer_id] = per_composer.get(other.composer_id, 0) + 1
        shared = shared_techniques(catalogue.vectors.get(piece.id, {}), catalogue.vectors.get(other.id, {}), catalogue.technique_names)
        chosen.append(
            {
                "id": other.id,
                "slug": piece_slug(other),
                "title": other.title,
                "full_title": full_title(other),
                "composer": other.composer.name if other.composer else None,
                "difficulty": float(other.difficulty_score),
                "band": difficulty_band(other.difficulty_score),
                "shared_techniques": shared,
                "reasons": reasons,
            }
        )
        if len(chosen) >= limit:
            break
    return chosen


def hardest_sections(piece: Piece) -> list[dict]:
    sections = []
    for passage in piece.hardest_passages:
        if passage.source not in (PassageSource.CATALOG, PassageSource.HARVEST) or not passage.description:
            continue
        sections.append(PieceOverviewService.section(passage))
        if len(sections) >= SECTION_LIMIT:
            break
    return sections


def technique_rows(piece: Piece) -> list[dict]:
    rows = []
    for link in piece.hardest_techniques[:TECHNIQUE_LIMIT]:
        technique = link.technique
        rows.append(
            {
                "name": technique.name,
                "weight": float(link.weight),
                "description": technique.description,
                "mechanic": technique.mechanic,
                "common_fault": technique.common_fault,
            }
        )
    return rows


def difficulty_summary(piece: Piece, catalogue: Catalogue) -> dict:
    score = float(piece.difficulty_score)
    band = difficulty_band(piece.difficulty_score)
    basis = difficulty_basis(piece)
    return {
        "score": round(score, 1),
        "band": band,
        "band_phrase": BAND_WORDS.get(band, band),
        "grade": piece.syllabus_grade,
        "basis": basis,
        "basis_text": BASIS_WORDS.get(basis, BASIS_WORDS["catalogue"]),
        "measured": basis in {"reference", "library", "harvest"},
        "harder_than": catalogue.percentile(score),
        "mechanical_load": float(piece.mechanical_load) if piece.mechanical_load is not None else None,
    }


def story_for(piece: Piece) -> dict:
    note = (piece.historical_note or "").strip() or None
    wiki = is_wikipedia(piece) and note is not None
    return {
        "history": note,
        "from_wikipedia": wiki,
        "wikipedia_url": piece.reference_url if wiki else None,
        "wikipedia_label": (piece.reference_label or "").split(":", 1)[-1].strip() if wiki else None,
        "fun_fact": (piece.fun_fact or "").strip() or None,
        "mood": piece.mood,
        "scene": piece.scene,
    }


class PublicPieceService(BaseService):
    async def piece_page(self, piece_id: int) -> Optional[dict]:
        catalogue = await load_catalogue(self.session)
        listed = catalogue.pieces.get(piece_id)
        if listed is None:
            return None
        try:
            piece = await PieceOverviewService(self.session).load(piece_id)
        except LookupError:
            return None
        profile = piece.load_profile
        steps = await self.steps(piece_id)
        return {
            "piece": piece,
            "id": piece.id,
            "slug": piece_slug(listed),
            "title": piece.title,
            "full_title": full_title(piece),
            "composer": piece.composer,
            "composer_slug": composer_slug(piece.composer) if piece.composer else None,
            "key": piece.key_signature,
            "year": piece.year_composed,
            "tempo_marking": piece.tempo_marking,
            "duration": piece.duration_label if piece.duration_sec else None,
            "genre": piece.genre.name if piece.genre else None,
            "era": piece.era_name,
            "difficulty": difficulty_summary(piece, catalogue),
            "sections": hardest_sections(piece),
            "techniques": technique_rows(piece),
            "story": story_for(piece),
            "similar": similar_pieces(listed, catalogue),
            "easier": steps.get("easier", []),
            "harder": steps.get("harder", []),
            "load": {
                "octave_density": float(profile.octave_density) if profile and profile.octave_density is not None else None,
                "max_stretch_cm": profile.max_stretch_cm() if profile else None,
                "peak_notes_per_second": float(profile.notes_per_second_peak) if profile and profile.notes_per_second_peak is not None else None,
            },
            "movements": [
                {"id": movement.id, "title": movement.title, "number": movement.movement_number, "slug": piece_slug_for(movement, piece.composer), "listed": movement.id in catalogue.pieces}
                for movement in sorted(piece.movements, key=lambda item: item.movement_number or 0)
            ],
            "parent": (
                {"title": piece.parent_piece.title, "slug": piece_slug_for(piece.parent_piece, piece.composer), "listed": piece.parent_piece.id in catalogue.pieces}
                if piece.parent_piece
                else None
            ),
            "library_credit": (piece.metadata_generation_model or "").startswith("score-library"),
            "source": harvest_credit(piece, await borrowed_record(self.session, piece)),
            "updated": piece.metadata_generated_at,
        }

    async def steps(self, piece_id: int) -> dict:
        from app.services.similar import similar_pieces as by_difficulty

        try:
            return await by_difficulty(self.session, piece_id, direction="both", limit=STEP_LIMIT)
        except LookupError:
            return {}

    async def composer_page(self, composer_id: int) -> Optional[dict]:
        catalogue = await load_catalogue(self.session)
        composer = catalogue.composers.get(composer_id)
        if composer is None:
            return None
        works = catalogue.by_composer(composer_id)
        return {
            "composer": composer,
            "id": composer.id,
            "slug": composer_slug(composer),
            "works": [
                {
                    "id": piece.id,
                    "slug": piece_slug(piece),
                    "title": piece.title,
                    "full_title": full_title(piece),
                    "difficulty": float(piece.difficulty_score),
                    "band": difficulty_band(piece.difficulty_score),
                    "key": piece.key_signature,
                    "year": piece.year_composed,
                }
                for piece in works
            ],
            "easiest": works[0] if works else None,
            "hardest": works[-1] if works else None,
        }

    async def listing(self) -> dict:
        catalogue = await load_catalogue(self.session)
        groups = []
        for composer in sorted(catalogue.composers.values(), key=lambda item: fold(item.name).lower()):
            works = catalogue.by_composer(composer.id)
            if works:
                groups.append({"composer": composer, "slug": composer_slug(composer), "works": [{"slug": piece_slug(work), "title": work.title, "difficulty": float(work.difficulty_score), "band": difficulty_band(work.difficulty_score), "full_title": full_title(work)} for work in works]})
        return {"groups": groups, "count": sum(len(group["works"]) for group in groups)}

    async def sitemap_entries(self) -> dict:
        catalogue = await load_catalogue(self.session)
        return {
            "pieces": [(piece_slug(piece), piece.metadata_generated_at) for piece in sorted(catalogue.pieces.values(), key=lambda item: item.id)],
            "composers": [composer_slug(composer) for composer in sorted(catalogue.composers.values(), key=lambda item: item.id)],
        }


def piece_slug_for(piece: Piece, composer: Optional[Composer]) -> str:
    title = slugify(piece.title, 200)
    catalog = slugify(piece.catalog_number or "", 40)
    parts = [slugify(composer.name, 40) if composer else "", title]
    if catalog and catalog not in title:
        parts.append(catalog)
    return f"{piece.id}-{'-'.join(part for part in parts if part)[:SLUG_LENGTH].strip('-')}".rstrip("-")
