import os

import pytest
from sqlalchemy import delete, func, select

from app.services.streaks import nudge_message

TEST_DB = os.environ.get("PIANO_TEST_DATABASE_URL")


def test_nudge_message_names_the_gap_and_the_piece():
    assert nudge_message(None, None) == "You haven't logged a practice session yet."
    assert nudge_message(None, "Fur Elise") == "You haven't logged a practice session yet. Fur Elise is waiting."
    assert nudge_message(4, "Fur Elise").startswith("It's been 4 days since you last practised. Fur Elise is waiting.")


@pytest.mark.skipif(not TEST_DB, reason="set PIANO_TEST_DATABASE_URL to a disposable, migrated, seeded database to run")
async def test_tier_retake_updates_in_place():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Technique, User, UserTechniqueProfile
    from app.schemas.schemas import TierAssignment
    from app.services.onboarding import OnboardingService

    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        techniques = (await session.execute(select(Technique))).scalars().all()
        if not techniques:
            pytest.skip("test database has no techniques; seed it first")
        user = User(email="retake-probe@example.com", password_hash="x")
        session.add(user)
        await session.commit()
        try:
            service = OnboardingService(session)
            await service.set_tier_list(user, [TierAssignment(technique_id=t.id, tier="B") for t in techniques])
            await session.commit()
            await service.set_tier_list(user, [TierAssignment(technique_id=techniques[0].id, tier="S")])
            await session.commit()
            count = (
                await session.execute(select(func.count()).select_from(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id))
            ).scalar_one()
            first = await session.get(UserTechniqueProfile, (user.id, techniques[0].id))
            assert count == len(techniques)
            assert float(first.proficiency_score) == 9.0
        finally:
            await session.execute(delete(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
    await engine.dispose()
