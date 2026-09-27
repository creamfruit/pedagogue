import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.services.meteor import shower_window, spread_pick

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def test_spread_pick_spans_the_range_and_is_deterministic():
    candidates = list(range(1, 31))
    picks = spread_pick(candidates, 5, "2026-09-27")
    assert len(set(picks)) == 5
    assert picks == spread_pick(candidates, 5, "2026-09-27")
    assert min(picks) <= 6 and max(picks) >= 25
    assert spread_pick([1, 2], 5, "x") == [1, 2]


def test_window_states():
    shower = SimpleNamespace(starts_at=NOW, ends_at=NOW + timedelta(hours=2))
    assert shower_window(shower, NOW - timedelta(seconds=1)) == "upcoming"
    assert shower_window(shower, NOW) == "active"
    assert shower_window(shower, NOW + timedelta(hours=2)) == "over"


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated database to run")
async def test_schedule_catch_and_after_the_window():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import (
        LedgerEntry,
        LedgerReason,
        MeteorShower,
        Piece,
        RepertoireEntry,
        RepertoireStatus,
        User,
    )
    from app.services.economy import EconomyService
    from app.services.meteor import MeteorService

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(email="meteor-a@example.com", password_hash="x", display_name="Meteor")
        session.add(user)
        await session.commit()
        user_id = user.id
        shower_ids = []
        try:
            pieces = (
                await session.execute(
                    select(Piece.id).where(Piece.is_user_created.is_(False), Piece.parent_piece_id.is_(None)).order_by(Piece.id).limit(4)
                )
            ).scalars().all()
            assert len(pieces) == 4, "the test database needs the seeded catalogue"
            service = MeteorService(session)
            start = datetime.now(timezone.utc) - timedelta(minutes=5)
            shower = await service.schedule(name="Test shower", starts_at=start, hours=1, piece_ids=pieces[:3])
            shower_ids.append(shower.id)
            with pytest.raises(ValueError):
                await service.schedule(name="Clash", starts_at=start + timedelta(minutes=30), hours=1, piece_ids=pieces[:3])
            with pytest.raises(ValueError):
                await service.schedule(name="Too few", starts_at=start + timedelta(days=3), hours=1, piece_ids=pieces[:2])

            view = await service.view(user)
            assert view["active"]["id"] == shower.id and view["active"]["open"] == 3

            result = await service.catch(user, shower.id, pieces[0])
            assert (result["xp"], result["gold"]) == (40, 25)
            with pytest.raises(ValueError):
                await service.catch(user, shower.id, pieces[0])
            with pytest.raises(LookupError):
                await service.catch(user, shower.id, pieces[3])

            entry = (
                await session.execute(
                    select(RepertoireEntry).where(RepertoireEntry.user_id == user.id, RepertoireEntry.piece_id == pieces[0])
                )
            ).scalar_one()
            await session.refresh(entry, ["piece"])
            await session.delete(entry)
            await session.flush()
            again = await service.catch(user, shower.id, pieces[0])
            assert (again["xp"], again["gold"]) == (0, 0)

            await service.end(shower.id)
            assert (await service.view(user))["active"] is None
            with pytest.raises(PermissionError):
                await service.catch(user, shower.id, pieces[1])

            caught = (
                await session.execute(
                    select(RepertoireEntry).where(RepertoireEntry.user_id == user.id, RepertoireEntry.piece_id == pieces[0])
                )
            ).scalar_one()
            assert caught.meteor_shower_id == shower.id
            await session.refresh(caught, ["piece"])
            caught.status = RepertoireStatus.PERFORMANCE_READY
            learned = await EconomyService(session).reward_learning(user, caught)
            plain = await EconomyService(session).reward_learning(user, caught)
            assert plain is None
            from app.services.economy import learning_reward

            base_xp, _ = learning_reward(caught.piece.difficulty_score)
            assert learned.delta_xp == round(base_xp * 1.5)
        finally:
            await session.rollback()
            await session.execute(delete(LedgerEntry).where(LedgerEntry.user_id == user_id))
            await session.execute(delete(RepertoireEntry).where(RepertoireEntry.user_id == user_id))
            await session.execute(delete(MeteorShower).where(MeteorShower.id.in_(shower_ids or [0])))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    await engine.dispose()
