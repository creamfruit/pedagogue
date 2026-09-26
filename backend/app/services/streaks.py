from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import LedgerEntry, LedgerReason, PracticeSession, User
from app.services.onboarding import BaseService

STREAK_MIN_MINUTES = 5
STREAK_XP_PER_DAY = 10
STREAK_BONUS_CAP_DAYS = 7
HISTORY_DAYS = 400


@dataclass
class StreakStats:
    current: int
    longest: int
    today_done: bool
    minutes_today: int
    next_bonus_xp: int
    last_day: Optional[date]

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "longest": self.longest,
            "today_done": self.today_done,
            "minutes_today": self.minutes_today,
            "min_minutes": STREAK_MIN_MINUTES,
            "next_bonus_xp": self.next_bonus_xp,
            "last_day": self.last_day.isoformat() if self.last_day else None,
        }


def zone_for(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_day(moment: datetime, zone: ZoneInfo) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


def bonus_for(streak_length: int) -> int:
    return STREAK_XP_PER_DAY * min(max(streak_length, 1), STREAK_BONUS_CAP_DAYS)


def compute_streak(minutes_by_day: dict[date, int], today: date) -> StreakStats:
    days = sorted(day for day, minutes in minutes_by_day.items() if minutes >= STREAK_MIN_MINUTES)
    qualifying = set(days)
    longest = run = 0
    previous: Optional[date] = None
    for day in days:
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    anchor = today if today in qualifying else today - timedelta(days=1)
    current = 0
    while anchor in qualifying:
        current += 1
        anchor -= timedelta(days=1)
    today_done = today in qualifying
    next_length = current if today_done else current + 1
    return StreakStats(
        current=current,
        longest=longest,
        today_done=today_done,
        minutes_today=minutes_by_day.get(today, 0),
        next_bonus_xp=bonus_for(next_length),
        last_day=days[-1] if days else None,
    )


def minutes_per_day(sessions: Iterable[PracticeSession], zone: ZoneInfo) -> dict[date, int]:
    totals: dict[date, int] = {}
    for practice in sessions:
        if practice.ended_at is None:
            continue
        day = local_day(practice.started_at, zone)
        totals[day] = totals.get(day, 0) + practice.logged_minutes
    return totals


class StreakService(BaseService):
    async def minutes_by_day(self, user: User) -> dict[date, int]:
        since = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
        stmt = (
            select(PracticeSession)
            .options(selectinload(PracticeSession.items))
            .where(PracticeSession.user_id == user.id, PracticeSession.started_at >= since)
        )
        sessions = (await self.session.execute(stmt)).scalars().all()
        return minutes_per_day(sessions, zone_for(user))

    async def stats(self, user: User) -> StreakStats:
        today = datetime.now(zone_for(user)).date()
        return compute_streak(await self.minutes_by_day(user), today)

    async def award_bonus(self, user: User, practice: PracticeSession) -> Optional[LedgerEntry]:
        from app.services.economy import EconomyService

        zone = zone_for(user)
        day = local_day(practice.started_at, zone)
        minutes = await self.minutes_by_day(user)
        if minutes.get(day, 0) < STREAK_MIN_MINUTES:
            return None
        already = await self.session.execute(
            select(LedgerEntry.id).where(
                LedgerEntry.user_id == user.id,
                LedgerEntry.reason == LedgerReason.STREAK_BONUS,
                LedgerEntry.ref_type == "streak_day",
                LedgerEntry.ref_id == day.isoformat(),
            )
        )
        if already.first() is not None:
            return None
        stats = compute_streak(minutes, day)
        xp = bonus_for(stats.current)
        return await EconomyService(self.session).award(
            user,
            xp,
            0,
            LedgerReason.STREAK_BONUS,
            detail=f"day {stats.current} of your practice streak",
            ref_type="streak_day",
            ref_id=day.isoformat(),
        )
