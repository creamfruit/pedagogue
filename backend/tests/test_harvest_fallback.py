import json
import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import harvest_library, public_pages, reference_notes, score_library, similar
from tests.harvest_helpers import write_study
from tests.test_keyboard_api import client, needs_db, world  # noqa: F401
from tools.harvest import extract, features as feature_module, ingest, scoredata

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = [
    ROOT / "backend" / "app" / "data" / "score_library.json",
    ROOT / "backend" / "app" / "seed.py",
    ROOT / "backend" / "app" / "seed_lore.py",
    ROOT / "backend" / "app" / "services" / "repertoire_reference.py",
    ROOT / "backend" / "app" / "services" / "score_library.py",
    ROOT / "frontend" / "public" / "excerpts" / "index.json",
]


def test_nothing_derived_from_the_asap_dataset_ships_in_the_library_or_the_seed():
    for path in SHIPPED:
        assert not re.search(r"asap", path.read_text(encoding="utf-8"), re.I), path


def test_every_library_entry_comes_from_a_source_that_allows_commercial_use():
    library = score_library.load_library()
    assert library["entries"]
    for name, source in library["sources"].items():
        assert source["commercial"] is True, name
        assert source["license"].startswith("CC BY"), name
    assert {entry["source"] for entry in library["entries"]} <= set(library["sources"])


def test_the_excerpt_index_lists_only_sources_with_a_commercial_licence():
    index = json.loads((ROOT / "frontend" / "public" / "excerpts" / "index.json").read_text(encoding="utf-8"))
    assert index["sources"]
    assert not any("asap" in name.lower() for name in index["sources"])
    for source in index["sources"].values():
        text = json.dumps(source).lower()
        assert "nc" not in re.findall(r"\bcc[ -]by[-a-z]*", text) and "by-nc" not in text


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    path = write_study(tmp_path_factory.mktemp("fallback"), "mid")
    data = scoredata.load_score(path, "mid")
    measured = feature_module.extract(data)
    return measured, extract.reference_for(data, measured)


@pytest.fixture
async def pair(world, study):
    from sqlalchemy import delete

    from app.models.models import Composer, Passage, PassageSource, PassageTechnique, Piece, PieceSource, PieceTechnique, Technique

    public_pages.forget_catalogue()
    similar.forget_vectors()
    measured, reference = study
    tag = uuid.uuid4().hex[:8]
    async with world.factory() as session:
        composer = Composer(name=f"Zephyr Fallback{tag}", birth_year=1801, death_year=1870)
        technique = (await session.execute(Technique.__table__.select().limit(1))).first()
        session.add(composer)
        await session.flush()
        lender = Piece(
            title=f"Quillon Study {tag}",
            catalog_number="Op. 9 No. 1",
            composer_id=composer.id,
            difficulty_score=48,
            mechanical_load=41,
            external_source="mutopia",
            external_ref=f"f{tag}",
            metadata_generation_model="harvest-1",
        )
        borrower = Piece(title=f"Quillon Study {tag}", catalog_number="Op. 9 No. 1", composer_id=composer.id, difficulty_score=20, metadata_generation_model="heuristic-0.3")
        elsewhere = Piece(title=f"Entirely Other Work {tag}", composer_id=composer.id, difficulty_score=20, metadata_generation_model="heuristic-0.3")
        session.add_all([lender, borrower, elsewhere])
        await session.flush()
        session.add(
            PieceSource(
                piece_id=lender.id,
                source="mutopia",
                source_id=f"f{tag}",
                source_url="https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=555",
                licence_code="public-domain",
                licence_name="Public Domain",
                licence_url="https://creativecommons.org/publicdomain/mark/1.0/",
                composer_name=f"Zephyr Fallback{tag}",
                composer_died_on=date(1870, 1, 1),
                attribution="Typeset by A Typesetter",
                content_hash="b" * 64,
            )
        )
        passage = Passage(piece_id=lender.id, start_measure=5, end_measure=7, label="Octave passage", source=PassageSource.HARVEST, description="Bars 5–7: octaves.", practice_cue="Slowly.", difficulty_score=6.0, image_key=f"harvest/passages/mutopia/f{tag}/5-7.svg")
        session.add(passage)
        await session.flush()
        if technique is not None:
            session.add(PieceTechnique(piece_id=lender.id, technique_id=technique.id, weight=0.8))
            session.add(PassageTechnique(passage_id=passage.id, technique_id=technique.id, weight=0.7))
        record = await session.get(PieceSource, lender.id)
        await reference_notes.store(session, lender, record, reference)
        await session.commit()
        ids = SimpleNamespace(lender=lender.id, borrower=borrower.id, elsewhere=elsewhere.id, composer=composer.id, tag=tag)
    try:
        yield ids
    finally:
        async with world.factory() as session:
            await session.execute(delete(Piece).where(Piece.id.in_([ids.lender, ids.borrower, ids.elsewhere])))
            await session.execute(delete(Composer).where(Composer.id == ids.composer))
            await session.commit()
        public_pages.forget_catalogue()
        similar.forget_vectors()


async def borrow(world, piece_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Piece

    async with world.factory() as session:
        piece = (await session.execute(select(Piece).options(selectinload(Piece.composer), selectinload(Piece.technique_links)).where(Piece.id == piece_id))).scalar_one()
        attached = await harvest_library.attach_harvest(session, piece, piece.composer.name)
        await session.commit()
    return attached


@needs_db
async def test_an_estimated_piece_takes_the_measured_data_of_the_same_work(world, pair):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Passage, Piece

    assert await borrow(world, pair.borrower) is True
    async with world.factory() as session:
        piece = (await session.execute(select(Piece).options(selectinload(Piece.technique_links)).where(Piece.id == pair.borrower))).scalar_one()
        passages = (await session.execute(select(Passage).where(Passage.piece_id == pair.borrower))).scalars().all()
    assert piece.harvest_piece_id == pair.lender
    assert float(piece.difficulty_score) == 48.0 and float(piece.mechanical_load) == 41.0
    assert piece.metadata_generation_model == "harvest-1"
    assert len(passages) == 1 and passages[0].image_key.endswith("5-7.svg") and passages[0].start_measure == 5
    assert piece.technique_links


@needs_db
async def test_taking_the_data_twice_adds_nothing(world, pair):
    from sqlalchemy import func, select

    from app.models.models import Passage

    await borrow(world, pair.borrower)
    await borrow(world, pair.borrower)
    async with world.factory() as session:
        count = (await session.execute(select(func.count()).select_from(Passage).where(Passage.piece_id == pair.borrower))).scalar_one()
    assert count == 1


@needs_db
async def test_a_different_work_is_left_alone(world, pair):
    assert await borrow(world, pair.elsewhere) is False
    async with world.factory() as session:
        from app.models.models import Piece

        piece = await session.get(Piece, pair.elsewhere)
    assert piece.harvest_piece_id is None and float(piece.difficulty_score) == 20.0


@needs_db
async def test_a_piece_the_ladder_already_places_is_left_to_the_ladder(world, pair):
    from app.models.models import Composer, Piece

    async with world.factory() as session:
        piece = await session.get(Piece, pair.borrower)
        piece.title = "Fur Elise"
        composer = await session.get(Composer, pair.composer)
        composer.name = "Zephyr Beethoven"
        await session.commit()
    assert await borrow(world, pair.borrower) is False


@needs_db
async def test_a_hidden_harvested_piece_is_not_lent(world, pair):
    from datetime import datetime, timezone

    from app.models.models import Piece

    async with world.factory() as session:
        lender = await session.get(Piece, pair.lender)
        lender.hidden_at = datetime.now(timezone.utc)
        await session.commit()
    assert await borrow(world, pair.borrower) is False


@needs_db
async def test_the_borrowing_piece_shows_the_lenders_source_and_scores_with_its_notes(world, pair):
    await borrow(world, pair.borrower)
    async with world.factory() as session:
        reference = await reference_notes.load_reference(session, pair.borrower)
        own = await reference_notes.load_reference(session, pair.lender)
    assert reference is not None and own is not None
    assert reference.first_bar == own.first_bar == 1 and len(reference.notes) == len(own.notes)
    async with client() as http:
        body = (await http.get(f"/api/v1/catalog/pieces/{pair.borrower}/overview")).json()
    assert body["difficulty_basis"] == "harvest"
    assert body["source"]["source_name"] == "Mutopia Project" and body["source"]["licence_name"] == "Public Domain"
    assert body["sections"][0]["source"] == "harvest"


@needs_db
async def test_the_seed_refresh_gives_estimated_pieces_the_harvested_data(world, pair):
    from app.models.models import Piece
    from app.services.piece_knowledge import refresh_catalog_knowledge

    async with world.factory() as session:
        counts = await refresh_catalog_knowledge(session)
        await session.commit()
        piece = await session.get(Piece, pair.borrower)
        other = await session.get(Piece, pair.elsewhere)
    assert counts["harvested"] >= 1
    assert piece.harvest_piece_id == pair.lender and float(piece.difficulty_score) == 48.0
    assert other.harvest_piece_id is None


def test_works_that_stop_passing_the_rules_are_hidden_and_restored_if_they_return():
    from datetime import datetime, timezone

    def record(hidden=None, reason=None):
        return SimpleNamespace(piece=SimpleNamespace(hidden_at=hidden, hidden_reason=reason))

    now = datetime.now(timezone.utc)
    kept, dropped = record(), record()
    returned = record(now, ingest.RETIRED)
    manual = record(now, "licence in doubt")
    context = SimpleNamespace(
        now=now,
        sources={("mutopia", "1"): kept, ("mutopia", "2"): dropped, ("mutopia", "3"): returned, ("mutopia", "4"): manual},
    )
    assert ingest.retire(context, {("mutopia", "1"), ("mutopia", "3"), ("mutopia", "4")}) == {"retired": 1, "restored": 1}
    assert dropped.piece.hidden_at == now and dropped.piece.hidden_reason == ingest.RETIRED
    assert returned.piece.hidden_at is None
    assert manual.piece.hidden_at == now and manual.piece.hidden_reason == "licence in doubt"
    assert ingest.retire(context, {("mutopia", "1"), ("mutopia", "3"), ("mutopia", "4")}) == {}
