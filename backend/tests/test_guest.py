import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import tokens
from app.main import app
from app.services.guest import GUEST_DOMAIN, guest_email
from app.services.quickstart import spread
from tests.test_billing import stripe_on
from tests.test_keyboard_api import TEST_DB, needs_db

PASSWORD = "sturdy-pass-123"


def http():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def db(monkeypatch):
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.database import get_session
    from app.core.rate_limit import limiter
    from app.models.models import Piece, User

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    made = SimpleNamespace(emails=[], pieces=[])

    async def override_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    limiter.reset()
    try:
        yield SimpleNamespace(factory=factory, made=made)
    finally:
        app.dependency_overrides.clear()
        async with factory() as session:
            await session.execute(delete(User).where(User.email.in_(made.emails)))
            await session.execute(delete(User).where(User.email.like(f"%@{GUEST_DOMAIN}")))
            if made.pieces:
                await session.execute(delete(Piece).where(Piece.id.in_(made.pieces)))
            await session.commit()
        await engine.dispose()


async def new_guest(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def me(client, token):
    response = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert response.status_code == 200, response.text
    return response.json()


async def make_piece(db, title, difficulty=30):
    from app.models.models import Passage, PassageSource, Piece

    async with db.factory() as session:
        piece = Piece(title=f"{title} {uuid.uuid4().hex[:6]}", difficulty_score=Decimal(str(difficulty)))
        session.add(piece)
        await session.flush()
        session.add(Passage(piece_id=piece.id, start_measure=1, end_measure=4, label="Opening", difficulty_score=Decimal("6.0"), source=PassageSource.CATALOG))
        await session.commit()
        db.made.pieces.append(piece.id)
        return piece.id


async def make_real_user(db, email=None):
    from app.core.security import hasher
    from app.models.models import User

    email = email or f"real-{uuid.uuid4().hex[:8]}@test.dev"
    async with db.factory() as session:
        user = User(email=email, password_hash=hasher.hash(PASSWORD), display_name="Real Ana")
        session.add(user)
        await session.commit()
        db.made.emails.append(email)
        return user.id, email


async def user_row(db, user_id):
    from app.models.models import User

    async with db.factory() as session:
        return await session.get(User, user_id)


async def give_entry(db, user_id, piece_id, *, tempo=None, practised=None, started=None, notes=None):
    from app.models.models import RepertoireEntry

    async with db.factory() as session:
        entry = RepertoireEntry(user_id=user_id, piece_id=piece_id, current_tempo_bpm=tempo, last_practiced_at=practised, started_on=started, notes=notes)
        session.add(entry)
        await session.commit()
        return entry.id


async def log_minutes(db, user_id, entry_id, minutes, *, when=None):
    from app.models.models import PracticeSession, SessionItem

    when = when or datetime.now(timezone.utc) - timedelta(minutes=30)
    async with db.factory() as session:
        practice = PracticeSession(user_id=user_id, started_at=when, ended_at=when + timedelta(minutes=minutes))
        session.add(practice)
        await session.flush()
        session.add(SessionItem(session_id=practice.id, repertoire_entry_id=entry_id, minutes=minutes))
        await session.commit()
        return practice.id


async def give_wallet(db, user_id, xp, gold):
    from app.models.models import Wallet

    async with db.factory() as session:
        session.add(Wallet(user_id=user_id, xp=xp, gold=gold, lifetime_xp=xp, lifetime_gold=gold))
        await session.commit()


def test_guest_addresses_are_unique_and_on_our_own_domain():
    first, second = guest_email(), guest_email()
    assert first != second
    assert first.endswith(f"@{GUEST_DOMAIN}") and first.startswith("guest-")


def test_the_starter_list_spreads_across_the_difficulty_range_with_one_piece_per_composer():
    pieces = [SimpleNamespace(id=index, composer_id=index // 2, difficulty_score=Decimal(index)) for index in range(40)]
    chosen = spread(pieces, 6)
    assert len(chosen) == 6
    assert len({piece.composer_id for piece in chosen}) == 6
    scores = [float(piece.difficulty_score) for piece in chosen]
    assert scores == sorted(scores)
    assert scores[-1] - scores[0] >= 30
    short = spread(pieces[:6], 6)
    assert len(short) == 3


@needs_db
async def test_a_first_launch_creates_a_guest_with_a_working_token(db):
    async with http() as client:
        token = await new_guest(client)
        profile = await me(client, token)
    assert profile["is_guest"] is True
    assert profile["email"].endswith(f"@{GUEST_DOMAIN}")
    assert tokens.subject(token) == profile["id"]


@needs_db
async def test_a_guest_can_never_sign_in_with_a_password(db):
    async with http() as client:
        token = await new_guest(client)
        email = (await me(client, token))["email"]
        attempt = await client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
    assert attempt.status_code == 401


@needs_db
async def test_choosing_a_level_and_one_piece_finishes_onboarding(db):
    async with http() as client:
        token = await new_guest(client)
        before = (await client.get("/api/v1/onboarding/status", headers=bearer(token))).json()
        assert before["complete"] is False
        starters = await client.get("/api/v1/onboarding/starter-pieces", params={"level": "beginner"}, headers=bearer(token))
        assert starters.status_code == 200
        picks = starters.json()
        assert 1 <= len(picks) <= 6
        assert all(float(item["difficulty_score"]) <= 38 for item in picks)
        done = await client.post("/api/v1/onboarding/quick", json={"self_level": "beginner", "piece_id": picks[0]["id"]}, headers=bearer(token))
        assert done.status_code == 200, done.text
        body = done.json()
        assert body["status"]["complete"] is True
        assert body["status"]["pieces_in_progress"] == 1
        assert body["piece_title"] == picks[0]["title"]
        profile = await me(client, token)
        assert profile["self_level"] == "beginner"
        assert profile["years_playing"] == 1
        assert profile["tier_quiz_completed_at"] and profile["tastes_completed_at"]


@needs_db
async def test_the_starter_pieces_follow_the_chosen_level(db):
    async with http() as client:
        token = await new_guest(client)
        easy = (await client.get("/api/v1/onboarding/starter-pieces", params={"level": "beginner"}, headers=bearer(token))).json()
        hard = (await client.get("/api/v1/onboarding/starter-pieces", params={"level": "advanced"}, headers=bearer(token))).json()
        junk = await client.get("/api/v1/onboarding/starter-pieces", params={"level": "wizard"}, headers=bearer(token))
    assert max(float(item["difficulty_score"]) for item in easy) <= 38
    assert min(float(item["difficulty_score"]) for item in hard) >= 55
    assert junk.status_code == 422


@needs_db
async def test_an_unknown_piece_is_refused(db):
    async with http() as client:
        token = await new_guest(client)
        response = await client.post("/api/v1/onboarding/quick", json={"self_level": "beginner", "piece_id": 99999999}, headers=bearer(token))
    assert response.status_code == 404


@needs_db
async def test_the_first_mission_is_ready_straight_after_quick_start(db):
    async with http() as client:
        token = await new_guest(client)
        picks = (await client.get("/api/v1/onboarding/starter-pieces", params={"level": "intermediate"}, headers=bearer(token))).json()
        await client.post("/api/v1/onboarding/quick", json={"self_level": "intermediate", "piece_id": picks[0]["id"]}, headers=bearer(token))
        mission = (await client.get("/api/v1/practice/mission", params={"first": "true"}, headers=bearer(token))).json()
    assert mission["kind"] == "first"
    assert [step["kind"] for step in mission["steps"]] == ["warmup", "passage", "playthrough"]
    assert mission["total_minutes"] <= 6
    assert mission["steps"][1]["piece_title"] == picks[0]["title"]


@needs_db
async def test_signing_up_keeps_everything_the_guest_did(db):
    piece = await make_piece(db, "Minuet")
    async with http() as client:
        token = await new_guest(client)
        guest = await me(client, token)
        guest_id = uuid.UUID(guest["id"])
        await client.post("/api/v1/onboarding/quick", json={"self_level": "beginner", "piece_id": piece}, headers=bearer(token))
        from sqlalchemy import select

        from app.models.models import RepertoireEntry

        async with db.factory() as session:
            entry_id = (await session.execute(select(RepertoireEntry.id).where(RepertoireEntry.user_id == guest_id))).scalar_one()
        await log_minutes(db, guest_id, entry_id, 12)
        await give_wallet(db, guest_id, 120, 15)
        email = f"signup-{uuid.uuid4().hex[:8]}@test.dev"
        db.made.emails.append(email)
        created = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "display_name": "Ana"},
            headers={"X-Guest-Token": token},
        )
        assert created.status_code == 201, created.text
        real = created.json()["access_token"]
        profile = await me(client, real)
        assert profile["is_guest"] is False and profile["email"] == email
        assert profile["self_level"] == "beginner"
        assert profile["tier_quiz_completed_at"] and profile["tastes_completed_at"]
        status = (await client.get("/api/v1/onboarding/status", headers=bearer(real))).json()
        assert status["complete"] is True and status["pieces_in_progress"] == 1
        entries = (await client.get("/api/v1/repertoire", headers=bearer(real))).json()["items"]
        assert [item["piece"]["id"] for item in entries] == [piece]
        sessions = (await client.get("/api/v1/practice/sessions", headers=bearer(real))).json()["items"]
        assert len(sessions) == 1 and sessions[0]["items"][0]["minutes"] == 12
        streak = (await client.get("/api/v1/progress/streak", headers=bearer(real))).json()
        assert streak["today_done"] is True
        gone = await client.get("/api/v1/auth/me", headers=bearer(token))
        assert gone.status_code == 401
    from app.models.models import User, Wallet

    async with db.factory() as session:
        assert await session.get(User, guest_id) is None
        stored = await session.get(Wallet, uuid.UUID(profile["id"]))
        assert (stored.xp, stored.gold) == (120, 15)


@needs_db
async def test_signing_in_to_an_existing_account_merges_the_guests_practice_into_it(db):
    shared = await make_piece(db, "Shared")
    only_guest = await make_piece(db, "Guest only")
    only_real = await make_piece(db, "Real only")
    real_id, email = await make_real_user(db)
    long_ago = datetime.now(timezone.utc) - timedelta(days=20)
    real_shared = await give_entry(db, real_id, shared, tempo=60, practised=long_ago, started=date(2026, 9, 1), notes="mine")
    await give_entry(db, real_id, only_real)
    await give_wallet(db, real_id, 300, 40)
    async with http() as client:
        token = await new_guest(client)
        guest_id = uuid.UUID((await me(client, token))["id"])
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        guest_shared = await give_entry(db, guest_id, shared, tempo=84, practised=recent, started=date(2026, 10, 20), notes="guest")
        await give_entry(db, guest_id, only_guest)
        practice = await log_minutes(db, guest_id, guest_shared, 10)
        await give_wallet(db, guest_id, 50, 5)
        logged_in = await client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        assert logged_in.status_code == 200, logged_in.text
        real = logged_in.json()["access_token"]
        entries = (await client.get("/api/v1/repertoire", params={"limit": 100}, headers=bearer(real))).json()["items"]
    by_piece = {item["piece"]["id"]: item for item in entries}
    assert set(by_piece) == {shared, only_guest, only_real}
    merged = by_piece[shared]
    assert merged["id"] == str(real_shared)
    assert merged["current_tempo_bpm"] == 84
    assert merged["notes"] == "mine"
    assert merged["started_on"] == "2026-09-01"
    from sqlalchemy import select

    from app.models.models import PracticeSession, RepertoireEntry, SessionItem, User, Wallet

    async with db.factory() as session:
        assert await session.get(User, guest_id) is None
        moved = await session.get(PracticeSession, practice)
        assert moved.user_id == real_id
        item = (await session.execute(select(SessionItem).where(SessionItem.session_id == practice))).scalar_one()
        assert item.repertoire_entry_id == real_shared
        wallet = await session.get(Wallet, real_id)
        assert (wallet.xp, wallet.gold, wallet.lifetime_xp) == (350, 45, 350)
        stored = await session.get(RepertoireEntry, real_shared)
        assert (datetime.now(timezone.utc) - stored.last_practiced_at).total_seconds() < 3 * 3600


@needs_db
async def test_techniques_missions_and_preferences_merge_without_overwriting_the_real_account(db):
    from sqlalchemy import select

    from app.models.models import Mission, SelfRating, Technique, UserTechniqueProfile

    real_id, email = await make_real_user(db)
    async with db.factory() as session:
        techniques = (await session.execute(select(Technique).order_by(Technique.id).limit(3))).scalars().all()
        session.add(UserTechniqueProfile(user_id=real_id, technique_id=techniques[0].id, self_rating=SelfRating.STRENGTH, proficiency_score=Decimal("9.00")))
        session.add(Mission(user_id=real_id, day=date.today(), steps=[{"index": 0, "kind": "warmup"}], progress=[]))
        await session.commit()
    async with http() as client:
        token = await new_guest(client)
        guest_id = uuid.UUID((await me(client, token))["id"])
        async with db.factory() as session:
            session.add(UserTechniqueProfile(user_id=guest_id, technique_id=techniques[0].id, self_rating=SelfRating.STRUGGLE, proficiency_score=Decimal("2.00")))
            session.add(UserTechniqueProfile(user_id=guest_id, technique_id=techniques[1].id, self_rating=SelfRating.STRUGGLE, proficiency_score=Decimal("3.00")))
            session.add(Mission(user_id=guest_id, day=date.today(), steps=[{"index": 0, "kind": "freeplay"}], progress=[]))
            session.add(Mission(user_id=guest_id, day=date.today() - timedelta(days=1), steps=[{"index": 0, "kind": "warmup"}], progress=[]))
            await session.commit()
        logged_in = await client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        assert logged_in.status_code == 200
    async with db.factory() as session:
        profiles = {row.technique_id: row for row in (await session.execute(select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == real_id))).scalars().all()}
        assert set(profiles) == {techniques[0].id, techniques[1].id}
        assert profiles[techniques[0].id].proficiency_score == Decimal("9.00")
        assert profiles[techniques[1].id].proficiency_score == Decimal("3.00")
        missions = {row.day: row for row in (await session.execute(select(Mission).where(Mission.user_id == real_id))).scalars().all()}
        assert set(missions) == {date.today(), date.today() - timedelta(days=1)}
        assert missions[date.today()].steps[0]["kind"] == "warmup"


@needs_db
async def test_a_bad_expired_or_real_users_token_in_the_header_is_ignored(db):
    real_id, email = await make_real_user(db)
    other_id, other_email = await make_real_user(db)
    piece = await make_piece(db, "Untouched")
    await give_entry(db, other_id, piece)
    async with http() as client:
        other_token = tokens.create_access_token(str(other_id))
        for header in ("not-a-token", other_token, tokens.create_access_token(str(uuid.uuid4()))):
            response = await client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD}, headers={"X-Guest-Token": header})
            assert response.status_code == 200
    from sqlalchemy import func, select

    from app.models.models import RepertoireEntry, User

    async with db.factory() as session:
        assert await session.get(User, other_id) is not None
        assert (await session.execute(select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == other_id))).scalar_one() == 1
        assert (await session.execute(select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == real_id))).scalar_one() == 0


@needs_db
async def test_a_guest_token_can_only_be_merged_once(db):
    piece = await make_piece(db, "Once")
    first_id, first_email = await make_real_user(db)
    second_id, second_email = await make_real_user(db)
    async with http() as client:
        token = await new_guest(client)
        guest_id = uuid.UUID((await me(client, token))["id"])
        await give_entry(db, guest_id, piece)
        one = await client.post("/api/v1/auth/token", json={"email": first_email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        two = await client.post("/api/v1/auth/token", json={"email": second_email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        assert one.status_code == 200 and two.status_code == 200
    from sqlalchemy import func, select

    from app.models.models import RepertoireEntry

    async with db.factory() as session:
        count = lambda user: select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == user)
        assert (await session.execute(count(first_id))).scalar_one() == 1
        assert (await session.execute(count(second_id))).scalar_one() == 0


@needs_db
async def test_logging_in_without_a_guest_token_changes_nothing(db):
    real_id, email = await make_real_user(db)
    async with http() as client:
        response = await client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
        form = await client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200 and form.status_code == 200


@needs_db
async def test_the_form_login_merges_too(db):
    piece = await make_piece(db, "Form")
    real_id, email = await make_real_user(db)
    async with http() as client:
        token = await new_guest(client)
        guest_id = uuid.UUID((await me(client, token))["id"])
        await give_entry(db, guest_id, piece)
        response = await client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        assert response.status_code == 200
    from sqlalchemy import func, select

    from app.models.models import RepertoireEntry

    async with db.factory() as session:
        assert (await session.execute(select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == real_id))).scalar_one() == 1


@needs_db
async def test_the_merge_refuses_to_join_two_real_accounts_or_a_guest_to_itself(db):
    from app.models.models import User
    from app.services.guest import create_guest, merge_guest

    real_id, _ = await make_real_user(db)
    other_id, _ = await make_real_user(db)
    async with db.factory() as session:
        real = await session.get(User, real_id)
        other = await session.get(User, other_id)
        guest = await create_guest(session)
        with pytest.raises(ValueError):
            await merge_guest(session, real, other)
        with pytest.raises(ValueError):
            await merge_guest(session, guest, guest)
        with pytest.raises(ValueError):
            await merge_guest(session, real, guest)
        await session.rollback()


@needs_db
async def test_a_guest_cannot_start_a_checkout(db, stripe_on):
    async with http() as client:
        token = await new_guest(client)
        response = await client.post("/api/v1/billing/checkout", json={"interval": "month"}, headers=bearer(token))
    assert response.status_code == 409
    assert "Create an account first" in response.json()["detail"]
    assert not [call for call in stripe_on.calls if call[0] in ("customer", "checkout")]


@needs_db
async def test_a_guest_works_through_a_mission_and_it_follows_them_into_the_account(db):
    piece = await make_piece(db, "Mission")
    async with http() as client:
        token = await new_guest(client)
        await client.post("/api/v1/onboarding/quick", json={"self_level": "beginner", "piece_id": piece}, headers=bearer(token))
        mission = (await client.get("/api/v1/practice/mission", params={"first": "true"}, headers=bearer(token))).json()
        for step in mission["steps"]:
            result = await client.post(f"/api/v1/practice/mission/{mission['id']}/steps/{step['index']}", json={"status": "done", "seconds": 150}, headers=bearer(token))
            assert result.status_code == 200, result.text
        assert result.json()["finished"] is True
        email = f"mission-{uuid.uuid4().hex[:8]}@test.dev"
        db.made.emails.append(email)
        created = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD}, headers={"X-Guest-Token": token})
        real = created.json()["access_token"]
        today = (await client.get("/api/v1/practice/mission", headers=bearer(real))).json()
        streak = (await client.get("/api/v1/progress/streak", headers=bearer(real))).json()
    assert today["id"] == mission["id"]
    assert today["completed_at"] is not None
    assert streak["today_done"] is True and streak["current"] == 1
