import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.core.database import dispose_engine, session_scope
from app.core.security import hasher
from app.models.models import (
    Genre,
    Piece,
    RepertoireEntry,
    RepertoireStatus,
    SelfLevel,
    SelfRating,
    Technique,
    TextSubmission,
    User,
    UserGenrePreference,
    UserTechniqueProfile,
    Wallet,
)

PLAN = [
    (RepertoireStatus.PERFORMANCE_READY, 92, 96, "Memorised. Keep the left hand quieter in the middle section."),
    (RepertoireStatus.POLISHING, 76, 88, "Bars 9 to 16 still rush. Practise with the metronome at 70."),
    (RepertoireStatus.LEARNING, 58, 80, "Hands separately this week, slow and even."),
    (RepertoireStatus.LEARNING, 50, 72, None),
    (RepertoireStatus.WISHLIST, None, None, None),
    (RepertoireStatus.WISHLIST, None, None, None),
]


async def ensure_demo_account(email: str, password: str, name: str) -> tuple[User, bool]:
    async with session_scope() as session:
        user = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        created = user is None
        now = datetime.now(timezone.utc)
        if created:
            user = User(email=email.lower(), password_hash=hasher.hash(password), display_name=name)
            session.add(user)
        else:
            user.password_hash = hasher.hash(password)
        user.years_playing = user.years_playing or 6
        user.self_level = user.self_level or SelfLevel.INTERMEDIATE
        user.tier_quiz_completed_at = user.tier_quiz_completed_at or now
        user.tastes_completed_at = user.tastes_completed_at or now
        await session.flush()

        if await session.get(Wallet, user.id) is None:
            session.add(Wallet(user_id=user.id, xp=1450, gold=320, lifetime_xp=1450, lifetime_gold=320))

        rated = (
            await session.execute(select(func.count()).select_from(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id))
        ).scalar_one()
        if not rated:
            techniques = (await session.execute(select(Technique).order_by(Technique.id))).scalars().all()
            for index, technique in enumerate(techniques):
                score = Decimal(str(round(3.5 + (index * 1.7) % 6, 2)))
                rating = SelfRating.STRUGGLE if score < 5 else SelfRating.STRENGTH if score >= 8 else SelfRating.NEUTRAL
                session.add(UserTechniqueProfile(user_id=user.id, technique_id=technique.id, self_rating=rating, proficiency_score=score))
            genres = (await session.execute(select(Genre.id).order_by(Genre.id).limit(2))).scalars().all()
            session.add_all([UserGenrePreference(user_id=user.id, genre_id=genre_id) for genre_id in genres])

        owned = (
            await session.execute(select(func.count()).select_from(RepertoireEntry).where(RepertoireEntry.user_id == user.id))
        ).scalar_one()
        if not owned:
            pieces = (
                await session.execute(
                    select(Piece)
                    .where(Piece.is_user_created.is_(False), Piece.difficulty_score.is_not(None))
                    .order_by(Piece.difficulty_score)
                    .limit(len(PLAN))
                )
            ).scalars().all()
            if not pieces:
                raise SystemExit("the catalogue is empty; run python -m app.seed first")
            for rank, (piece, (status, current, target, note)) in enumerate(zip(pieces, PLAN), start=1):
                started = date.today() - timedelta(days=30 * (len(PLAN) - rank + 1))
                entry = RepertoireEntry(
                    user_id=user.id,
                    piece_id=piece.id,
                    status=status,
                    is_top_ten=status != RepertoireStatus.WISHLIST,
                    top_ten_rank=rank if status != RepertoireStatus.WISHLIST else None,
                    current_tempo_bpm=current,
                    target_tempo_bpm=target,
                    started_on=started if status != RepertoireStatus.WISHLIST else None,
                    last_practiced_at=now - timedelta(days=rank) if status != RepertoireStatus.WISHLIST else None,
                )
                session.add(entry)
                await session.flush()
                if note:
                    session.add(TextSubmission(repertoire_entry_id=entry.id, body=note))
        return user, created


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create or refresh a fully set-up demo account, for App Review and testing.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Demo Pianist")
    args = parser.parse_args()
    if len(args.password) < 8:
        raise SystemExit("use a password of at least 8 characters")
    try:
        user, created = await ensure_demo_account(args.email, args.password, args.name)
    finally:
        await dispose_engine()
    print(f"{'created' if created else 'refreshed'} demo account {user.email}")


if __name__ == "__main__":
    asyncio.run(main())
