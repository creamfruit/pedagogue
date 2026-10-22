import os
import uuid

import pytest

from tests.harvest_helpers import write_study
from tools.harvest import features as feature_module
from tools.harvest import ingest, scoredata
from tools.harvest.licences import parse_licence
from tools.harvest.models import Candidate

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")


@pytest.fixture(scope="module")
def study_payload(tmp_path_factory):
    path = write_study(tmp_path_factory.mktemp("ingest"), "mid")
    measured = feature_module.extract(scoredata.load_score(path, "mid"))
    return {"features": measured, "vector": feature_module.to_vector(measured)}


def candidate_for(tag, **changes):
    values = dict(
        source="mutopia",
        source_id=f"t{tag}",
        title=f"Study {tag}",
        composer="Q. Quillon",
        source_url=f"https://www.mutopiaproject.org/cgibin/piece-info.cgi?id={abs(hash(tag)) % 100000}",
        licence=parse_licence("Creative Commons Attribution 4.0"),
        licence_text="Creative Commons Attribution 4.0",
        instrument="Piano",
        born=1801,
        died=1870,
        composer_qid="Q1",
        composer_died_on="1870-02-03",
        catalog_number="Opus 9. No. 1",
        files={"ly": "https://example.test/a.ly", "mid": "https://example.test/a.mid"},
        extra={"composer_label": f"Quillon {tag}", "published": "Edition X", "header": {"maintainer": "A Typesetter", "title": "Study"}, "content_hash": "a" * 64},
    )
    values.update(changes)
    return Candidate(**values)


@pytest.fixture
async def database():
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Composer, Piece

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:8]
    try:
        yield factory, tag
    finally:
        async with factory() as session:
            ids = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalars().all()
            await session.execute(delete(Piece).where(Piece.id.in_(ids)))
            await session.execute(delete(Composer).where(Composer.name == f"Quillon {tag}"))
            await session.commit()
        await engine.dispose()


async def run_upsert(factory, candidate, payload):
    async with factory() as session:
        context = await ingest.load_context(session)
        outcome = await ingest.upsert(session, context, candidate, payload)
        await session.commit()
    return outcome


@needs_db
async def test_a_harvested_work_is_stored_with_its_source_licence_composer_features_and_vector(database, study_payload):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Piece

    factory, tag = database
    candidate = candidate_for(tag)
    payload = {**study_payload, "content_hash": "a" * 64}
    assert await run_upsert(factory, candidate, payload) == "created"
    async with factory() as session:
        piece = (
            await session.execute(
                select(Piece).options(selectinload(Piece.harvest), selectinload(Piece.composer)).where(Piece.external_ref == f"t{tag}")
            )
        ).scalar_one()
    record = piece.harvest
    assert piece.title == f"Study {tag}" and piece.catalog_number == "Op. 9 No. 1"
    assert piece.composer.name == f"Quillon {tag}" and piece.composer.birth_year == 1801 and piece.composer.death_year == 1870
    assert piece.composer.era_id is not None
    assert (record.source, record.licence_code, record.licence_name) == ("mutopia", "cc-by", "CC BY 4.0")
    assert record.licence_url == "https://creativecommons.org/licenses/by/4.0/"
    assert record.source_url.startswith("https://www.mutopiaproject.org/")
    assert record.composer_name == f"Quillon {tag}" and record.composer_qid == "Q1"
    assert str(record.composer_died_on) == "1870-02-03"
    assert "Typeset by A Typesetter" in record.attribution and "Edition X" in record.attribution
    assert record.features["bars"] == 12 and record.feature_version == feature_module.FEATURE_VERSION
    assert len(piece.technique_vector) == feature_module.VECTOR_DIM
    assert list(map(round, piece.technique_vector, [4] * 64)) == list(map(round, study_payload["vector"], [4] * 64))
    assert piece.external_source == "mutopia" and piece.metadata_generation_model == ingest.HARVEST_MODEL


@needs_db
async def test_running_the_import_again_changes_nothing(database, study_payload):
    from sqlalchemy import func, select

    from app.models.models import Piece, PieceSource

    factory, tag = database
    candidate = candidate_for(tag)
    payload = {**study_payload, "content_hash": "a" * 64}
    assert await run_upsert(factory, candidate, payload) == "created"
    assert await run_upsert(factory, candidate, payload) == "unchanged"
    assert await run_upsert(factory, candidate, payload) == "unchanged"
    async with factory() as session:
        pieces = (await session.execute(select(func.count()).select_from(Piece).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        sources = (await session.execute(select(func.count()).select_from(PieceSource).where(PieceSource.source_id == f"t{tag}"))).scalar_one()
    assert pieces == 1 and sources == 1


@needs_db
async def test_a_changed_score_updates_the_same_piece(database, study_payload):
    from sqlalchemy import select

    from app.models.models import Piece, PieceSource

    factory, tag = database
    candidate = candidate_for(tag)
    assert await run_upsert(factory, candidate, {**study_payload}) == "created"
    changed = candidate_for(tag)
    changed.extra["content_hash"] = "b" * 64
    newer = {"features": {**study_payload["features"], "bars": 13}, "vector": [0.5] * 64}
    assert await run_upsert(factory, changed, newer) == "updated"
    async with factory() as session:
        record = (await session.execute(select(PieceSource).where(PieceSource.source_id == f"t{tag}"))).scalar_one()
        piece = await session.get(Piece, record.piece_id)
    assert record.content_hash == "b" * 64 and record.features["bars"] == 13
    assert list(piece.technique_vector) == [0.5] * 64


@needs_db
async def test_a_licence_change_upstream_is_recorded_on_the_next_run(database, study_payload):
    from sqlalchemy import select

    from app.models.models import PieceSource

    factory, tag = database
    assert await run_upsert(factory, candidate_for(tag), study_payload) == "created"
    relicensed = candidate_for(tag, licence=parse_licence("Public Domain"), licence_text="Public Domain")
    assert await run_upsert(factory, relicensed, study_payload) == "updated"
    async with factory() as session:
        record = (await session.execute(select(PieceSource).where(PieceSource.source_id == f"t{tag}"))).scalar_one()
    assert record.licence_code == "public-domain"


@needs_db
async def test_a_work_already_in_the_catalogue_is_attached_instead_of_duplicated(database, study_payload):
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from app.models.models import Composer, Piece

    factory, tag = database
    async with factory() as session:
        composer = Composer(name=f"Quillon {tag}", birth_year=1801, death_year=1870)
        session.add(composer)
        await session.flush()
        existing = Piece(title=f"Study {tag}", composer_id=composer.id, catalog_number="Op. 9 No. 1", difficulty_score=55, external_ref=f"t{tag}")
        session.add(existing)
        await session.commit()
        existing_id = existing.id
    outcome = await run_upsert(factory, candidate_for(tag), study_payload)
    assert outcome == "attached"
    async with factory() as session:
        count = (await session.execute(select(func.count()).select_from(Piece).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        piece = (await session.execute(select(Piece).options(selectinload(Piece.harvest)).where(Piece.id == existing_id))).scalar_one()
    assert count == 1
    assert piece.harvest is not None and float(piece.difficulty_score) == 55.0
    assert len(piece.technique_vector) == 64
