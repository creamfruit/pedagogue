from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Analysis,
    GRADED_PASS_SCORE,
    LedgerEntry,
    LedgerReason,
    AudioSubmission,
    PassageAssessment,
    Performance,
    PerformanceProgram,
    Piece,
    ReadinessScore,
    RepertoireEntry,
    RepertoireStatus,
    Submission,
    User,
)
from app.services.economy import AchievementEngine, EconomyService
from app.services.onboarding import BaseService

RESTART_PENALTY = 6.0
SLIP_PENALTY = 12.0
ACCURACY_WEIGHT = 55.0
STABILITY_WEIGHT = 30.0
BASE_SCORE = 15.0


class ReadinessScorer(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.economy = EconomyService(session)
        self.achievements = AchievementEngine(session)

    async def latest_run_through(self, entry_id: uuid.UUID) -> Optional[AudioSubmission]:
        stmt = (
            select(AudioSubmission)
            .where(
                AudioSubmission.repertoire_entry_id == entry_id,
                AudioSubmission.is_full_run_through.is_(True),
            )
            .order_by(AudioSubmission.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assessments_for(self, submission_id: uuid.UUID) -> list[PassageAssessment]:
        stmt = (
            select(PassageAssessment)
            .join(Analysis, Analysis.id == PassageAssessment.analysis_id)
            .where(Analysis.submission_id == submission_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def compute(assessments: Sequence[PassageAssessment]) -> dict:
        if not assessments:
            return {
                "overall_score": None,
                "tempo_stability": None,
                "restart_count": 0,
                "memory_slip_count": 0,
            }
        accuracies = [float(a.accuracy_score) for a in assessments if a.accuracy_score is not None]
        stabilities = [float(a.tempo_stability) for a in assessments if a.tempo_stability is not None]
        restarts = sum(a.restart_count for a in assessments)
        slips = sum(1 for a in assessments if a.memory_slip)

        accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0
        stability = sum(stabilities) / len(stabilities) if stabilities else 0.0
        raw = BASE_SCORE + ACCURACY_WEIGHT * accuracy + STABILITY_WEIGHT * stability
        raw -= RESTART_PENALTY * restarts + SLIP_PENALTY * slips
        return {
            "overall_score": round(max(0.0, min(100.0, raw)), 1),
            "tempo_stability": round(stability, 3) if stabilities else None,
            "restart_count": restarts,
            "memory_slip_count": slips,
        }

    async def score_entry(self, user: User, entry_id: uuid.UUID) -> ReadinessScore:
        stmt = (
            select(RepertoireEntry)
            .options(selectinload(RepertoireEntry.piece))
            .where(RepertoireEntry.id == entry_id)
        )
        entry = (await self.session.execute(stmt)).scalar_one_or_none()
        if entry is None or entry.user_id != user.id:
            raise LookupError("repertoire entry not found")
        submission = await self.latest_run_through(entry_id)
        if submission is None:
            raise ValueError("upload a full run-through recording before scoring readiness")
        assessments = await self.assessments_for(submission.id)
        metrics = self.compute(assessments)
        score = ReadinessScore(
            repertoire_entry_id=entry_id,
            audio_submission_id=submission.id,
            overall_score=Decimal(str(metrics["overall_score"]))
            if metrics["overall_score"] is not None
            else None,
            tempo_stability=Decimal(str(metrics["tempo_stability"]))
            if metrics["tempo_stability"] is not None
            else None,
            restart_count=metrics["restart_count"],
            memory_slip_count=metrics["memory_slip_count"],
        )
        self.session.add(score)
        await self.session.flush()

        score.promoted = False
        score.reward_xp = 0
        score.reward_gold = 0
        if score.overall_score is not None and score.overall_score >= GRADED_PASS_SCORE:
            already = await self.session.execute(
                select(LedgerEntry).where(
                    LedgerEntry.user_id == user.id,
                    LedgerEntry.reason == LedgerReason.GRADED_PERFORMANCE,
                    LedgerEntry.ref_id == str(score.id),
                )
            )
            if already.scalar_one_or_none() is None:
                ledger = await self.economy.reward_graded(user, entry, score)
                score.reward_xp = ledger.delta_xp
                score.reward_gold = ledger.delta_gold
            if entry.status != RepertoireStatus.PERFORMANCE_READY:
                entry.status = RepertoireStatus.PERFORMANCE_READY
                score.promoted = True
                await self.session.flush()
            await self.achievements.evaluate(user)
        return score

    async def history(self, user: User, entry_id: uuid.UUID, limit: int = 20) -> list[ReadinessScore]:
        stmt = (
            select(ReadinessScore)
            .join(RepertoireEntry, RepertoireEntry.id == ReadinessScore.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id, ReadinessScore.repertoire_entry_id == entry_id)
            .order_by(ReadinessScore.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_by_entry(self, user: User) -> dict[uuid.UUID, ReadinessScore]:
        stmt = (
            select(ReadinessScore)
            .join(RepertoireEntry, RepertoireEntry.id == ReadinessScore.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id)
            .order_by(ReadinessScore.created_at.desc())
        )
        result = await self.session.execute(stmt)
        latest: dict[uuid.UUID, ReadinessScore] = {}
        for score in result.scalars().all():
            latest.setdefault(score.repertoire_entry_id, score)
        return latest


class PerformanceService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.scorer = ReadinessScorer(session)

    @staticmethod
    def performance_options():
        return (
            selectinload(Performance.program)
            .selectinload(PerformanceProgram.repertoire_entry)
            .selectinload(RepertoireEntry.piece)
            .selectinload(Piece.composer),
            selectinload(Performance.program)
            .selectinload(PerformanceProgram.repertoire_entry)
            .selectinload(RepertoireEntry.piece)
            .selectinload(Piece.genre),
        )

    async def get(self, user: User, performance_id: uuid.UUID) -> Performance:
        stmt = (
            select(Performance)
            .options(*self.performance_options())
            .where(Performance.id == performance_id, Performance.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        performance = result.scalar_one_or_none()
        if performance is None:
            raise LookupError("performance not found")
        return performance

    async def list(self, user: User, upcoming_only: bool = False) -> list[Performance]:
        stmt = (
            select(Performance)
            .options(*self.performance_options())
            .where(Performance.user_id == user.id)
            .order_by(Performance.event_date.asc().nulls_last())
        )
        if upcoming_only:
            stmt = stmt.where(Performance.event_date >= date.today())
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def create(
        self, user: User, title: str, event_date: Optional[date], venue: Optional[str]
    ) -> Performance:
        performance = Performance(user_id=user.id, title=title, event_date=event_date, venue=venue)
        self.session.add(performance)
        await self.session.flush()
        return await self.get(user, performance.id)

    async def update(
        self, user: User, performance_id: uuid.UUID, changes: dict
    ) -> Performance:
        performance = await self.get(user, performance_id)
        for field, value in changes.items():
            setattr(performance, field, value)
        await self.session.flush()
        return await self.get(user, performance.id)

    async def delete(self, user: User, performance_id: uuid.UUID) -> None:
        performance = await self.get(user, performance_id)
        await self.session.delete(performance)
        await self.session.flush()

    async def set_program(
        self, user: User, performance_id: uuid.UUID, entry_ids: Sequence[uuid.UUID]
    ) -> Performance:
        performance = await self.get(user, performance_id)
        owned = await self.session.execute(
            select(RepertoireEntry.id).where(
                RepertoireEntry.user_id == user.id, RepertoireEntry.id.in_(list(entry_ids))
            )
        )
        valid = set(owned.scalars().all())
        missing = [str(eid) for eid in entry_ids if eid not in valid]
        if missing:
            raise LookupError(f"repertoire entries not found: {', '.join(missing)}")

        for item in list(performance.program):
            await self.session.delete(item)
        await self.session.flush()

        for order, entry_id in enumerate(entry_ids, start=1):
            self.session.add(
                PerformanceProgram(
                    performance_id=performance.id,
                    repertoire_entry_id=entry_id,
                    program_order=order,
                )
            )
        await self.session.flush()
        self.session.expire(performance, ["program"])
        return await self.get(user, performance.id)

    async def readiness_report(self, user: User, performance_id: uuid.UUID) -> dict:
        performance = await self.get(user, performance_id)
        latest = await self.scorer.latest_by_entry(user)
        items = []
        scores: list[float] = []
        for entry in performance.program:
            repertoire = entry.repertoire_entry
            score = latest.get(repertoire.id)
            value = float(score.overall_score) if score and score.overall_score is not None else None
            if value is not None:
                scores.append(value)
            items.append(
                {
                    "program_order": entry.program_order,
                    "repertoire_entry_id": str(repertoire.id),
                    "title": repertoire.piece.display_title,
                    "status": repertoire.status.value,
                    "overall_score": value,
                    "verdict": score.verdict if score else "unscored",
                    "restart_count": score.restart_count if score else None,
                    "memory_slip_count": score.memory_slip_count if score else None,
                    "duration_sec": repertoire.piece.duration_sec,
                }
            )
        unscored = [item for item in items if item["overall_score"] is None]
        weakest = min((i for i in items if i["overall_score"] is not None), key=lambda i: i["overall_score"], default=None)
        return {
            "performance_id": str(performance.id),
            "title": performance.title,
            "event_date": performance.event_date.isoformat() if performance.event_date else None,
            "days_until": performance.days_until,
            "total_duration_sec": performance.total_duration_sec,
            "program": items,
            "average_score": round(sum(scores) / len(scores), 1) if scores else None,
            "unscored_count": len(unscored),
            "weakest_link": weakest,
            "verdict": self.overall_verdict(items),
        }

    @staticmethod
    def overall_verdict(items: Sequence[dict]) -> str:
        if not items:
            return "no program set"
        scored = [i for i in items if i["overall_score"] is not None]
        if not scored:
            return "record run-throughs to get a readiness picture"
        if len(scored) < len(items):
            return f"{len(items) - len(scored)} piece(s) still unscored"
        worst = min(i["overall_score"] for i in scored)
        if worst >= 85:
            return "whole program is stage ready"
        if worst >= 70:
            return "nearly there, one or two pieces need another pass"
        return "not ready, the weakest piece needs real work"
