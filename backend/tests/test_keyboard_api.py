import io
import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.deps import get_current_user, get_file_storage
from app.core.config import settings
from app.core.database import get_session
from app.core.rate_limit import limiter
from app.core.storage import LocalStorage
from app.main import app
from app.schemas.keyboard import AttemptIn
from app.services import keyboard as keyboard_service
from app.services.keyboard import Reference, reference_from_parsed
from tests.test_score_library import octave_study_xml

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")


def parsed_score():
    events = [SimpleNamespace(onset=float(i), duration=1.0, midi=60 + i, hand=0, measure=1 + i // 4) for i in range(8)]
    return SimpleNamespace(events=events, measure_starts={1: 0.0, 2: 4.0}, measure_lengths={1: 4.0, 2: 4.0}, quarter_bpm=96.0)


def test_a_parsed_score_becomes_a_sliceable_reference():
    reference = reference_from_parsed(parsed_score(), "musicxml")
    assert (reference.first_bar, reference.last_bar, reference.beats_per_bar) == (1, 2, 4)
    second = reference.slice(2, 2)
    assert [(note.onset, note.midi, note.bar) for note in second] == [(0.0, 64, 2), (1.0, 65, 2), (2.0, 66, 2), (3.0, 67, 2)]
    assert reference.slice(5, 6) == []
    assert len(reference.slice(1, 2)) == 8


def test_waltz_and_compound_bars_give_the_right_beat_count():
    waltz = Reference("musicxml", 120.0, [(0.0, 60, 1)], {1: 0.0, 2: 3.0}, {1: 3.0, 2: 3.0})
    assert waltz.beats_per_bar == 3
    assert Reference("midi", 100.0).beats_per_bar == 4


def test_attempts_must_say_what_they_need():
    with pytest.raises(ValidationError):
        AttemptIn(mode="scored", start_bar=1, end_bar=2)
    with pytest.raises(ValidationError):
        AttemptIn(mode="scored", tempo_bpm=80)
    with pytest.raises(ValidationError):
        AttemptIn(mode="wait", start_bar=4, end_bar=2)
    with pytest.raises(ValidationError):
        AttemptIn(mode="free", tempo_bpm=10)
    with pytest.raises(ValidationError):
        AttemptIn(mode="free", tempo_bpm=80, notes=[{"t": 0, "midi": 200}])
    assert AttemptIn(mode="wait", start_bar=1, end_bar=2).notes == []
    assert AttemptIn(mode="free", tempo_bpm=80).start_bar is None


@pytest.fixture
async def world(tmp_path, monkeypatch):
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import PdfSubmission, Piece, RepertoireEntry, Subscription, User

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    keyboard_service._cache.clear()
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    storage = LocalStorage(root=str(tmp_path))
    async with factory() as session:
        me = User(email=f"kb-{uuid.uuid4().hex[:8]}@test.dev", password_hash="x")
        other = User(email=f"kb-{uuid.uuid4().hex[:8]}@test.dev", password_hash="x")
        piece = Piece(title=f"Octave study {uuid.uuid4().hex[:6]}")
        session.add_all([me, other, piece])
        await session.flush()
        session.add(Subscription(user_id=me.id, status="active", stripe_customer_id=f"cus_{uuid.uuid4().hex[:12]}"))
        entry = RepertoireEntry(user_id=me.id, piece_id=piece.id, target_tempo_bpm=100)
        spare = await new_piece(session)
        bare = RepertoireEntry(user_id=me.id, piece_id=spare.id)
        session.add_all([entry, bare])
        await session.flush()
        key = storage.build_key(me.id, "musicxml", "study.musicxml")
        storage.save(io.BytesIO(octave_study_xml()), key)
        session.add(PdfSubmission(repertoire_entry_id=entry.id, storage_key=key, musicxml_key=key))
        await session.commit()
        ids = SimpleNamespace(user=me.id, other=other.id, piece=piece.id, spare=spare.id, entry=entry.id, bare=bare.id)
        current = SimpleNamespace(id=me.id)

    async def override_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_user():
        async with factory() as session:
            return await session.get(User, current.id)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_file_storage] = lambda: storage
    limiter.reset()
    try:
        yield SimpleNamespace(ids=ids, factory=factory, current=current, storage=storage)
    finally:
        app.dependency_overrides.clear()
        async with factory() as session:
            await session.execute(delete(User).where(User.id.in_([ids.user, ids.other])))
            await session.execute(delete(Piece).where(Piece.id.in_([ids.piece, ids.spare])))
            await session.commit()
        await engine.dispose()


async def new_piece(session):
    from app.models.models import Piece

    piece = Piece(title=f"Bare piece {uuid.uuid4().hex[:6]}")
    session.add(piece)
    await session.flush()
    return piece


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def perform(notes, tempo, drop=(), replace=None):
    replace = replace or {}
    return [
        {"t": onset * 60000.0 / tempo, "midi": replace.get(index, midi)}
        for index, (onset, midi, _bar) in enumerate(notes)
        if index not in drop
    ]


async def passage(http, entry, start=1, end=3):
    response = await http.get(f"/api/v1/keyboard/entries/{entry}/reference/notes", params={"start_bar": start, "end_bar": end})
    assert response.status_code == 200, response.text
    return response.json()


@needs_db
async def test_a_piece_without_a_reference_says_note_checking_is_unavailable(world):
    async with client() as http:
        summary = (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")).json()
        assert summary["available"] is False
        assert "isn't available" in summary["message"]
        assert "free play" in summary["message"].lower()
        assert (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference/notes", params={"start_bar": 1, "end_bar": 2})).status_code == 409
        refused = await http.post(
            f"/api/v1/keyboard/entries/{world.ids.bare}/attempts",
            json={"mode": "scored", "start_bar": 1, "end_bar": 2, "tempo_bpm": 80, "notes": []},
        )
        assert refused.status_code == 409
        assert "isn't available" in refused.json()["detail"]


@needs_db
async def test_an_uploaded_musicxml_score_is_the_reference(world):
    async with client() as http:
        summary = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference")).json()
        assert summary["available"] is True and summary["source"] == "musicxml"
        assert summary["first_bar"] == 1 and summary["last_bar"] == 12
        assert summary["target_tempo_bpm"] == 100
        notes = await passage(http, world.ids.entry, 2, 3)
        assert notes["bars"] == [2, 3]
        assert min(note[0] for note in notes["notes"]) == 0.0
        assert all(note[2] in (2, 3) for note in notes["notes"])


@needs_db
async def test_a_clean_scored_run_is_stored_and_climbs_the_ladder(world):
    from sqlalchemy import select

    from app.models.models import KeyboardAttempt, KeyboardAttemptBar

    async with client() as http:
        notes = (await passage(http, world.ids.entry, 1, 3))["notes"]
        body = {"mode": "scored", "start_bar": 1, "end_bar": 3, "tempo_bpm": 80, "duration_sec": 20, "notes": perform(notes, 80)}
        first = await http.post(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", json=body)
        assert first.status_code == 201, first.text
        data = first.json()
        assert data["accuracy"] == 1.0 and data["clean"] is True and data["note_checking"] is True
        assert [item["bar"] for item in data["bars"]] == [1, 2, 3]
        assert data["ladder"]["clean_streak"] == 1 and data["ladder"]["raised"] is False
        second = (await http.post(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", json=body)).json()
        assert second["ladder"]["raised"] is True
        assert second["ladder"]["recommended_tempo"] == 84
        state = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/ladder", params={"start_bar": 1, "end_bar": 3})).json()
        assert state["recommended_tempo"] == 84 and state["current_tempo"] == 80
    async with world.factory() as session:
        attempts = (await session.execute(select(KeyboardAttempt).where(KeyboardAttempt.repertoire_entry_id == world.ids.entry))).scalars().all()
        assert len(attempts) == 2 and all(a.clean and a.tempo_bpm == 80 and a.mode == "scored" for a in attempts)
        bars = (await session.execute(select(KeyboardAttemptBar).where(KeyboardAttemptBar.attempt_id == attempts[0].id))).scalars().all()
        assert sorted(b.bar for b in bars) == [1, 2, 3]
        assert all(float(b.accuracy) == 1.0 for b in bars)
        assert all(b.tempo_bpm is not None for b in bars)


@needs_db
async def test_wrong_notes_are_scored_against_the_right_bars_and_break_the_streak(world):
    async with client() as http:
        notes = (await passage(http, world.ids.entry, 1, 3))["notes"]
        bar_two = [index for index, note in enumerate(notes) if note[2] == 2][1]
        body = {"mode": "scored", "start_bar": 1, "end_bar": 3, "tempo_bpm": 80, "notes": perform(notes, 80, replace={bar_two: 90})}
        data = (await http.post(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", json=body)).json()
        assert data["clean"] is False and data["wrong"] >= 1 and data["missing"] >= 1
        by_bar = {item["bar"]: item for item in data["bars"]}
        assert by_bar[1]["accuracy"] == 1.0 and by_bar[3]["accuracy"] == 1.0
        assert by_bar[2]["accuracy"] < 1.0
        assert data["ladder"]["clean_streak"] == 0


@needs_db
async def test_wait_mode_is_scored_without_a_tempo(world):
    async with client() as http:
        notes = (await passage(http, world.ids.entry, 1, 2))["notes"]
        played = perform(notes, 40)
        body = {"mode": "wait", "start_bar": 1, "end_bar": 2, "notes": played}
        data = (await http.post(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", json=body)).json()
        assert data["mode"] == "wait" and data["tempo_bpm"] is None
        assert data["accuracy"] == 1.0 and data["timing"] is None and data["ladder"] is None


@needs_db
async def test_free_play_works_without_a_reference_and_says_so(world):
    async with client() as http:
        played = [{"t": i * 300.0, "midi": 60 + i % 4} for i in range(16)]
        data = (await http.post(f"/api/v1/keyboard/entries/{world.ids.bare}/attempts", json={"mode": "free", "tempo_bpm": 100, "notes": played})).json()
        assert data["mode"] == "free" and data["note_checking"] is False
        assert data["accuracy"] is None and data["expected"] == 0
        assert data["timing"] == 100.0 and data["evenness"] == 100.0
        assert "Note checking isn't available" in data["message"]
        assert data["ladder"]["current_tempo"] == 100


@needs_db
async def test_ranges_and_other_peoples_pieces_are_refused(world):
    async with client() as http:
        out_of_range = await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference/notes", params={"start_bar": 40, "end_bar": 41})
        assert out_of_range.status_code == 422
        assert "runs from bar 1 to bar 12" in out_of_range.json()["detail"]
        backwards = await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference/notes", params={"start_bar": 5, "end_bar": 2})
        assert backwards.status_code == 422
        world.current.id = world.ids.other
        stranger = await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference")
        assert stranger.status_code == 404
        attempt = await http.post(f"/api/v1/keyboard/entries/{world.ids.entry}/attempts", json={"mode": "free", "tempo_bpm": 90, "notes": []})
        assert attempt.status_code == 404


@needs_db
async def test_saving_runs_is_rate_limited(world, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_keyboard_attempt", "2/hour")
    async with client() as http:
        body = {"mode": "free", "tempo_bpm": 90, "notes": []}
        codes = [(await http.post(f"/api/v1/keyboard/entries/{world.ids.bare}/attempts", json=body)).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


@needs_db
async def test_free_play_climbs_its_own_ladder_without_a_reference(world):
    async with client() as http:
        played = [{"t": i * 375.0, "midi": 60 + i % 4} for i in range(16)]
        body = {"mode": "free", "tempo_bpm": 80, "notes": played}
        first = (await http.post(f"/api/v1/keyboard/entries/{world.ids.bare}/attempts", json=body)).json()
        assert first["clean"] is True and first["ladder"]["raised"] is False
        second = (await http.post(f"/api/v1/keyboard/entries/{world.ids.bare}/attempts", json=body)).json()
        assert second["ladder"]["raised"] is True and second["ladder"]["recommended_tempo"] == 84
        state = (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/ladder", params={"mode": "free"})).json()
        assert state["recommended_tempo"] == 84
        scored = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/ladder", params={"mode": "scored", "start_bar": 1, "end_bar": 3})).json()
        assert scored["current_tempo"] is None
