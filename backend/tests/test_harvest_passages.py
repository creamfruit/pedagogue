import copy
import io
import os
import re
import uuid

import pytest

from tests.harvest_helpers import write_study
from tests.test_harvest_ingest import candidate_for, needs_db
from tools.harvest import features as feature_module
from tools.harvest import ingest, passages, render, scoredata


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    folder = tmp_path_factory.mktemp("passages")
    path = write_study(folder, "mid")
    data = scoredata.load_score(path, "mid")
    return feature_module.extract(data), data, folder


def test_the_hardest_stretches_are_the_octave_leap_and_run_bars(study):
    found, _, _ = study
    spans = passages.detect(found)
    assert spans
    covered = {bar for item in spans for bar in range(item["start"], item["end"] + 1)}
    assert {5, 6, 7} <= covered
    assert 10 in covered
    top = spans[0]
    assert top["start"] <= 5 <= top["end"]
    assert "Blocked octaves" in top["techniques"]
    assert top["hardest_bar"] in range(top["start"], top["end"] + 1)


def test_passages_do_not_overlap_and_stay_short(study):
    found, _, _ = study
    spans = passages.detect(found)
    assert len(spans) <= passages.MAX_PASSAGES
    bars = [bar for item in spans for bar in range(item["start"], item["end"] + 1)]
    assert len(bars) == len(set(bars))
    assert all(passages.MIN_BARS <= item["end"] - item["start"] + 1 <= passages.MAX_BARS for item in spans)


def test_passages_come_hardest_first_with_a_relative_weight(study):
    found, _, _ = study
    spans = passages.detect(found)
    scores = [item["score"] for item in spans]
    assert scores == sorted(scores, reverse=True)
    assert spans[0]["relative"] == 1.0
    assert all(0 < item["relative"] <= 1.0 for item in spans)


def test_each_passage_says_what_to_practise(study):
    found, _, _ = study
    for item in passages.detect(found):
        assert item["label"] and item["cue"]
        assert item["description"].startswith(("Bar ", "Bars "))
        assert str(item["hardest_bar"]) in item["description"] or not item["techniques"]


def test_the_hardest_bars_are_ranked(study):
    found, _, _ = study
    bars = passages.hardest_bars(found, 3)
    assert len(bars) == 3
    assert bars[0] in (5, 6)
    assert set(bars) <= {5, 6, 7, 8, 10}


def test_a_plain_piece_has_no_hard_passages(study):
    found, _, _ = study
    flat = copy.deepcopy(found)
    count = len(flat["per_bar"]["numbers"])
    for key in ("notes", "span", "leap", "octave", "tuplet", "run", "window", "nps", "onsets"):
        flat["per_bar"][key] = [2.0 if key == "notes" else 1.0 if key == "nps" else 0.0] * count
    assert passages.detect(flat) == []


def test_piece_techniques_name_the_techniques_that_run_through_the_score(study):
    found, _, _ = study
    names = dict(passages.piece_techniques(passages.bar_signals(found["per_bar"]), found["length"]["minutes"]))
    assert {"Blocked octaves", "Wide leaps", "Rapid scales"} <= set(names)
    assert all(0.15 <= weight <= 1.0 for weight in names.values())


def test_passage_difficulty_follows_the_piece_on_the_catalogue_scale():
    assert passages.passage_difficulty(70, 1.0) == 7.3
    assert passages.passage_difficulty(70, 0.5) < passages.passage_difficulty(70, 1.0)
    assert passages.passage_difficulty(100, 1.0) == 10.0
    assert 0 < passages.passage_difficulty(None, 0.8) <= 10


def test_the_lilypond_source_is_cropped_to_the_bar_range():
    source = '\\version "2.24.0"\n\\header { title = "T" }\n\\score { \\new Staff { c1 c1 c1 } \\layout { } }\n'
    cropped = render.crop_source(source, 12, 16)
    assert "bar-filter-engraver 12 16" in cropped
    assert cropped.index("bar-filter-engraver") < cropped.index("\\score")
    assert cropped.index("scoreTitleMarkup = ##f") < cropped.index("\\score")
    assert render.crop_source("no version here", 1, 2) is None
    assert render.source_version(source) == (2, 24)


def test_a_musicxml_score_is_rendered_to_the_chosen_bars(study, tmp_path):
    _, _, _ = study
    path = write_study(tmp_path, "mxl")
    numbers = list(range(1, 13))
    svg = render.render_musicxml(path, numbers, 5, 6)
    assert svg and svg.lstrip().startswith("<svg")
    assert len(re.findall(r'class="measure"', svg)) == 2
    assert render.render_musicxml(path, numbers, 5, 40) is None


def test_the_fallback_draws_the_bars_from_the_notes_themselves(study):
    _, data, _ = study
    svg = render.render_from_notes(data, 5, 7)
    assert svg and "<svg" in svg
    assert len(re.findall(r'class="measure"', svg)) == 3
    assert render.render_from_notes(data, 5, 99) is None


@pytest.mark.skipif(render.lilypond_binary() is None, reason="set LILYPOND_BIN to run")
def test_a_lilypond_score_is_cropped_to_the_chosen_bars(tmp_path):
    source = tmp_path / "piece.ly"
    notes = " ".join("c'1" if bar % 2 else "d'1" for bar in range(1, 11))
    source.write_text('\\version "2.24.0"\n\\header { title = "Title that must not appear" }\n\\score { \\new Staff { ' + notes + " } \\layout { } }\n", encoding="utf-8")
    svg = render.render_lilypond(source, 4, 6)
    assert svg and "<svg" in svg
    numbers = re.findall(r"<tspan[^>]*>(\d+)</tspan>", svg)
    assert set(numbers) == {"4", "5", "6"}
    assert "Title that must not appear" not in svg


@pytest.mark.skipif(render.lilypond_binary() is None, reason="set LILYPOND_BIN to run")
def test_a_broken_lilypond_source_yields_nothing_instead_of_an_error(tmp_path):
    source = tmp_path / "broken.ly"
    source.write_text('\\version "2.24.0"\n\\score { \\new Staff { \\nonsense c1 } }\n', encoding="utf-8")
    assert render.render_lilypond(source, 1, 2) is None


def sample_extras(study_features, with_image=True):
    spans = passages.detect(study_features)
    for item in spans:
        item["image"] = f"{item['start']}-{item['end']}.svg" if with_image else None
    index = {
        "passages": spans,
        "techniques": passages.piece_techniques(passages.bar_signals(study_features["per_bar"]), study_features["length"]["minutes"]),
        "hardest_bars": passages.hardest_bars(study_features),
    }
    return {"index": index, "images": {item["image"]: b"<svg xmlns='http://www.w3.org/2000/svg'><path d='M0 0'/></svg>" for item in spans if item["image"]}}


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def exists(self, key):
        return key in self.files

    def save(self, stream, key, limit=None):
        self.files[key] = stream.read()
        return len(self.files[key])


@pytest.fixture
async def database():
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Composer, Piece

    engine = create_async_engine(os.environ["PIANO_TEST_DATABASE_URL"])
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


class StubModel:
    version = "stub-1"

    def score(self, features):
        return 62.0


async def run(factory, candidate, payload, extras, storage):
    async with factory() as session:
        context = await ingest.load_context(session)
        context.storage = storage
        context.model = StubModel()
        outcome = await ingest.upsert(session, context, candidate, payload, extras)
        await session.commit()
    return outcome


@needs_db
async def test_hard_passages_are_stored_with_a_source_marker_and_an_image(database, study):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Passage, PassageSource, Piece

    factory, tag = database
    found, _, _ = study
    payload = {"features": found, "vector": feature_module.to_vector(found)}
    extras = sample_extras(found)
    storage = MemoryStorage()
    candidate = candidate_for(tag)
    assert await run(factory, candidate, payload, extras, storage) == "created"
    async with factory() as session:
        piece = (await session.execute(select(Piece).where(Piece.external_ref == f"t{tag}").options(selectinload(Piece.technique_links)))).scalar_one()
        rows = (await session.execute(select(Passage).where(Passage.piece_id == piece.id).options(selectinload(Passage.technique_links)))).scalars().all()
    assert len(rows) == len(extras["index"]["passages"]) >= 2
    assert {row.source for row in rows} == {PassageSource.HARVEST}
    assert all(row.image_key == f"harvest/passages/mutopia/t{tag}/{row.start_measure}-{row.end_measure}.svg" for row in rows)
    assert all(row.image_key in storage.files for row in rows)
    assert all(row.description and row.practice_cue and row.difficulty_score is not None for row in rows)
    assert all(0 <= float(row.difficulty_score) <= 10 for row in rows)
    assert any(row.technique_links for row in rows)
    assert piece.technique_links and piece.mechanical_load is not None


@needs_db
async def test_importing_again_keeps_exactly_the_same_passages(database, study):
    from sqlalchemy import func, select

    from app.models.models import Passage, Piece

    factory, tag = database
    found, _, _ = study
    payload = {"features": found, "vector": feature_module.to_vector(found)}
    extras = sample_extras(found)
    storage = MemoryStorage()
    candidate = candidate_for(tag)
    await run(factory, candidate, payload, extras, storage)
    first = dict(storage.files)
    assert await run(factory, candidate, payload, extras, storage) == "unchanged"
    assert await run(factory, candidate, payload, extras, storage) == "unchanged"
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        count = (await session.execute(select(func.count()).select_from(Passage).where(Passage.piece_id == piece_id))).scalar_one()
    assert count == len(extras["index"]["passages"])
    assert storage.files == first


@needs_db
async def test_a_passage_that_is_no_longer_hard_is_removed_and_one_with_an_assessment_is_kept(database, study):
    from sqlalchemy import select

    from app.models.models import Passage, Piece

    factory, tag = database
    found, _, _ = study
    payload = {"features": found, "vector": feature_module.to_vector(found)}
    extras = sample_extras(found)
    candidate = candidate_for(tag)
    await run(factory, candidate, payload, extras, MemoryStorage())
    shorter = {**extras, "index": {**extras["index"], "passages": extras["index"]["passages"][:1]}}
    await run(factory, candidate, payload, shorter, MemoryStorage())
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        rows = (await session.execute(select(Passage).where(Passage.piece_id == piece_id))).scalars().all()
    assert len(rows) == 1


@needs_db
async def test_a_passage_without_a_rendered_image_is_stored_without_one(database, study):
    from sqlalchemy import select

    from app.models.models import Passage, Piece

    factory, tag = database
    found, _, _ = study
    payload = {"features": found, "vector": feature_module.to_vector(found)}
    extras = sample_extras(found, with_image=False)
    await run(factory, candidate_for(tag), payload, extras, MemoryStorage())
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        rows = (await session.execute(select(Passage).where(Passage.piece_id == piece_id))).scalars().all()
    assert rows and all(row.image_key is None for row in rows)
