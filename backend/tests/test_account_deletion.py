import io
import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_file_storage
from app.core.database import get_session
from app.core.security import hasher
from app.core.storage import LocalStorage
from app.main import app
from app.services import account

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


def put(storage, key, body=b"data"):
    storage.save(io.BytesIO(body), key)
    return key


def test_delete_user_files_only_touches_that_user(tmp_path):
    storage = LocalStorage(root=str(tmp_path))
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    put(storage, f"scores/{mine}/a.pdf")
    put(storage, f"recordings/{mine}/b.wav")
    put(storage, f"recordings/{mine}/nested/c.wav")
    kept = put(storage, f"scores/{theirs}/d.pdf")
    assert storage.delete_user_files(mine) == 3
    assert not (tmp_path / "scores" / str(mine)).exists()
    assert not (tmp_path / "recordings" / str(mine)).exists()
    assert storage.exists(kept)


def test_delete_prefix_refuses_the_storage_root(tmp_path):
    storage = LocalStorage(root=str(tmp_path))
    kept = put(storage, f"scores/{uuid.uuid4()}/a.pdf")
    assert storage.delete_prefix("") == 0
    assert storage.exists(kept)


def test_remove_files_keeps_going_after_a_failure(tmp_path):
    storage = LocalStorage(root=str(tmp_path))
    user_id = uuid.uuid4()
    good = put(storage, f"scores/{user_id}/a.pdf")
    outside = put(storage, "elsewhere/b.mid")
    original = storage.delete

    def flaky(key):
        if key == "broken":
            raise RuntimeError("storage offline")
        return original(key)

    storage.delete = flaky
    removed, errors = account.remove_files(storage, user_id, ["broken", outside, good])
    assert errors == 1
    assert removed == 2
    assert not storage.exists(outside)
    assert not storage.exists(good)


@pytest.fixture
def signed_in(tmp_path, monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), password_hash=hasher.hash("correct horse"))
    calls = []

    async def fake_delete(session, target, storage):
        calls.append((target, storage))

    async def fake_session():
        yield SimpleNamespace()

    storage = LocalStorage(root=str(tmp_path))
    monkeypatch.setattr("app.api.v1.auth.delete_account", fake_delete)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_file_storage] = lambda: storage
    yield SimpleNamespace(user=user, calls=calls, storage=storage)
    app.dependency_overrides.clear()


async def send(payload):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request("DELETE", "/api/v1/auth/me", json=payload, headers={"Authorization": "Bearer t"})


async def test_delete_me_removes_the_account(signed_in):
    response = await send({"password": "correct horse", "confirmation": "DELETE"})
    assert response.status_code == 204
    assert signed_in.calls == [(signed_in.user, signed_in.storage)]


async def test_delete_me_requires_the_typed_confirmation(signed_in):
    response = await send({"password": "correct horse", "confirmation": "delete it"})
    assert response.status_code == 400
    assert signed_in.calls == []


async def test_delete_me_requires_the_password(signed_in):
    response = await send({"password": "wrong", "confirmation": "DELETE"})
    assert response.status_code == 403
    assert signed_in.calls == []


async def test_delete_me_requires_sign_in():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request("DELETE", "/api/v1/auth/me", json={"password": "x", "confirmation": "DELETE"})
    assert response.status_code == 401


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated, seeded database to run")
async def test_delete_account_removes_rows_and_files(tmp_path):
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import (
        AIGeneration,
        AudioSubmission,
        GenerationStatus,
        PdfSubmission,
        Piece,
        RepertoireEntry,
        Submission,
        TextSubmission,
        User,
        Wallet,
    )
    from app.services import coach_feedback

    storage = LocalStorage(root=str(tmp_path))
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        piece_id = (await session.execute(select(Piece.id).order_by(Piece.id).limit(1))).scalar_one_or_none()
        if piece_id is None:
            pytest.skip("test database has no pieces; seed it first")
        leaving = User(email=f"leaving-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        staying = User(email=f"staying-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        session.add_all([leaving, staying])
        await session.flush()
        entry = RepertoireEntry(user_id=leaving.id, piece_id=piece_id)
        other_entry = RepertoireEntry(user_id=staying.id, piece_id=piece_id)
        session.add_all([entry, other_entry, Wallet(user_id=leaving.id)])
        await session.flush()
        score = put(storage, storage.build_key(leaving.id, "scores", "a.pdf"))
        xml = put(storage, f"musicxml/{leaving.id}/a.musicxml")
        take = put(storage, storage.build_key(leaving.id, "recordings", "b.wav"))
        other_score = put(storage, storage.build_key(staying.id, "scores", "c.pdf"))
        audio = AudioSubmission(repertoire_entry_id=entry.id, storage_key=take)
        session.add_all(
            [
                PdfSubmission(repertoire_entry_id=entry.id, storage_key=score, musicxml_key=xml),
                TextSubmission(repertoire_entry_id=entry.id, body="slow hands"),
                PdfSubmission(repertoire_entry_id=other_entry.id, storage_key=other_score),
                audio,
            ]
        )
        await session.flush()
        session.add(
            AIGeneration(
                purpose=coach_feedback.PURPOSE,
                subject_key=coach_feedback.subject_key(audio.id),
                status=GenerationStatus.DONE,
                output={"summary": "x"},
            )
        )
        await session.commit()
        leaving_id, staying_id = leaving.id, staying.id

        try:
            report = await account.delete_account(session, leaving, storage)
            assert report.files_found == 3
            assert report.file_errors == 0
            assert await session.get(User, leaving_id) is None
            assert (await session.execute(select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == leaving_id))).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(Submission).where(Submission.repertoire_entry_id == entry.id))).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(Wallet).where(Wallet.user_id == leaving_id))).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(AIGeneration).where(AIGeneration.subject_key == coach_feedback.subject_key(audio.id)))).scalar_one() == 0
            assert not storage.exists(score) and not storage.exists(xml) and not storage.exists(take)
            assert storage.exists(other_score)
            assert await session.get(User, staying_id) is not None
        finally:
            await session.rollback()
            from sqlalchemy import delete

            await session.execute(delete(User).where(User.id.in_([leaving_id, staying_id])))
            await session.commit()
    await engine.dispose()
