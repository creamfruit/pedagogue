from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Composer,
    Genre,
    LinkType,
    Passage,
    PassageTechnique,
    Piece,
    PieceLinkNote,
    PassageSource,
    PieceTechnique,
    Technique,
)
from app.services.difficulty import difficulty_band, mastery_for, personalize_difficulty
from app.services.onboarding import BaseService

PIECE_LOADERS = (
    selectinload(Piece.composer).selectinload(Composer.era),
    selectinload(Piece.genre),
    selectinload(Piece.load_profile),
    selectinload(Piece.technique_links).selectinload(PieceTechnique.technique),
    selectinload(Piece.passages).selectinload(Passage.technique_links).selectinload(PassageTechnique.technique),
    selectinload(Piece.movements),
    selectinload(Piece.parent_piece),
)


def pick_technique_examples(links: list[PassageTechnique]) -> dict[int, PassageTechnique]:
    best: dict[int, PassageTechnique] = {}
    for link in links:
        current = best.get(link.technique_id)
        rank = (float(link.weight), float(link.passage.difficulty_score or 0), -link.passage_id)
        if current is None or rank > (
            float(current.weight),
            float(current.passage.difficulty_score or 0),
            -current.passage_id,
        ):
            best[link.technique_id] = link
    return best


class TechniqueExampleService(BaseService):
    async def examples(self) -> list[dict]:
        stmt = (
            select(PassageTechnique)
            .join(Passage, Passage.id == PassageTechnique.passage_id)
            .join(Piece, Piece.id == Passage.piece_id)
            .where(Passage.source == PassageSource.CATALOG, Piece.is_user_created.is_(False))
            .options(
                selectinload(PassageTechnique.technique),
                selectinload(PassageTechnique.passage).selectinload(Passage.piece).selectinload(Piece.composer),
            )
        )
        links = list((await self.session.execute(stmt)).scalars().all())
        chosen = pick_technique_examples(links)
        return [
            {
                "technique_id": link.technique_id,
                "technique_name": link.technique.name,
                "passage_id": link.passage_id,
                "piece_id": link.passage.piece_id,
                "piece_title": link.passage.piece.title,
                "composer": link.passage.piece.composer.name if link.passage.piece.composer else None,
                "label": link.passage.label,
                "measure_span": link.passage.measure_span,
                "description": link.passage.description,
                "practice_cue": link.passage.practice_cue,
                "weight": link.weight,
                "difficulty_score": link.passage.difficulty_score,
            }
            for link in sorted(chosen.values(), key=lambda link: link.technique_id)
        ]


class PieceOverviewService(BaseService):
    async def load(self, piece_id: int) -> Piece:
        stmt = select(Piece).options(*PIECE_LOADERS).where(Piece.id == piece_id)
        piece = (await self.session.execute(stmt)).scalars().unique().one_or_none()
        if piece is None:
            raise LookupError("piece not found")
        return piece

    async def overview(self, piece_id: int, user=None) -> dict:
        piece = await self.load(piece_id)
        profiles = await self.profiles_for(user) if user is not None else {}
        return self.render(piece, profiles)

    async def profiles_for(self, user) -> dict[int, "UserTechniqueProfile"]:
        from app.models.models import UserTechniqueProfile

        stmt = select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return {row.technique_id: row for row in rows}

    def render(self, piece: Piece, profiles: Optional[dict] = None) -> dict:
        profiles = profiles or {}
        composer = piece.composer
        sections = [self.section(passage) for passage in piece.hardest_passages]
        techniques = [self.technique(link, profiles) for link in piece.hardest_techniques]
        technique_weights = {link.technique_id: float(link.weight) for link in piece.technique_links}
        personalized = personalize_difficulty(piece.difficulty_score, technique_weights, profiles)
        return {
            "id": piece.id,
            "title": piece.title,
            "catalog_number": piece.catalog_number,
            "key_signature": piece.key_signature,
            "year_composed": piece.year_composed,
            "tempo_marking": piece.tempo_marking,
            "difficulty_score": piece.difficulty_score,
            "mechanical_load": piece.mechanical_load,
            "personalized_difficulty": personalized,
            "difficulty_band": difficulty_band(piece.difficulty_score),
            "syllabus_grade": piece.syllabus_grade,
            "requires_verification": piece.requires_verification,
            "is_custom": piece.is_custom,
            "external_source": piece.external_source,
            "duration_sec": piece.duration_sec,
            "duration_label": piece.duration_label,
            "genre": piece.genre.name if piece.genre else None,
            "era": piece.era_name,
            "mood": piece.mood,
            "scene": piece.scene,
            "historical_note": piece.historical_note,
            "fun_fact": piece.fun_fact,
            "composer": self.composer(composer) if composer else None,
            "sections": sections,
            "techniques": techniques,
            "load_profile": self.load_profile(piece),
            "movements": [
                {
                    "id": movement.id,
                    "title": movement.title,
                    "movement_number": movement.movement_number,
                    "difficulty_score": movement.difficulty_score,
                    "duration_label": movement.duration_label,
                }
                for movement in sorted(piece.movements, key=lambda m: m.movement_number or 0)
            ],
            "parent_piece": (
                {"id": piece.parent_piece.id, "title": piece.parent_piece.title}
                if piece.parent_piece
                else None
            ),
        }

    @staticmethod
    def composer(composer: Composer) -> dict:
        return {
            "id": composer.id,
            "name": composer.name,
            "nationality": composer.nationality,
            "birth_year": composer.birth_year,
            "death_year": composer.death_year,
            "lifespan": composer.lifespan,
            "byline": composer.byline,
            "bio": composer.bio,
            "fun_fact": composer.fun_fact,
            "signature_sound": composer.signature_sound,
            "era": composer.era.name if composer.era else None,
        }

    @staticmethod
    def section(passage: Passage) -> dict:
        ranked = sorted(passage.technique_links, key=lambda link: float(link.weight), reverse=True)
        return {
            "id": passage.id,
            "label": passage.label,
            "start_measure": passage.start_measure,
            "end_measure": passage.end_measure,
            "measure_span": passage.measure_span,
            "length": passage.length,
            "difficulty_score": passage.difficulty_score,
            "description": passage.description,
            "practice_cue": passage.practice_cue,
            "techniques": [link.technique.name for link in ranked],
        }

    @staticmethod
    def technique(link: PieceTechnique, profiles: Optional[dict] = None) -> dict:
        technique = link.technique
        tier, color = mastery_for(technique.id, profiles or {})
        return {
            "id": technique.id,
            "name": technique.name,
            "category": technique.category,
            "weight": link.weight,
            "load_factor": technique.load_factor,
            "description": technique.description,
            "mechanic": technique.mechanic,
            "common_fault": technique.common_fault,
            "mastery_tier": tier,
            "mastery_color": color,
        }

    @staticmethod
    def load_profile(piece: Piece) -> Optional[dict]:
        profile = piece.load_profile
        if profile is None:
            return None
        return {
            "octave_density": profile.octave_density,
            "max_stretch_semitones": profile.max_stretch_semitones,
            "max_stretch_cm": profile.max_stretch_cm(),
            "repeated_chord_density": profile.repeated_chord_density,
            "notes_per_second_peak": profile.notes_per_second_peak,
            "load_index": profile.load_index,
        }


class LinkExplainer(BaseService):
    SHARED_FLOOR = 0.25

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.overviews = PieceOverviewService(session)

    async def explain(self, source_id: int, target_id: int, link_type: str) -> dict:
        try:
            kind = LinkType(link_type)
        except ValueError as exc:
            raise ValueError(f"unknown link type: {link_type}") from exc
        if source_id == target_id:
            raise ValueError("a piece cannot link to itself")

        source = await self.overviews.load(source_id)
        target = await self.overviews.load(target_id)
        note = await self.note(source_id, target_id, kind)

        if kind is LinkType.TECHNIQUE:
            body = self.technique_body(source, target)
        elif kind is LinkType.COMPOSER:
            body = self.composer_body(source, target)
        else:
            body = self.era_genre_body(source, target)

        return {
            "link_type": kind,
            "source": self.stub(source),
            "target": self.stub(target),
            "headline": (note.headline if note and note.headline else body["headline"]),
            "summary": (note.summary if note else body["summary"]),
            "curated": note is not None,
            "shared_techniques": body.get("shared_techniques", []),
            "shared_sections": body.get("shared_sections", []),
            "facts": body.get("facts", []),
        }

    async def note(self, a: int, b: int, kind: LinkType) -> Optional[PieceLinkNote]:
        low, high = PieceLinkNote.order_pair(a, b)
        stmt = select(PieceLinkNote).where(
            PieceLinkNote.low_piece_id == low,
            PieceLinkNote.high_piece_id == high,
            PieceLinkNote.link_type == kind,
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    @staticmethod
    def stub(piece: Piece) -> dict:
        return {
            "id": piece.id,
            "title": piece.title,
            "composer": piece.composer.name if piece.composer else None,
            "difficulty_score": piece.difficulty_score,
            "era": piece.era_name,
            "genre": piece.genre.name if piece.genre else None,
        }

    def technique_body(self, source: Piece, target: Piece) -> dict:
        left = {link.technique_id: link for link in source.technique_links}
        right = {link.technique_id: link for link in target.technique_links}
        shared = []
        for technique_id, a_link in left.items():
            b_link = right.get(technique_id)
            if b_link is None:
                continue
            pair_weight = min(float(a_link.weight), float(b_link.weight))
            if pair_weight < self.SHARED_FLOOR:
                continue
            technique = a_link.technique
            shared.append(
                {
                    "id": technique.id,
                    "name": technique.name,
                    "category": technique.category,
                    "mechanic": technique.mechanic,
                    "common_fault": technique.common_fault,
                    "load_factor": technique.load_factor,
                    "source_weight": a_link.weight,
                    "target_weight": b_link.weight,
                    "pair_weight": round(pair_weight, 2),
                }
            )
        shared.sort(key=lambda row: float(row["pair_weight"]) * float(row["load_factor"]), reverse=True)

        sections = self.shared_sections(source, target, {row["id"] for row in shared})
        if not shared:
            return {
                "headline": "Loosely related",
                "summary": (
                    f"{source.title} and {target.title} sit close in the technique space without "
                    "sharing any one demand strongly. The engine drew this line from the overall "
                    "shape of their technique profiles."
                ),
                "shared_techniques": [],
                "shared_sections": sections,
                "facts": [],
            }

        lead = shared[0]
        names = [row["name"].lower() for row in shared[:3]]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
        headline = f"Both live on {lead['name'].lower()}"
        summary = (
            f"{source.title} and {target.title} share {listed}. "
            f"{lead['name']} carries the most weight in both: "
            f"{float(lead['source_weight']):.0%} of the demand in {source.title} and "
            f"{float(lead['target_weight']):.0%} in {target.title}."
        )
        if lead["mechanic"]:
            summary += f" {lead['mechanic']}"
        if lead["common_fault"]:
            summary += f" The usual failure in both: {lead['common_fault'][0].lower()}{lead['common_fault'][1:]}"
        facts = [
            f"Shared demands: {len(shared)}",
            f"Difficulty gap: {self.gap(source, target)}",
        ]
        return {
            "headline": headline,
            "summary": summary,
            "shared_techniques": shared,
            "shared_sections": sections,
            "facts": facts,
        }

    @staticmethod
    def shared_sections(source: Piece, target: Piece, technique_ids: set[int]) -> list[dict]:
        rows = []
        for piece in (source, target):
            for passage in piece.hardest_passages:
                hits = [
                    link.technique.name
                    for link in passage.technique_links
                    if link.technique_id in technique_ids
                ]
                if not hits:
                    continue
                rows.append(
                    {
                        "piece_id": piece.id,
                        "piece_title": piece.title,
                        "label": passage.label,
                        "measure_span": passage.measure_span,
                        "difficulty_score": passage.difficulty_score,
                        "description": passage.description,
                        "techniques": hits,
                    }
                )
        return rows[:6]

    def composer_body(self, source: Piece, target: Piece) -> dict:
        composer = source.composer
        name = composer.name if composer else "the same composer"
        summary = f"Both were written by {name}."
        if composer and composer.signature_sound:
            summary += f" {composer.signature_sound}"
        if composer and composer.bio:
            summary += f" {composer.bio}"
        facts = []
        if composer and composer.lifespan:
            facts.append(f"{name}: {composer.lifespan}")
        years = [p.year_composed for p in (source, target) if p.year_composed]
        if len(years) == 2:
            span = abs(years[0] - years[1])
            if span == 0:
                facts.append(f"Both written in {years[0]}")
            elif span == 1:
                facts.append(f"Written {min(years)} and {max(years)}, a year apart")
            else:
                facts.append(f"Written {min(years)} and {max(years)}, {span} years apart")
        facts.append(f"Difficulty gap: {self.gap(source, target)}")
        return {"headline": f"Both by {name}", "summary": summary, "facts": facts}

    def era_genre_body(self, source: Piece, target: Piece) -> dict:
        if source.era_name and source.era_name == target.era_name:
            summary = (
                f"{source.title} and {target.title} both come out of the {source.era_name} period, "
                "so they expect the same pedalling habits, rubato and tone."
            )
            headline = f"Both {source.era_name}"
        elif source.genre and target.genre and source.genre_id == target.genre_id:
            summary = (
                f"Both are written as a {source.genre.name.lower()}, so they follow the same "
                "conventions of form and pacing even though they come from different hands."
            )
            headline = f"Both a {source.genre.name.lower()}"
        else:
            summary = f"{source.title} and {target.title} share a period or genre tag."
            headline = "Same family"
        facts = []
        if source.genre and target.genre:
            facts.append(f"{source.genre.name} · {target.genre.name}")
        facts.append(f"Difficulty gap: {self.gap(source, target)}")
        return {"headline": headline, "summary": summary, "facts": facts}

    @staticmethod
    def gap(source: Piece, target: Piece) -> str:
        if source.difficulty_score is None or target.difficulty_score is None:
            return "unknown"
        delta = abs(float(source.difficulty_score) - float(target.difficulty_score))
        return f"{delta:.1f} points"


class CatalogSearchService(BaseService):
    async def techniques(self) -> list[Technique]:
        result = await self.session.execute(select(Technique).order_by(Technique.name))
        return list(result.scalars().all())

    async def by_title(self, term: str, limit: int = 20) -> list[Piece]:
        stmt = (
            select(Piece)
            .options(*PIECE_LOADERS)
            .join(Composer, Piece.composer_id == Composer.id, isouter=True)
            .join(Genre, Piece.genre_id == Genre.id, isouter=True)
            .where(or_(Piece.title.ilike(f"%{term}%"), Composer.name.ilike(f"%{term}%")))
            .order_by(Piece.difficulty_score)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())
