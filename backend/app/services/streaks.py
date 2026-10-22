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
FREEZE_START = 1
FREEZE_CAP = 2
FREEZE_EVERY = 7
FROZEN_SHOWN_DAYS = 14


@dataclass
class StreakStats:
    current: int
    longest: int
    today_done: bool
    minutes_today: int
    next_bonus_xp: int
    last_day: Optional[date]
    freezes: int = 0
    frozen_days: tuple = ()
    state: str = "new"
    next_freeze_in: int = FREEZE_EVERY

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "longest": self.longest,
            "today_done": self.today_done,
            "minutes_today": self.minutes_today,
            "min_minutes": STREAK_MIN_MINUTES,
            "next_bonus_xp": self.next_bonus_xp,
            "last_day": self.last_day.isoformat() if self.last_day else None,
            "freezes": self.freezes,
            "freeze_cap": FREEZE_CAP,
            "frozen_days": [day.isoformat() for day in self.frozen_days],
            "state": self.state,
            "next_freeze_in": self.next_freeze_in,
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
    qualifying = {day for day, minutes in minutes_by_day.items() if minutes >= STREAK_MIN_MINUTES and day <= today}
    ordered = sorted(qualifying)
    streak = longest = 0
    freezes = FREEZE_START
    frozen: list[date] = []
    if ordered:
        day = ordered[0]
        while day <= today:
            if day in qualifying:
                streak += 1
                longest = max(longest, streak)
                if streak % FREEZE_EVERY == 0:
                    freezes = min(freezes + 1, FREEZE_CAP)
            elif day < today and streak > 0:
                if freezes > 0:
                    freezes -= 1
                    frozen.append(day)
                else:
                    streak = 0
                    freezes = FREEZE_START
            day += timedelta(days=1)
    today_done = today in qualifying
    yesterday = today - timedelta(days=1)
    if today_done:
        state = "lit"
    elif frozen and frozen[-1] == yesterday:
        state = "covered"
    elif streak == 0 and ordered:
        state = "fresh"
    elif streak == 0:
        state = "new"
    else:
        state = "waiting"
    next_length = streak if today_done else streak + 1
    shown_from = today - timedelta(days=FROZEN_SHOWN_DAYS)
    return StreakStats(
        current=streak,
        longest=longest,
        today_done=today_done,
        minutes_today=minutes_by_day.get(today, 0),
        next_bonus_xp=bonus_for(next_length),
        last_day=ordered[-1] if ordered else None,
        freezes=freezes,
        frozen_days=tuple(day for day in frozen if day >= shown_from),
        state=state,
        next_freeze_in=FREEZE_EVERY - (streak % FREEZE_EVERY) if streak % FREEZE_EVERY else FREEZE_EVERY,
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

    async def record_week(self, user: User, practice: PracticeSession) -> None:
        from app.services.leaderboard import LeaderboardService, practice_week_board

        zone = zone_for(user)
        day = local_day(practice.started_at, zone)
        start = day - timedelta(days=day.weekday())
        minutes = await self.minutes_by_day(user)
        total = sum(value for when, value in minutes.items() if start <= when < start + timedelta(days=7))
        stats = compute_streak(minutes, datetime.now(zone).date())
        await LeaderboardService(self.session).submit(
            practice_week_board(day), user, total, {"minutes": total, "streak": stats.current}, keep="replace"
        )

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


def nudge_message(days: Optional[int], title: Optional[str]) -> str:
    target = f" {title} is waiting." if title else ""
    if days is None:
        return f"You haven't logged a practice session yet.{target}"
    return f"It's been {days} days since you last practised.{target} Even five minutes keeps your sky from drifting."


class NudgeService(BaseService):
    async def nudge(self, user: User) -> Optional[dict]:
        from app.models.models import RepertoireEntry, RepertoireStatus

        if not user.nudge_after_days:
            return None
        zone = zone_for(user)
        today = datetime.now(zone).date()
        last = (
            await self.session.execute(
                select(PracticeSession.started_at)
                .where(PracticeSession.user_id == user.id, PracticeSession.ended_at.is_not(None))
                .order_by(PracticeSession.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        days = (today - local_day(last, zone)).days if last else None
        if days is not None and days < user.nudge_after_days:
            return None
        entries = (
            await self.session.execute(
                select(RepertoireEntry)
                .options(selectinload(RepertoireEntry.piece))
                .where(
                    RepertoireEntry.user_id == user.id,
                    RepertoireEntry.status.in_([RepertoireStatus.LEARNING, RepertoireStatus.POLISHING]),
                )
            )
        ).scalars().all()
        if not entries and days is None:
            return None
        epoch = datetime.min.replace(tzinfo=timezone.utc)
        pick = min(entries, key=lambda entry: entry.last_practiced_at or epoch, default=None)
        return {
            "days_since_practice": days,
            "after_days": user.nudge_after_days,
            "message": nudge_message(days, pick.piece.title if pick else None),
            "entry_id": pick.id if pick else None,
            "piece_title": pick.piece.title if pick else None,
        }
