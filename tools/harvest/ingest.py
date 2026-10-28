import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from . import naming
from . import passages as passage_module
from .difficulty import Model
from .models import Candidate
from .workspace import Workspace

HARVEST_MODEL = "harvest-1"
FLUSH_EVERY = 50


@dataclass
class Context:
    eras: list
    genres: dict
    composers: list
    sources: dict
    catalogue: dict = field(default_factory=lambda: defaultdict(list))
    model: Optional[object] = None
    techniques: dict = field(default_factory=dict)
    storage: Optional[object] = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def provenance(candidate: Candidate) -> dict:
    extra = candidate.extra
    if candidate.source == "mutopia":
        maintainer = (extra.get("header") or {}).get("maintainer", "").strip()
        parts = [f"Typeset by {maintainer}" if maintainer else "", f"Edition: {extra['published']}" if extra.get("published") else "", "Mutopia Project (https://www.mutopiaproject.org)"]
        attribution = "; ".join(part for part in parts if part)
        urls = {kind: url for kind, url in candidate.files.items() if kind in {"ly", "lys", "mid"}}
        original = (extra.get("header") or {}).get("title") or candidate.title
    else:
        attribution = candidate.attribution
        urls = {"repository": extra.get("repository", ""), "musescore": candidate.source_url}
        original = f"{candidate.parent}: {candidate.title}" if candidate.parent else candidate.title
    died = date.fromisoformat(candidate.composer_died_on) if candidate.composer_died_on else None
    return {
        "source": candidate.source,
        "source_id": candidate.source_id,
        "source_url": candidate.source_url,
        "licence_code": candidate.licence.code,
        "licence_name": candidate.licence.name,
        "licence_url": candidate.licence.url,
        "composer_name": candidate.extra.get("composer_label") or candidate.composer,
        "composer_qid": candidate.composer_qid,
        "composer_died_on": died,
        "attribution": attribution,
        "original_title": original[:300],
        "file_urls": urls,
    }


def resolve_composer(context: Context, candidate: Candidate, session):
    from app.models.models import Composer
    from app.services.catalog_match import composer_surname, fold

    label = candidate.extra.get("composer_label") or candidate.composer
    wanted = fold(label)
    exact = next((composer for composer in context.composers if fold(composer.name) == wanted), None)
    if exact is not None:
        return exact
    surname = composer_surname(label)
    related = [
        composer
        for composer in context.composers
        if composer_surname(composer.name) == surname and (composer.birth_year is None or candidate.born is None or composer.birth_year == candidate.born)
    ]
    if len(related) == 1:
        return related[0]
    era = naming.era_for(context.eras, candidate.born)
    died = date.fromisoformat(candidate.composer_died_on).year if candidate.composer_died_on else candidate.died
    composer = Composer(name=label[:120], birth_year=candidate.born, death_year=died, era_id=era.id if era else None)
    session.add(composer)
    context.composers.append(composer)
    return composer


def first_key(features: dict) -> Optional[str]:
    signatures = features.get("key", {}).get("signatures") or []
    return naming.pretty_key(signatures[0]["key"]) if signatures else None


def new_piece(context: Context, candidate: Candidate, composer, payload: dict):
    from app.models.models import Piece
    from app.services.score_library import genre_for
    from app.services.work_titles import parse_work_title

    features = payload["features"]
    title = naming.piece_title(candidate.title, candidate.source)
    parsed = parse_work_title(title)
    genre = genre_for(title, context.genres)
    words = features["tempo"]["words"]
    return Piece(
        title=title,
        composer_id=composer.id,
        genre_id=genre.id if genre else None,
        catalog_number=naming.catalogue_number(candidate.catalog_number) or parsed.catalog_number,
        key_signature=parsed.key_signature or first_key(features),
        duration_sec=int(features["length"]["seconds"]) or None,
        tempo_marking=words[0].capitalize() if words else None,
        technique_vector=payload["vector"],
        external_source=candidate.source,
        external_ref=candidate.source_id,
        metadata_generated_at=context.now,
        metadata_generation_model=HARVEST_MODEL,
    )


def match_existing(context: Context, candidate: Candidate, composer):
    from app.services.catalog_match import composer_surname, same_work

    if candidate.source != "mutopia":
        return None
    surname = composer_surname(composer.name)
    wanted = f"{candidate.title} {candidate.catalog_number}"
    found = [
        piece
        for piece in context.catalogue.get(surname, [])
        if piece.harvest is None and same_work(f"{piece.title} {piece.catalog_number or ''}", composer.name, wanted, composer.name)
    ]
    return found[0] if len(found) == 1 else None


async def load_context(session) -> Context:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Composer, Era, Genre, Piece, PieceSource, Technique
    from app.services.catalog_match import composer_surname

    eras = list((await session.execute(select(Era))).scalars().all())
    genres = {genre.name: genre for genre in (await session.execute(select(Genre))).scalars().all()}
    composers = list((await session.execute(select(Composer))).scalars().all())
    sources = {
        (record.source, record.source_id): record
        for record in (await session.execute(select(PieceSource).options(selectinload(PieceSource.piece)))).scalars().all()
    }
    context = Context(eras, genres, composers, sources)
    context.techniques = {technique.name: technique for technique in (await session.execute(select(Technique))).scalars().all()}
    pieces = (
        await session.execute(
            select(Piece)
            .options(selectinload(Piece.composer), selectinload(Piece.harvest))
            .where(Piece.is_user_created.is_(False), Piece.parent_piece_id.is_(None))
        )
    ).scalars().all()
    for piece in pieces:
        if piece.composer is not None:
            context.catalogue[composer_surname(piece.composer.name)].append(piece)
    return context


def apply_features(piece, record, payload: dict, candidate: Candidate, context: Context) -> None:
    features = payload["features"]
    record.features = features
    record.feature_version = features["version"]
    record.content_hash = candidate.extra["content_hash"]
    record.updated_at = context.now
    piece.technique_vector = payload["vector"]
    if features["length"]["seconds"] and not piece.duration_sec:
        piece.duration_sec = int(features["length"]["seconds"])


def apply_difficulty(piece, record, features: dict, context: Context) -> None:
    from app.services.difficulty import difficulty_band
    from app.services.metadata_generator import GRADE_BY_BAND
    from app.services.repertoire_reference import lookup

    model = context.model
    computed = Decimal(str(model.score(features))) if model is not None else None
    record.computed_difficulty = computed
    record.calibration_version = model.version if model is not None else None
    reference = lookup(piece.title, record.composer_name, piece.catalog_number)
    if reference is not None:
        piece.difficulty_score = reference.score
    elif computed is not None and (piece.difficulty_score is None or (piece.metadata_generation_model or "").startswith(("harvest", "heuristic"))):
        piece.difficulty_score = computed
        piece.metadata_generation_model = HARVEST_MODEL
    if piece.difficulty_score is not None and (piece.syllabus_grade is None or piece.metadata_generation_model == HARVEST_MODEL):
        piece.syllabus_grade = GRADE_BY_BAND.get(difficulty_band(piece.difficulty_score))


def passage_key(candidate: Candidate, start: int, end: int) -> str:
    return f"harvest/passages/{candidate.source}/{candidate.source_id}/{start}-{end}.svg"


async def apply_passages(session, context: Context, piece, candidate: Candidate, extras: dict) -> None:
    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload

    from app.models.models import Passage, PassageSource, PassageTechnique, PieceTechnique
    from app.services.difficulty import compute_mechanical_load

    index = extras["index"]
    techniques = context.techniques
    owned = piece.metadata_generation_model == HARVEST_MODEL
    existing_links = (await session.execute(select(PieceTechnique.technique_id).where(PieceTechnique.piece_id == piece.id))).scalars().all()
    usable = [(name, weight) for name, weight in index["techniques"] if name in techniques]
    if usable and (owned or not existing_links):
        await session.execute(delete(PieceTechnique).where(PieceTechnique.piece_id == piece.id))
        for name, weight in usable:
            session.add(PieceTechnique(piece_id=piece.id, technique_id=techniques[name].id, weight=weight))
        if piece.difficulty_score is not None:
            piece.mechanical_load = compute_mechanical_load(usable, {name: float(t.load_factor) for name, t in techniques.items()}, piece.difficulty_score)
    held = (
        await session.execute(
            select(Passage)
            .where(Passage.piece_id == piece.id, Passage.source == PassageSource.HARVEST)
            .options(selectinload(Passage.technique_links), selectinload(Passage.assessments))
        )
    ).scalars().all()
    by_span = {(row.start_measure, row.end_measure): row for row in held}
    wanted = set()
    for item in index["passages"]:
        span = (item["start"], item["end"])
        wanted.add(span)
        row = by_span.get(span)
        if row is None:
            row = Passage(piece_id=piece.id, start_measure=item["start"], end_measure=item["end"], source=PassageSource.HARVEST)
            session.add(row)
            row.technique_links = []
        row.label = item["label"][:80]
        row.description = item["description"]
        row.practice_cue = item["cue"]
        row.difficulty_score = Decimal(str(passage_module.passage_difficulty(float(piece.difficulty_score) if piece.difficulty_score is not None else None, item["relative"])))
        links = {name: weight for name, weight in item["techniques"].items() if name in techniques}
        current = {link.technique_id: link for link in row.technique_links}
        for name, weight in links.items():
            link = current.pop(techniques[name].id, None)
            if link is None:
                row.technique_links.append(PassageTechnique(technique_id=techniques[name].id, weight=Decimal(str(round(min(max(weight, 0.05), 1.0), 2)))))
            else:
                link.weight = Decimal(str(round(min(max(weight, 0.05), 1.0), 2)))
        for link in current.values():
            row.technique_links.remove(link)
        image = extras["images"].get(item["image"]) if item.get("image") else None
        if image is not None:
            key = passage_key(candidate, *span)
            if context.storage is not None and not context.storage.exists(key):
                context.storage.save(io.BytesIO(image), key)
            row.image_key = key
    for span, row in by_span.items():
        if span not in wanted and not row.assessments:
            await session.delete(row)


async def apply_reference(session, piece, record, payload: dict) -> None:
    from app.services import reference_notes

    if payload.get("reference"):
        await reference_notes.store(session, piece, record, payload["reference"])


async def upsert(session, context: Context, candidate: Candidate, payload: dict, extras: Optional[dict] = None) -> str:
    from app.models.models import PieceSource

    facts = provenance(candidate)
    record = context.sources.get((candidate.source, candidate.source_id))
    if record is not None:
        changed = False
        for name, value in facts.items():
            if getattr(record, name) != value:
                setattr(record, name, value)
                changed = True
        stale = record.content_hash != candidate.extra["content_hash"] or record.feature_version != payload["features"]["version"]
        recalibrated = context.model is not None and record.calibration_version != context.model.version
        if stale:
            apply_features(record.piece, record, payload, candidate, context)
        if stale or recalibrated:
            apply_difficulty(record.piece, record, payload["features"], context)
        if changed or stale or recalibrated:
            record.updated_at = context.now
        if extras is not None:
            await apply_passages(session, context, record.piece, candidate, extras)
        await apply_reference(session, record.piece, record, payload)
        return "updated" if (changed or stale or recalibrated) else "unchanged"
    composer = resolve_composer(context, candidate, session)
    if composer.id is None:
        await session.flush()
    piece = match_existing(context, candidate, composer)
    outcome = "attached" if piece is not None else "created"
    if piece is None:
        piece = new_piece(context, candidate, composer, payload)
        session.add(piece)
        await session.flush()
    piece.harvest_piece_id = None
    record = PieceSource(piece_id=piece.id, **facts, content_hash=candidate.extra["content_hash"])
    session.add(record)
    record.piece = piece
    apply_features(piece, record, payload, candidate, context)
    apply_difficulty(piece, record, payload["features"], context)
    context.sources[(candidate.source, candidate.source_id)] = record
    if extras is not None:
        await apply_passages(session, context, piece, candidate, extras)
    await apply_reference(session, piece, record, payload)
    return outcome


RETIRED = "harvest: no longer passes the licence or composer rules"


def retire(context: Context, current: set) -> dict:
    counts = {"retired": 0, "restored": 0}
    for key, record in context.sources.items():
        piece = record.piece
        if key not in current and piece.hidden_at is None:
            piece.hidden_at = context.now
            piece.hidden_reason = RETIRED
            counts["retired"] += 1
        elif key in current and piece.hidden_at is not None and piece.hidden_reason == RETIRED:
            piece.hidden_at = None
            piece.hidden_reason = None
            counts["restored"] += 1
    return {name: value for name, value in counts.items() if value}


def load_extras(ws: Workspace, candidate: Candidate) -> Optional[dict]:
    if "passages" not in candidate.local:
        return None
    path = ws.abs(candidate.local["passages"])
    index = json.loads(path.read_text(encoding="utf-8"))
    images = {item["image"]: (path.parent / item["image"]).read_bytes() for item in index["passages"] if item.get("image") and (path.parent / item["image"]).exists()}
    return {"index": index, "images": images}


async def ingest(ws: Workspace, source_stage: str, *, say: Callable[[str], None] = print, limit: Optional[int] = None) -> dict:
    from app.core.database import dispose_engine, session_scope
    from app.core.storage import storage as default_storage

    candidates = ws.read_stage(source_stage)
    if limit is not None:
        candidates = candidates[:limit]
    counts: Counter = Counter()
    async with session_scope() as session:
        context = await load_context(session)
        context.model = Model.load()
        context.storage = default_storage
        for index, candidate in enumerate(candidates, start=1):
            payload = json.loads(ws.abs(candidate.local["features"]).read_text(encoding="utf-8"))
            counts[await upsert(session, context, candidate, payload, load_extras(ws, candidate))] += 1
            if index % FLUSH_EVERY == 0:
                await session.flush()
                say(f"ingest: {index}/{len(candidates)} {dict(counts)}")
        if limit is None:
            current = {(candidate.source, candidate.source_id) for candidate in candidates}
            counts.update(retire(context, current))
    await dispose_engine()
    return dict(counts)
