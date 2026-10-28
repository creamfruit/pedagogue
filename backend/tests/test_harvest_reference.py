import copy
import os
import uuid

import pytest

from app.services import reference_notes
from app.services.keyboard_scoring import PlayedNote, score_timed
from tests.harvest_helpers import write_study
from tests.test_harvest_ingest import candidate_for, needs_db
from tools.harvest import extract, features as feature_module, scoredata


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    path = write_study(tmp_path_factory.mktemp("reference"), "mid")
    data = scoredata.load_score(path, "mid")
    measured = feature_module.extract(data)
    return measured, extract.reference_for(data, measured)


def test_a_clean_study_passes_validation(study):
    _, payload = study
    assert reference_notes.validate(payload) == []


def test_the_notes_are_stored_as_parallel_lists_with_the_bar_layout(study):
    _, payload = study
    assert len(payload["onsets"]) == len(payload["midi"]) == len(payload["bars"])
    assert payload["bars"][0] == 1 and payload["bars"][-1] == 12
    assert payload["bar_starts"]["5"] == 16.0 and payload["bar_lengths"]["11"] == 3.0
    assert payload["quarter_bpm"] == pytest.approx(120.0)
    assert payload["onsets"] == sorted(payload["onsets"])


def test_the_payload_becomes_a_reference_the_keyboard_engine_slices(study):
    _, payload = study
    reference = reference_notes.to_reference(payload)
    assert reference.source == "harvest" and reference.first_bar == 1 and reference.last_bar == 12
    assert reference.beats_per_bar == 4
    chunk = reference.slice(5, 6)
    assert chunk and min(note.onset for note in chunk) == 0.0
    assert {note.bar for note in chunk} == {5, 6}


def test_a_perfect_run_through_the_reference_scores_full_marks(study):
    _, payload = study
    reference = reference_notes.to_reference(payload)
    notes = reference.slice(1, 4)
    beat_ms = 60000.0 / 120
    result = score_timed(notes, [PlayedNote(note.onset * beat_ms, note.midi) for note in notes], 120)
    assert result.correct == result.expected and result.accuracy == 1.0


def broken(payload, **changes):
    found = copy.deepcopy(payload)
    found.update(changes)
    return found


@pytest.mark.parametrize(
    "change, fragment",
    [
        (lambda p: broken(p, midi=[5] + p["midi"][1:]), "range"),
        (lambda p: broken(p, midi=[200] + p["midi"][1:]), "range"),
        (lambda p: broken(p, onsets=[-1.0] + p["onsets"][1:]), "negative"),
        (lambda p: broken(p, onsets=[float("nan")] + p["onsets"][1:]), "negative"),
        (lambda p: broken(p, onsets=list(reversed(p["onsets"]))), "time order"),
        (lambda p: broken(p, bars=list(reversed(p["bars"]))), "backwards"),
        (lambda p: broken(p, bars=p["bars"][:-1]), "differ in length"),
        (lambda p: broken(p, quarter_bpm=5), "tempo"),
        (lambda p: broken(p, quarter_bpm=900), "tempo"),
        (lambda p: broken(p, bar_starts={}), "no start or length"),
        (lambda p: broken(p, onsets=p["onsets"][:4], midi=p["midi"][:4], bars=p["bars"][:4]), "fewer than"),
        (lambda p: {"onsets": []}, "incomplete"),
    ],
)
def test_damaged_note_data_is_refused_with_a_reason(study, change, fragment):
    _, payload = study
    issues = reference_notes.validate(change(payload))
    assert issues and any(fragment in issue for issue in issues), issues


def test_a_note_far_from_its_bar_is_refused(study):
    _, payload = study
    shifted = copy.deepcopy(payload)
    shifted["onsets"][0] = 5.0
    assert any("outside its bar" in issue for issue in reference_notes.structure_issues(shifted))


def test_a_passage_too_dense_to_score_is_refused(study):
    _, payload = study
    dense = {"onsets": [], "midi": [], "bars": [], "bar_starts": {}, "bar_lengths": {}, "quarter_bpm": 100}
    for bar in range(1, 9):
        dense["bar_starts"][str(bar)] = (bar - 1) * 4.0
        dense["bar_lengths"][str(bar)] = 4.0
        for step in range(110):
            dense["onsets"].append((bar - 1) * 4.0 + step * 0.035)
            dense["midi"].append(40 + step % 40)
            dense["bars"].append(bar)
    assert any("too many to score" in issue for issue in reference_notes.density_issues(dense))
    assert reference_notes.density_issues(payload) == []


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


async def ingest_one(factory, tag, measured, reference):
    from tools.harvest import ingest

    payload = {"features": measured, "vector": feature_module.to_vector(measured), "reference": reference}
    async with factory() as session:
        context = await ingest.load_context(session)
        outcome = await ingest.upsert(session, context, candidate_for(tag), payload)
        await session.commit()
    return outcome


@needs_db
async def test_a_piece_whose_notes_pass_is_marked_scoring_ready_and_can_be_read_back(database, study):
    from sqlalchemy import select

    from app.models.models import Piece, PieceReferenceNotes, PieceSource

    factory, tag = database
    measured, reference = study
    await ingest_one(factory, tag, measured, reference)
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        record = await session.get(PieceSource, piece_id)
        stored = await session.get(PieceReferenceNotes, piece_id)
        loaded = await reference_notes.load_reference(session, piece_id)
    assert record.scoring_ready is True and record.scoring_issues is None
    assert stored.note_count == len(reference["midi"]) and stored.bar_count == 12
    assert loaded is not None and loaded.first_bar == 1 and loaded.last_bar == 12
    assert len(loaded.notes) == len(reference["midi"])


@needs_db
async def test_a_piece_whose_notes_fail_is_not_scoring_ready_and_gives_no_reference(database, study):
    from sqlalchemy import select

    from app.models.models import Piece, PieceSource

    factory, tag = database
    measured, reference = study
    damaged = copy.deepcopy(reference)
    damaged["midi"][0] = 3
    await ingest_one(factory, tag, measured, damaged)
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        record = await session.get(PieceSource, piece_id)
        loaded = await reference_notes.load_reference(session, piece_id)
    assert record.scoring_ready is False
    assert any("range" in issue for issue in record.scoring_issues["issues"])
    assert loaded is None


@needs_db
async def test_fixing_the_notes_on_a_later_run_turns_scoring_on(database, study):
    from sqlalchemy import select

    from app.models.models import Piece, PieceSource

    factory, tag = database
    measured, reference = study
    damaged = copy.deepcopy(reference)
    damaged["midi"][0] = 3
    await ingest_one(factory, tag, measured, damaged)
    await ingest_one(factory, tag, measured, reference)
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).where(Piece.external_ref == f"t{tag}"))).scalar_one()
        record = await session.get(PieceSource, piece_id)
    assert record.scoring_ready is True and record.scoring_issues is None
