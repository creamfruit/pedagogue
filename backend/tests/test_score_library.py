import os
from types import SimpleNamespace

import pytest

from app.core.storage import sniff_score
from app.services.score_analysis import analyse_file
from app.services.score_library import catalogue_keys, find_entries, load_library


def octave_study_xml() -> bytes:
    from music21 import chord, meter, note, stream, tempo

    right = stream.PartStaff()
    left = stream.PartStaff()
    for number in range(1, 13):
        upper = stream.Measure(number=number)
        lower = stream.Measure(number=number)
        if number == 1:
            upper.append(tempo.MetronomeMark(number=120))
            upper.append(meter.TimeSignature("4/4"))
            lower.append(meter.TimeSignature("4/4"))
        if 9 <= number <= 11:
            for step in range(16):
                pitch = 72 + (step % 8)
                upper.append(chord.Chord([pitch, pitch + 12], quarterLength=0.25))
        else:
            for pitch in (72, 74, 76, 77):
                upper.append(note.Note(pitch, quarterLength=1))
        for pitch in (48, 55):
            lower.append(note.Note(pitch, quarterLength=2))
        right.append(upper)
        left.append(lower)
    score = stream.Score([right, left])
    path = "octave_study_test.musicxml"
    score.write("musicxml", fp=path)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    finally:
        os.unlink(path)


def test_analyser_finds_the_octave_bars():
    report = analyse_file(octave_study_xml(), "study.musicxml")
    assert report.measures == 12
    assert report.passages, "expected at least one hard passage"
    top = report.passages[0]
    assert 8 <= top.start <= 10 and 10 <= top.end <= 12
    assert "Blocked octaves" in top.techniques
    assert top.label.lower().startswith(("octave", "closing", "opening")) or "octave" in top.label.lower()
    assert "Blocked octaves" in dict(report.techniques)


def test_library_ships_with_real_passages():
    entries = load_library()["entries"]
    assert len(entries) > 500
    with_passages = [entry for entry in entries if entry["passages"]]
    assert len(with_passages) / len(entries) > 0.9
    for entry in entries[:50]:
        assert 0 < entry["difficulty"] <= 100
        for passage in entry["passages"]:
            assert passage["start"] <= passage["end"]
            assert passage["description"].startswith(("Bar", "Bars"))


@pytest.mark.parametrize(
    ("title", "composer", "expected"),
    [
        ("12 Études, op. 10: No. 1 in C major", "Frédéric Chopin", "Étude in C major"),
        ("Piano Sonata no. 14 in C-sharp minor, op. 27 no. 2: III. Presto agitato", "Ludwig van Beethoven", "III. Presto agitato"),
        ("Das Wohltemperierte Klavier I, BWV 846: Fuge", "Johann Sebastian Bach", "Fugue in C major"),
        ("Mazurkas, op. 17: No. 4 in A minor", "Frédéric Chopin", "Mazurka in A minor"),
        ("Harmonies du soir", "Franz Liszt", "Harmonies du soir"),
        ("Maple Leaf Rag", "Scott Joplin", "Maple Leaf Rag"),
    ],
)
def test_imported_titles_find_their_library_entry(title, composer, expected):
    found = find_entries(title, composer)
    assert found, title
    assert expected in found[0]["title"]


def test_whole_sonata_brings_every_movement():
    found = find_entries("Piano Sonata no. 14 in C-sharp minor, op. 27 no. 2", "Ludwig van Beethoven")
    assert [entry["movement"][0] for entry in found] == [1, 2, 3]


def test_no_false_match_on_shared_generic_title():
    assert find_entries("Sonata in D minor, K. 141, L. 422", "Domenico Scarlatti") == []
    assert find_entries("Islamey", "Franz Liszt") == []


def test_catalogue_keys_handle_colons_and_leading_zeros():
    assert "op10n1" in catalogue_keys("12 Études, op. 10: No. 1")
    assert "k75" in catalogue_keys("K. 075")
    assert "hobxvi52" in catalogue_keys("Hob. XVI:52")


def test_score_files_are_sniffed():
    assert sniff_score(b"%PDF-1.7 ...", ".pdf")
    assert not sniff_score(b"<html>", ".pdf")
    assert sniff_score(b"MThd\x00\x00", ".mid")
    assert sniff_score(b"PK\x03\x04", ".mxl")
    assert sniff_score(b'<?xml version="1.0"?><score-partwise version="4.0">', ".musicxml")
    assert not sniff_score(b"hello", ".xml")


def test_audio_lock_turns_off_grading_and_verification(monkeypatch):
    from app.core.config import settings
    from app.models.models import Piece
    from app.services.repertoire import RepertoireService

    piece = Piece(title="Hard piece")
    piece.difficulty_score = 95
    monkeypatch.setattr(settings, "audio_features_enabled", False)
    assert RepertoireService.requires_grading(piece) is False
    assert piece.requires_verification is False
    monkeypatch.setattr(settings, "audio_features_enabled", True)
    assert RepertoireService.requires_grading(piece) is True
    assert piece.requires_verification is True


TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
async def test_uploaded_musicxml_marks_passages_on_the_piece(tmp_path):
    import io
    import uuid

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.storage import LocalStorage
    from app.models.models import Passage, PdfSubmission, Piece, RepertoireEntry, Technique, User
    from app.services.analyzers import ScoreAnalyzer, load_submission

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = LocalStorage(root=str(tmp_path))
    async with factory() as session:
        if (await session.execute(select(Technique).limit(1))).scalar_one_or_none() is None:
            pytest.skip("test database has no techniques; seed it first")
        user = User(email=f"score-{uuid.uuid4().hex[:8]}@test.dev", password_hash="x")
        piece = Piece(title="Octave study for tests")
        session.add_all([user, piece])
        await session.flush()
        entry = RepertoireEntry(user_id=user.id, piece_id=piece.id)
        session.add(entry)
        await session.flush()
        key = storage.build_key(user.id, "scores", "study.musicxml")
        storage.save(io.BytesIO(octave_study_xml()), key)
        submission = PdfSubmission(repertoire_entry_id=entry.id, storage_key=key, musicxml_key=key)
        session.add(submission)
        await session.commit()
        ids = (user.id, piece.id, submission.id)

    try:
        async with factory() as session:
            loaded = await load_submission(session, ids[2])
            analysis = await ScoreAnalyzer(session, storage).run(loaded)
            await session.commit()
            assert "hard passage" in analysis.summary
        async with factory() as session:
            passages = (await session.execute(select(Passage).where(Passage.piece_id == ids[1]))).scalars().all()
            assert passages
            assert any(9 <= p.start_measure <= 11 for p in passages)
            assert all(p.description for p in passages)
    finally:
        async with factory() as session:
            await session.execute(delete(RepertoireEntry).where(RepertoireEntry.user_id == ids[0]))
            await session.execute(delete(User).where(User.id == ids[0]))
            await session.execute(delete(Piece).where(Piece.id == ids[1]))
            await session.commit()
        await engine.dispose()
