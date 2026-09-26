from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import LedgerEntry, LedgerReason, PracticeSession, RepertoireEntry, SessionItem, User
from app.services.onboarding import BaseService
from app.services.streaks import local_day, zone_for

DEFAULT_WEEKS = 26
ROLLING_WEEKS = 4


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def rolling(values: list[Optional[float]], window: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for index in range(len(values)):
        recent = [value for value in values[max(0, index - window + 1) : index + 1] if value is not None]
        result.append(round(sum(recent) / len(recent), 1) if recent else None)
    return result


def weekly_series(
    practice: list[tuple[date, float, int]], learned: list[tuple[date, str, float]], today: date, weeks: int
) -> dict:
    first = week_start(today) - timedelta(weeks=weeks - 1)
    starts = [first + timedelta(weeks=offset) for offset in range(weeks)]
    weighted: dict[date, float] = {}
    minutes: dict[date, int] = {}
    for day, difficulty, spent in practice:
        start = week_start(day)
        if start < first:
            continue
        weighted[start] = weighted.get(start, 0.0) + difficulty * spent
        minutes[start] = minutes.get(start, 0) + spent
    averages = [round(weighted[start] / minutes[start], 1) if minutes.get(start) else None for start in starts]
    smooth = rolling(averages, ROLLING_WEEKS)
    learned_by_week: dict[date, list[dict]] = {}
    for day, title, difficulty in learned:
        start = week_start(day)
        if start >= first:
            learned_by_week.setdefault(start, []).append({"title": title, "difficulty": round(difficulty, 1), "day": day.isoformat()})
    points = [value for value in smooth if value is not None]
    return {
        "weeks": [
            {
                "start": start.isoformat(),
                "practised_avg": averages[index],
                "rolling_avg": smooth[index],
                "minutes": minutes.get(start, 0),
                "learned": learned_by_week.get(start, []),
            }
            for index, start in enumerate(starts)
        ],
        "rolling_weeks": ROLLING_WEEKS,
        "first_avg": points[0] if points else None,
        "latest_avg": points[-1] if points else None,
        "change": round(points[-1] - points[0], 1) if len(points) > 1 else None,
    }


class GrowthService(BaseService):
    async def difficulty_history(self, user: User, weeks: int = DEFAULT_WEEKS) -> dict:
        zone = zone_for(user)
        today = datetime.now(zone).date()
        since = datetime.now(timezone.utc) - timedelta(weeks=weeks + 1)
        stmt = (
            select(PracticeSession)
            .options(
                selectinload(PracticeSession.items)
                .selectinload(SessionItem.repertoire_entry)
                .selectinload(RepertoireEntry.piece)
            )
            .where(PracticeSession.user_id == user.id, PracticeSession.started_at >= since, PracticeSession.ended_at.is_not(None))
        )
        practice = []
        for session in (await self.session.execute(stmt)).scalars().all():
            day = local_day(session.started_at, zone)
            for item in session.items:
                piece = item.repertoire_entry.piece if item.repertoire_entry else None
                if piece is None or piece.difficulty_score is None or not item.minutes:
                    continue
                practice.append((day, float(piece.difficulty_score), int(item.minutes)))

        ledger = (
            await self.session.execute(
                select(LedgerEntry).where(
                    LedgerEntry.user_id == user.id,
                    LedgerEntry.reason == LedgerReason.PIECE_LEARNED,
                    LedgerEntry.created_at >= since,
                )
            )
        ).scalars().all()
        entry_ids = []
        for row in ledger:
            try:
                entry_ids.append(uuid.UUID(row.ref_id))
            except (TypeError, ValueError):
                continue
        entries = {}
        if entry_ids:
            rows = await self.session.execute(
                select(RepertoireEntry).options(selectinload(RepertoireEntry.piece)).where(RepertoireEntry.id.in_(entry_ids))
            )
            entries = {str(entry.id): entry for entry in rows.scalars().all()}
        learned = [
            (local_day(row.created_at, zone), entries[row.ref_id].piece.title, float(entries[row.ref_id].piece.difficulty_score))
            for row in ledger
            if row.ref_id in entries and entries[row.ref_id].piece.difficulty_score is not None
        ]
        return weekly_series(practice, learned, today, weeks)
