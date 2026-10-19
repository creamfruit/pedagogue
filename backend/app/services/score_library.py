from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Composer,
    Era,
    Genre,
    Passage,
    PassageSource,
    PassageTechnique,
    Piece,
    PieceTechnique,
    RepertoireEntry,
    Technique,
)
from app.services.catalog_match import composer_surname, fold, normalize_title
from app.services.difficulty import compute_mechanical_load, difficulty_band

logger = logging.getLogger("piano.library")

LIBRARY_PATH = Path(__file__).resolve().parents[1] / "data" / "score_library.json"
LIBRARY_MODEL = "score-library-1"
LIBRARY_SOURCE = "library"
ROMAN_VALUES = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
MOVEMENT_MARK = re.compile(r"[:,]\s*(I{1,3}|IV|V|VI{0,3}|IX|X)\.?(?:\s|$)")
TRAILING_MOVEMENT = re.compile(r",\s*(I{1,3}|IV|V|VI{0,3}|IX|X)\s*$")
GENRE_WORDS = [
    ("etude", "Etude"), ("étude", "Etude"), ("study", "Etude"), ("nocturne", "Nocturne"), ("sonata", "Sonata"),
    ("sonate", "Sonata"), ("concerto", "Concerto"), ("prelude", "Prelude"), ("prélude", "Prelude"),
    ("invention", "Prelude"), ("sinfonia", "Prelude"), ("fugue", "Prelude"), ("ballade", "Ballade"),
    ("waltz", "Waltz"), ("valse", "Waltz"), ("rag", "Jazz standard"),
]


@lru_cache(maxsize=1)
def load_library() -> dict:
    if not LIBRARY_PATH.exists():
        return {"entries": [], "sources": {}}
    payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    for entry in payload.get("entries", []):
        entry.setdefault("id", entry_id(entry))
    return payload


def feature_row(features: dict) -> list[float]:
    import math

    return [
        1.0,
        features["p90"],
        features["p50"],
        features["peak"],
        math.log1p(features["minutes"]),
        min(features["nps_peak"], 60) / 10,
        features["tech_peak"],
    ]


def calibrated_difficulty(features: dict) -> Optional[Decimal]:
    weights = (load_library().get("calibration") or {}).get("weights")
    if not weights:
        return None
    value = sum(w * x for w, x in zip(weights, feature_row(features)))
    return Decimal(str(round(min(max(value, 5.0), 94.0), 1)))


def entry_id(entry: dict) -> str:
    movement = (entry.get("movement") or [0])[0]
    anchor = entry.get("catalog") or entry.get("title") or ""
    kind = ""
    if composer_surname(entry["composer"]) == "bach" and "well-tempered" in entry["title"].lower():
        kind = "-fugue" if entry["title"].lower().startswith("fugue") else "-prelude"
    slug = re.sub(r"[^a-z0-9]+", "-", fold(f"{composer_surname(entry['composer'])} {anchor}")).strip("-")
    return f"{slug}{kind}-{movement}"[:118]


CATALOGUE_KEY = re.compile(r" (op|s|bwv|k|d|l|m|woo|hob xvi|b|kk) (\d+[a-z]?)(?: no (\d+))?(?= )")


def catalogue_keys(text: str) -> set[str]:
    from app.services.work_titles import match_text

    normalized = match_text(text)
    keys = set()
    for marker, number, sub in CATALOGUE_KEY.findall(normalized):
        number = number.lstrip("0") or "0"
        keys.add(f"{marker.replace(' ', '')}{number}" + (f"n{sub}" if sub else ""))
    return keys


def movement_of(title: str) -> Optional[int]:
    found = MOVEMENT_MARK.search(title) or TRAILING_MOVEMENT.search(title)
    return ROMAN_VALUES.get(found.group(1)) if found else None


def bach_kind(title: str) -> str:
    lowered = fold(title)
    if any(word in lowered for word in ("fugue", "fuga", "fuge")):
        return "fugue"
    if any(word in lowered for word in ("prelude", "praludium", "praeludium", "preludium")):
        return "prelude"
    return ""


@lru_cache(maxsize=1)
def library_index() -> tuple[dict, dict]:
    by_catalogue: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_title: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in load_library().get("entries", []):
        surname = composer_surname(entry["composer"])
        for ident in catalogue_keys(entry.get("catalog") or ""):
            by_catalogue[(surname, ident)].append(entry)
        by_title[(surname, normalize_title(entry.get("parent") or entry["title"]))].append(entry)
    return by_catalogue, by_title


def find_entries(title: str, composer_name: Optional[str], catalog_number: Optional[str] = None) -> list[dict]:
    if not title or not composer_name:
        return []
    surname = composer_surname(composer_name)
    by_catalogue, by_title = library_index()
    text = f"{title} {catalog_number or ''}"
    candidates: list[dict] = []
    keys = catalogue_keys(text)
    specific = {key for key in keys if "n" in key[1:]}
    for ident in specific or keys:
        candidates.extend(by_catalogue.get((surname, ident), []))
    if not candidates and not keys:
        wanted = normalize_title(title)
        candidates = list(by_title.get((surname, wanted), []))
        if not candidates and len(wanted.split()) >= 2:
            candidates = [
                entry
                for (entry_surname, entry_title), group in by_title.items()
                if entry_surname == surname and f" {wanted} " in f" {entry_title} "
                for entry in group
            ][:3]
    if not candidates:
        return []
    if surname == "bach":
        kind = bach_kind(title)
        if kind:
            narrowed = [c for c in candidates if bach_kind(c["title"]) == kind]
            candidates = narrowed or candidates
        else:
            candidates = [c for c in candidates if bach_kind(c["title"]) == "prelude"] or candidates
    movement = movement_of(title)
    with_movements = [c for c in candidates if c.get("movement")]
    if movement is not None and with_movements:
        return [c for c in with_movements if c["movement"][0] == movement][:1]
    if with_movements and len(with_movements) == len(candidates):
        return sorted(with_movements, key=lambda c: c["movement"][0])
    return [c for c in candidates if not c.get("movement")][:1] or candidates[:1]


def library_difficulty(entries: list[dict]) -> Optional[Decimal]:
    values = [e.get("difficulty") or e.get("estimated_difficulty") for e in entries]
    values = [v for v in values if v is not None]
    return Decimal(str(round(max(values), 1))) if values else None


def passage_rows(entries: list[dict], piece_difficulty: Optional[Decimal]) -> list[dict]:
    rows = []
    multi = len(entries) > 1
    for entry in entries:
        base = float(piece_difficulty if piece_difficulty is not None else entry.get("difficulty") or entry.get("estimated_difficulty") or 50) / 10
        prefix = ""
        if multi and entry.get("movement"):
            number, name = entry["movement"]
            prefix = f"{['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'][number - 1] if 1 <= number <= 7 else number}. "
        for item in entry.get("passages", []):
            rows.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "label": f"{prefix}{item['label']}"[:120],
                    "description": item["description"],
                    "cue": item["cue"],
                    "techniques": item["techniques"],
                    "difficulty": Decimal(str(round(min(10.0, base * (0.82 + 0.22 * float(item.get("relative") or 0.8))), 1))),
                }
            )
    return rows


def merged_techniques(entries: list[dict]) -> list[tuple[str, float]]:
    merged: dict[str, float] = {}
    for entry in entries:
        for name, weight in entry.get("techniques", []):
            merged[name] = max(merged.get(name, 0.0), float(weight))
    return sorted(merged.items(), key=lambda item: -item[1])[:5]


async def add_passages(session: AsyncSession, piece: Piece, rows: list[dict], techniques: dict[str, Technique]) -> int:
    existing = (await session.execute(select(Passage.start_measure, Passage.end_measure, Passage.label).where(Passage.piece_id == piece.id))).all()
    seen = {(start, end, label) for start, end, label in existing}
    added = 0
    for row in rows:
        if (row["start"], row["end"], row["label"]) in seen:
            continue
        passage = Passage(
            piece_id=piece.id,
            start_measure=row["start"],
            end_measure=row["end"],
            label=row["label"],
            description=row["description"],
            practice_cue=row["cue"],
            difficulty_score=row["difficulty"],
            source=PassageSource.ANALYZER,
            technique_links=[
                PassageTechnique(technique_id=techniques[name].id, weight=Decimal(str(round(min(max(weight, 0.05), 1.0), 2))))
                for name, weight in row["techniques"].items()
                if name in techniques
            ],
        )
        session.add(passage)
        added += 1
    return added


async def set_techniques(session: AsyncSession, piece: Piece, links: list[tuple[str, float]], techniques: dict[str, Technique]) -> None:
    usable = [(name, weight) for name, weight in links if name in techniques]
    if not usable:
        return
    for link in list(piece.technique_links or []):
        await session.delete(link)
    await session.flush()
    for name, weight in usable:
        session.add(PieceTechnique(piece_id=piece.id, technique_id=techniques[name].id, weight=weight))
    piece.mechanical_load = compute_mechanical_load(
        usable, {name: float(t.load_factor) for name, t in techniques.items()}, piece.difficulty_score
    )


async def attach_library(session: AsyncSession, piece: Piece, composer_name: Optional[str], *, replace_techniques: bool) -> bool:
    entries = find_entries(piece.title, composer_name, piece.catalog_number)
    if not entries:
        return False
    techniques = {t.name: t for t in (await session.execute(select(Technique))).scalars().all()}
    has_passages = (await session.execute(select(Passage.id).where(Passage.piece_id == piece.id).limit(1))).first() is not None
    if not has_passages:
        await add_passages(session, piece, passage_rows(entries, piece.difficulty_score), techniques)
    if piece.duration_sec is None:
        piece.duration_sec = sum(int(e.get("duration_sec") or 0) for e in entries) or None
    if not piece.key_signature and entries[0].get("key") and len(entries) == 1:
        piece.key_signature = entries[0]["key"]
    if replace_techniques:
        await session.refresh(piece, ["technique_links"])
        await set_techniques(session, piece, merged_techniques(entries), techniques)
    return True


def genre_for(title: str, genres: dict[str, Genre]) -> Optional[Genre]:
    lowered = title.lower()
    for word, name in GENRE_WORDS:
        if word in lowered and name in genres:
            return genres[name]
    return None


def parent_ref(entry: dict) -> str:
    return f"work:{entry['id'].rsplit('-', 1)[0]}"


def library_refs_in_use() -> tuple[set[str], set[str]]:
    entries = load_library().get("entries", [])
    return {entry["id"] for entry in entries}, {parent_ref(entry) for entry in entries if entry.get("parent") and entry.get("movement")}


def is_withdrawn(piece: Piece, composer_name: Optional[str], current_ids: set[str], current_parents: set[str]) -> bool:
    if piece.external_source == LIBRARY_SOURCE:
        ref = piece.external_ref or ""
        return ref not in (current_parents if ref.startswith("work:") else current_ids)
    if piece.metadata_generation_model != LIBRARY_MODEL:
        return False
    return not find_entries(piece.title, composer_name, piece.catalog_number)


async def withdraw_library_data(session: AsyncSession) -> dict[str, int]:
    from app.models.models import PassageAssessment, PdfSubmission
    from app.services.metadata_generator import METADATA_MODEL_HEURISTIC

    counts = {"withdrawn": 0, "passages_removed": 0, "pieces_removed": 0}
    current_ids, current_parents = library_refs_in_use()
    pieces = (
        await session.execute(
            select(Piece)
            .where((Piece.external_source == LIBRARY_SOURCE) | (Piece.metadata_generation_model == LIBRARY_MODEL))
            .options(selectinload(Piece.composer))
        )
    ).scalars().all()
    stale = [piece for piece in pieces if is_withdrawn(piece, piece.composer.name if piece.composer else None, current_ids, current_parents)]
    if not stale:
        return counts
    ids = [piece.id for piece in stale]
    used = set((await session.execute(select(RepertoireEntry.piece_id).where(RepertoireEntry.piece_id.in_(ids)))).scalars().all())
    uploaded = set(
        (
            await session.execute(
                select(RepertoireEntry.piece_id)
                .join(PdfSubmission, PdfSubmission.repertoire_entry_id == RepertoireEntry.id)
                .where(RepertoireEntry.piece_id.in_(ids))
            )
        ).scalars().all()
    )
    assessed = select(PassageAssessment.passage_id)
    stale.sort(key=lambda piece: (piece.external_ref or "").startswith("work:"))
    for piece in stale:
        if piece.external_source == LIBRARY_SOURCE and piece.id not in used:
            await session.flush()
            has_children = (await session.execute(select(Piece.id).where(Piece.parent_piece_id == piece.id).limit(1))).first() is not None
            if not has_children:
                await session.delete(piece)
                counts["pieces_removed"] += 1
                continue
        if piece.id not in uploaded:
            passages = (
                await session.execute(
                    select(Passage).where(
                        Passage.piece_id == piece.id,
                        Passage.source == PassageSource.ANALYZER,
                        Passage.id.not_in(assessed),
                    )
                )
            ).scalars().all()
            for passage in passages:
                await session.delete(passage)
            counts["passages_removed"] += len(passages)
        piece.metadata_generation_model = METADATA_MODEL_HEURISTIC
        counts["withdrawn"] += 1
    await session.flush()
    return counts


async def seed_score_library(session: AsyncSession) -> dict[str, int]:
    from app.services.metadata_generator import GRADE_BY_BAND
    from app.services.piece_knowledge import fill_composer

    withdrawn = await withdraw_library_data(session)
    library = load_library()
    entries = library.get("entries", [])
    counts = {"created": 0, "enriched": 0, "skipped": 0, **withdrawn}
    if not entries:
        return counts
    techniques = {t.name: t for t in (await session.execute(select(Technique))).scalars().all()}
    genres = {g.name: g for g in (await session.execute(select(Genre))).scalars().all()}
    eras = {era.name: era for era in (await session.execute(select(Era))).scalars().all()}
    composers = {c.name: c for c in (await session.execute(select(Composer))).scalars().all()}
    by_surname = {composer_surname(name): composer for name, composer in composers.items()}
    pieces = (await session.execute(select(Piece).options(selectinload(Piece.composer), selectinload(Piece.technique_links)))).scalars().all()
    library_refs = {p.external_ref: p for p in pieces if p.external_source == LIBRARY_SOURCE}
    claimed: set[str] = set()
    claimed_by: dict[str, Piece] = {}
    for piece in pieces:
        if piece.external_source == LIBRARY_SOURCE:
            continue
        name = piece.composer.name if piece.composer else None
        matched = find_entries(piece.title, name, piece.catalog_number)
        if not matched:
            continue
        movement = movement_of(piece.title)
        if len(matched) == 1 or movement is not None:
            claimed.update(e["id"] for e in matched)
            for e in matched:
                claimed_by.setdefault(e["id"], piece)
        has_passages = (await session.execute(select(Passage.id).where(Passage.piece_id == piece.id).limit(1))).first() is not None
        if not has_passages:
            await add_passages(session, piece, passage_rows(matched, piece.difficulty_score), techniques)
            counts["enriched"] += 1

    def composer_for(name: str) -> Composer:
        composer = composers.get(name) or by_surname.get(composer_surname(name))
        if composer is None:
            composer = Composer(name=name)
            session.add(composer)
            composers[name] = composer
            by_surname[composer_surname(name)] = composer
        return composer

    by_id = {entry["id"]: entry for entry in entries}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    singles: list[dict] = []
    for entry in entries:
        if entry.get("parent") and entry.get("movement"):
            groups[(entry["composer"], entry["parent"])].append(entry)
        else:
            singles.append(entry)

    now = datetime.now(timezone.utc)

    def make_piece(entry: dict, composer: Composer, *, title: Optional[str] = None, parent: Optional[Piece] = None, number: Optional[int] = None, difficulty: Optional[Decimal] = None) -> Piece:
        value = difficulty if difficulty is not None else library_difficulty([entry])
        genre = genre_for(title or entry["title"], genres)
        return Piece(
            title=(title or entry["title"])[:200],
            composer_id=composer.id,
            genre_id=genre.id if genre else None,
            catalog_number=(entry.get("catalog") or None) and entry["catalog"][:40],
            key_signature=entry.get("key"),
            difficulty_score=value,
            duration_sec=int(entry.get("duration_sec") or 0) or None,
            parent_piece_id=parent.id if parent else None,
            movement_number=number,
            external_source=LIBRARY_SOURCE,
            external_ref=entry["id"],
            metadata_generated_at=now,
            metadata_generation_model=LIBRARY_MODEL,
            syllabus_grade=GRADE_BY_BAND.get(difficulty_band(value)) if value is not None else None,
        )

    async def finish(piece: Piece, members: list[dict]) -> None:
        await session.flush()
        links = [(name, weight) for name, weight in merged_techniques(members) if name in techniques]
        for name, weight in links:
            session.add(PieceTechnique(piece_id=piece.id, technique_id=techniques[name].id, weight=weight))
        piece.mechanical_load = compute_mechanical_load(links, {n: float(t.load_factor) for n, t in techniques.items()}, piece.difficulty_score)
        if len(members) == 1:
            await add_passages(session, piece, passage_rows(members, piece.difficulty_score), techniques)

    used = set((await session.execute(select(RepertoireEntry.piece_id))).scalars().all())
    for ref, piece in list(library_refs.items()):
        if ref.startswith("work:") or ref in by_id:
            continue
        if piece.id not in used:
            await session.delete(piece)
            library_refs.pop(ref)
            counts["removed"] = counts.get("removed", 0) + 1

    for ref, piece in library_refs.items():
        entry = by_id.get(ref)
        if entry is None:
            continue
        if piece.parent_piece_id is None and not entry.get("parent"):
            piece.title = entry["title"][:200]
        piece.key_signature = piece.key_signature or entry.get("key")
        piece.difficulty_score = library_difficulty([entry])

    for entry in singles:
        if entry["id"] in claimed or entry["id"] in library_refs:
            counts["skipped"] += 1
            continue
        composer = composer_for(entry["composer"])
        if composer.id is None:
            await session.flush()
        await fill_composer(session, composer, eras)
        piece = make_piece(entry, composer)
        session.add(piece)
        await finish(piece, [entry])
        counts["created"] += 1

    for (composer_name, parent_title), members in groups.items():
        members.sort(key=lambda e: e["movement"][0])
        group_ref = parent_ref(members[0])
        if group_ref in library_refs or all(m["id"] in claimed for m in members):
            existing_parent = library_refs.get(group_ref)
            if existing_parent is not None:
                for entry in members:
                    owner = claimed_by.get(entry["id"])
                    if owner is not None and owner.parent_piece_id is None and owner.id != existing_parent.id:
                        owner.parent_piece_id = existing_parent.id
                        owner.movement_number = entry["movement"][0]
            counts["skipped"] += len(members)
            continue
        composer = composer_for(composer_name)
        if composer.id is None:
            await session.flush()
        await fill_composer(session, composer, eras)
        catalog = members[0].get("catalog")
        parent_display = f"{parent_title}, {catalog}" if catalog and catalog not in parent_title else parent_title
        parent_entry = {**members[0], "id": group_ref, "duration_sec": sum(int(m.get("duration_sec") or 0) for m in members)}
        parent = make_piece(parent_entry, composer, title=parent_display, difficulty=library_difficulty(members))
        parent.key_signature = members[0].get("key")
        session.add(parent)
        await finish(parent, members)
        counts["created"] += 1
        for entry in members:
            if entry["id"] in claimed:
                owner = claimed_by.get(entry["id"])
                if owner is not None and owner.parent_piece_id is None:
                    owner.parent_piece_id = parent.id
                    owner.movement_number = entry["movement"][0]
                continue
            number, name = entry["movement"]
            roman = ["I", "II", "III", "IV", "V", "VI", "VII"][number - 1] if 1 <= number <= 7 else str(number)
            movement_title = f"{parent_display}: {roman}. {name}".rstrip(". ") if name else f"{parent_display}: {roman}"
            child = make_piece(entry, composer, title=movement_title, parent=parent, number=number)
            session.add(child)
            await finish(child, [entry])
            counts["created"] += 1
    await session.flush()
    return counts
