from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Drill,
    LoadAlert,
    LoadSeverity,
    Passage,
    PassageTechnique,
    Piece,
    PieceLoadProfile,
    PracticeMode,
    PracticeSession,
    RepertoireEntry,
    SessionItem,
    Technique,
    User,
)
from app.services.economy import AchievementEngine, EconomyService
from app.services.onboarding import BaseService
from app.services.streaks import StreakService

BASELINE_FLOOR = Decimal("120.00")
CAUTION_RATIO = 1.20
REST_RATIO = 1.50
CHRONIC_WEEKS = 4
ACUTE_MULTIPLIER = Decimal("1.30")


def week_start(day: Optional[date] = None) -> date:
    day = day or date.today()
    return day - timedelta(days=day.weekday())


class PracticeSessionService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.economy = EconomyService(session)
        self.achievements = AchievementEngine(session)

    @staticmethod
    def item_options():
        return (
            selectinload(SessionItem.passage).selectinload(Passage.piece).selectinload(Piece.composer),
            selectinload(SessionItem.repertoire_entry)
            .selectinload(RepertoireEntry.piece)
            .selectinload(Piece.composer),
            selectinload(SessionItem.drill).selectinload(Drill.passage).selectinload(Passage.piece),
        )

    def session_options(self):
        return (selectinload(PracticeSession.items).options(*self.item_options()),)

    async def get(self, user: User, session_id: uuid.UUID) -> PracticeSession:
        stmt = (
            select(PracticeSession)
            .options(*self.session_options())
            .where(PracticeSession.id == session_id, PracticeSession.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        practice = result.scalar_one_or_none()
        if practice is None:
            raise LookupError("practice session not found")
        return practice

    async def start(
        self, user: User, mode: PracticeMode = PracticeMode.FREE, notes: Optional[str] = None
    ) -> PracticeSession:
        open_session = await self.open_session(user)
        if open_session is not None:
            raise ValueError("you already have an open practice session")
        practice = PracticeSession(user_id=user.id, mode=mode, notes=notes)
        self.session.add(practice)
        await self.session.flush()
        return await self.get(user, practice.id)

    async def open_session(self, user: User) -> Optional[PracticeSession]:
        stmt = (
            select(PracticeSession)
            .options(*self.session_options())
            .where(PracticeSession.user_id == user.id, PracticeSession.ended_at.is_(None))
            .order_by(PracticeSession.started_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, user: User, limit: int = 20, offset: int = 0) -> tuple[list[PracticeSession], int]:
        total = await self.session.execute(
            select(func.count()).select_from(PracticeSession).where(PracticeSession.user_id == user.id)
        )
        stmt = (
            select(PracticeSession)
            .options(*self.session_options())
            .where(PracticeSession.user_id == user.id)
            .order_by(PracticeSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all()), int(total.scalar_one())

    async def add_item(
        self,
        user: User,
        session_id: uuid.UUID,
        minutes: int,
        repertoire_entry_id: Optional[uuid.UUID] = None,
        passage_id: Optional[int] = None,
        drill_id: Optional[uuid.UUID] = None,
    ) -> SessionItem:
        practice = await self.get(user, session_id)
        if not practice.is_open:
            raise ValueError("that practice session is already closed")
        item = SessionItem(
            session_id=practice.id,
            repertoire_entry_id=repertoire_entry_id,
            passage_id=passage_id,
            drill_id=drill_id,
            minutes=minutes,
        )
        self.session.add(item)
        await self.session.flush()
        item.load_units = await self.compute_load(item)
        if repertoire_entry_id is not None:
            entry = await self.session.get(RepertoireEntry, repertoire_entry_id)
            if entry is not None and entry.user_id == user.id:
                entry.last_practiced_at = datetime.now(timezone.utc)
        await self.session.flush()
        return item

    async def compute_load(self, item: SessionItem) -> Decimal:
        minutes = item.minutes or 0
        factor = 1.0
        if item.passage_id is not None:
            factor = await self.passage_factor(item.passage_id)
        elif item.repertoire_entry_id is not None:
            factor = await self.entry_factor(item.repertoire_entry_id)
        return Decimal(str(round(minutes * factor, 2)))

    async def passage_factor(self, passage_id: int) -> float:
        stmt = (
            select(Technique.load_factor, PassageTechnique.weight)
            .join(PassageTechnique, PassageTechnique.technique_id == Technique.id)
            .where(PassageTechnique.passage_id == passage_id)
        )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return 1.0
        values = [float(load) * float(weight) for load, weight in rows]
        return round(max(sum(values) / len(values), 0.5), 3)

    async def entry_factor(self, entry_id: uuid.UUID) -> float:
        stmt = (
            select(Piece.difficulty_score, PieceLoadProfile.load_index)
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .outerjoin(PieceLoadProfile, PieceLoadProfile.piece_id == Piece.id)
            .where(RepertoireEntry.id == entry_id)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return 1.0
        difficulty, load_index = row
        if load_index is not None:
            return round(float(load_index), 3)
        if difficulty is not None:
            return round(0.8 + float(difficulty) / 120.0, 3)
        return 1.0

    async def close(
        self, user: User, session_id: uuid.UUID, perceived_tension: Optional[int] = None
    ) -> PracticeSession:
        practice = await self.get(user, session_id)
        if not practice.is_open:
            raise ValueError("that practice session is already closed")
        practice.close(perceived_tension)
        await self.session.flush()
        await self.economy.reward_practice(user, practice.logged_minutes, practice.id)
        await StreakService(self.session).award_bonus(user, practice)
        await self.achievements.evaluate(user)
        return await self.get(user, practice.id)


class LoadGuard(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.practice = PracticeSessionService(session)

    async def weekly_load(self, user: User, start: date) -> Decimal:
        end = start + timedelta(days=7)
        stmt = (
            select(func.coalesce(func.sum(SessionItem.load_units), 0))
            .join(PracticeSession, PracticeSession.id == SessionItem.session_id)
            .where(
                PracticeSession.user_id == user.id,
                PracticeSession.started_at >= datetime.combine(start, datetime.min.time(), timezone.utc),
                PracticeSession.started_at < datetime.combine(end, datetime.min.time(), timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one() or 0))

    async def chronic_baseline(self, user: User, current: date) -> Decimal:
        totals = []
        for offset in range(1, CHRONIC_WEEKS + 1):
            totals.append(await self.weekly_load(user, current - timedelta(weeks=offset)))
        active = [t for t in totals if t > 0]
        if not active:
            return BASELINE_FLOOR
        average = sum(active) / Decimal(len(active))
        return max(average * ACUTE_MULTIPLIER, BASELINE_FLOOR)

    @staticmethod
    def severity_for(ratio: float) -> LoadSeverity:
        if ratio >= REST_RATIO:
            return LoadSeverity.REST
        if ratio >= CAUTION_RATIO:
            return LoadSeverity.CAUTION
        return LoadSeverity.INFO

    @staticmethod
    def message_for(severity: LoadSeverity, total: Decimal, threshold: Decimal) -> str:
        if severity == LoadSeverity.REST:
            return (
                f"This week's load is {total:.0f} against a {threshold:.0f} ceiling. "
                "Take a full rest day before the next heavy session."
            )
        if severity == LoadSeverity.CAUTION:
            return (
                f"Load is climbing: {total:.0f} against {threshold:.0f}. "
                "Keep the next session light and technical rather than long."
            )
        if total > threshold:
            return (
                f"Load is {total:.0f}, a little over the {threshold:.0f} ceiling but not yet a concern. "
                "Keep an eye on how the hands feel."
            )
        return f"Load is {total:.0f}, comfortably inside the {threshold:.0f} ceiling."

    async def evaluate(self, user: User, day: Optional[date] = None) -> LoadAlert:
        start = week_start(day)
        total = await self.weekly_load(user, start)
        threshold = await self.chronic_baseline(user, start)
        ratio = float(total / threshold) if threshold else 0.0
        severity = self.severity_for(ratio)
        message = self.message_for(severity, total, threshold)

        existing = await self.session.execute(
            select(LoadAlert).where(LoadAlert.user_id == user.id, LoadAlert.week_start == start)
        )
        alert = existing.scalar_one_or_none()
        if alert is None:
            alert = LoadAlert(
                user_id=user.id,
                week_start=start,
                load_total=total,
                threshold=threshold,
                severity=severity,
                message=message,
            )
            self.session.add(alert)
        else:
            alert.load_total = total
            alert.threshold = threshold
            if alert.severity != severity:
                alert.acknowledged_at = None
            alert.severity = severity
            alert.message = message
        await self.session.flush()
        return alert

    async def list_alerts(self, user: User, limit: int = 12) -> list[LoadAlert]:
        stmt = (
            select(LoadAlert)
            .where(LoadAlert.user_id == user.id)
            .order_by(LoadAlert.week_start.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def acknowledge(self, user: User, alert_id: uuid.UUID) -> LoadAlert:
        alert = await self.session.get(LoadAlert, alert_id)
        if alert is None or alert.user_id != user.id:
            raise LookupError("alert not found")
        alert.acknowledge()
        await self.session.flush()
        return alert

    async def stretch_warnings(self, user: User) -> list[dict]:
        if user.hand_span_cm is None:
            return []
        stmt = (
            select(Piece, PieceLoadProfile)
            .join(PieceLoadProfile, PieceLoadProfile.piece_id == Piece.id)
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .where(RepertoireEntry.user_id == user.id)
        )
        rows = (await self.session.execute(stmt)).all()
        warnings = []
        for piece, profile in rows:
            if profile.exceeds_span(user.hand_span_cm):
                warnings.append(
                    {
                        "piece_id": piece.id,
                        "title": piece.title,
                        "required_cm": profile.max_stretch_cm(),
                        "your_span_cm": float(user.hand_span_cm),
                        "advice": "roll the widest chords rather than forcing the stretch",
                    }
                )
        return warnings

    async def summary(self, user: User, day: Optional[date] = None) -> dict:
        start = week_start(day)
        alert = await self.evaluate(user, day)
        history = []
        for offset in range(CHRONIC_WEEKS, -1, -1):
            wk = start - timedelta(weeks=offset)
            history.append({"week_start": wk.isoformat(), "load": float(await self.weekly_load(user, wk))})
        minutes = await self.session.execute(
            select(func.coalesce(func.sum(SessionItem.minutes), 0))
            .join(PracticeSession, PracticeSession.id == SessionItem.session_id)
            .where(
                PracticeSession.user_id == user.id,
                PracticeSession.started_at
                >= datetime.combine(start, datetime.min.time(), timezone.utc),
            )
        )
        return {
            "week_start": start.isoformat(),
            "load_total": float(alert.load_total),
            "threshold": float(alert.threshold),
            "ratio": alert.overshoot_ratio,
            "severity": alert.severity.value,
            "message": alert.message,
            "minutes_this_week": int(minutes.scalar_one() or 0),
            "history": history,
            "stretch_warnings": await self.stretch_warnings(user),
        }


class LiveListeningCoach:
    TEMPO_DRIFT = 0.06
    ACCURACY_FLOOR = 0.85
    TENSION_CEILING = 0.75

    def __init__(self, target_bpm: Optional[int] = None) -> None:
        self.target_bpm = target_bpm
        self.frames = 0
        self.bpm_samples: list[float] = []
        self.accuracy_samples: list[float] = []
        self.tension_samples: list[float] = []
        self.cues: list[str] = []

    def ingest(self, frame: dict) -> dict:
        self.frames += 1
        bpm = frame.get("bpm")
        accuracy = frame.get("accuracy")
        tension = frame.get("tension")
        cues: list[str] = []

        if bpm is not None:
            self.bpm_samples.append(float(bpm))
            if self.target_bpm:
                drift = (float(bpm) - self.target_bpm) / self.target_bpm
                if drift > self.TEMPO_DRIFT:
                    cues.append(f"rushing by {drift * 100:.0f} percent, settle back toward {self.target_bpm}")
                elif drift < -self.TEMPO_DRIFT:
                    cues.append(f"dragging by {abs(drift) * 100:.0f} percent, lift the pulse")
        if accuracy is not None:
            self.accuracy_samples.append(float(accuracy))
            if float(accuracy) < self.ACCURACY_FLOOR:
                cues.append("accuracy is slipping, drop the tempo a notch and rebuild")
        if tension is not None:
            self.tension_samples.append(float(tension))
            if float(tension) > self.TENSION_CEILING:
                cues.append("forearm tension is high, release the wrist between phrases")

        self.cues.extend(cues)
        return {
            "frame": self.frames,
            "cues": cues,
            "rolling": self.rolling(),
        }

    def rolling(self) -> dict:
        def mean(values: list[float]) -> Optional[float]:
            return round(sum(values) / len(values), 3) if values else None

        return {
            "bpm": mean(self.bpm_samples[-20:]),
            "accuracy": mean(self.accuracy_samples[-20:]),
            "tension": mean(self.tension_samples[-20:]),
        }

    def report(self) -> dict:
        rolling = self.rolling()
        tension = rolling.get("tension")
        return {
            "frames": self.frames,
            "average": {
                "bpm": round(sum(self.bpm_samples) / len(self.bpm_samples), 1) if self.bpm_samples else None,
                "accuracy": round(sum(self.accuracy_samples) / len(self.accuracy_samples), 3)
                if self.accuracy_samples
                else None,
                "tension": round(sum(self.tension_samples) / len(self.tension_samples), 3)
                if self.tension_samples
                else None,
            },
            "cue_count": len(self.cues),
            "distinct_cues": sorted(set(self.cues)),
            "perceived_tension": self.tension_scale(tension),
        }

    @staticmethod
    def tension_scale(value: Optional[float]) -> Optional[int]:
        if value is None:
            return None
        return max(1, min(5, int(round(value * 5))))
