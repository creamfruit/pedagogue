from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import BinaryIO, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectin_polymorphic, selectinload

from app.core.storage import (
    AUDIO_TYPES,
    PDF_TYPES,
    Storage,
    ensure_media_type,
    storage as default_storage,
)
from app.models.models import (
    Analysis,
    GRADED_DIFFICULTY_THRESHOLD,
    GRADED_PASS_SCORE,
    AudioSubmission,
    Composer,
    PassageAssessment,
    PdfSubmission,
    ReadinessScore,
    Piece,
    ProcessingStatus,
    RepertoireEntry,
    RepertoireStatus,
    Submission,
    TextSubmission,
    User,
)
from app.schemas.schemas import (
    PageMeta,
    RepertoireEntryCreate,
    RepertoireEntryUpdate,
    RepertoireStats,
)
from app.services.economy import AchievementEngine, EconomyService, LEARNED_STATUSES
from app.services.onboarding import BaseService, CatalogService


class RepertoireService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.catalog = CatalogService(session)
        self.economy = EconomyService(session)
        self.achievements = AchievementEngine(session)

    @staticmethod
    def requires_grading(piece: Piece) -> bool:
        return (
            piece.difficulty_score is not None
            and piece.difficulty_score >= GRADED_DIFFICULTY_THRESHOLD
        )

    async def best_grade(self, entry_id: uuid.UUID) -> Optional[Decimal]:
        result = await self.session.execute(
            select(func.max(ReadinessScore.overall_score)).where(
                ReadinessScore.repertoire_entry_id == entry_id
            )
        )
        return result.scalar_one_or_none()

    async def gate(self, entry: RepertoireEntry) -> dict:
        required = self.requires_grading(entry.piece)
        best = await self.best_grade(entry.id) if required else None
        return {
            "requires_grading": required,
            "threshold": float(GRADED_DIFFICULTY_THRESHOLD),
            "pass_score": float(GRADED_PASS_SCORE),
            "best_score": float(best) if best is not None else None,
            "unlocked": not required or (best is not None and best >= GRADED_PASS_SCORE),
        }

    @staticmethod
    def entry_options():
        return (
            selectinload(RepertoireEntry.piece).selectinload(Piece.composer),
            selectinload(RepertoireEntry.piece).selectinload(Piece.genre),
        )

    async def get(self, user: User, entry_id: uuid.UUID) -> RepertoireEntry:
        stmt = (
            select(RepertoireEntry)
            .options(*self.entry_options())
            .where(RepertoireEntry.id == entry_id, RepertoireEntry.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            raise LookupError("repertoire entry not found")
        return entry

    async def list(
        self,
        user: User,
        status: Optional[RepertoireStatus] = None,
        query: Optional[str] = None,
        top_ten_only: bool = False,
        genre_id: Optional[int] = None,
        composer_id: Optional[int] = None,
        min_difficulty: Optional[Decimal] = None,
        max_difficulty: Optional[Decimal] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[RepertoireEntry], PageMeta]:
        conditions = [RepertoireEntry.user_id == user.id]
        if status is not None:
            conditions.append(RepertoireEntry.status == status)
        if top_ten_only:
            conditions.append(RepertoireEntry.is_top_ten.is_(True))
        if genre_id is not None:
            conditions.append(Piece.genre_id == genre_id)
        if composer_id is not None:
            conditions.append(Piece.composer_id == composer_id)
        if min_difficulty is not None:
            conditions.append(Piece.difficulty_score >= min_difficulty)
        if max_difficulty is not None:
            conditions.append(Piece.difficulty_score <= max_difficulty)

        base = select(RepertoireEntry).join(Piece, Piece.id == RepertoireEntry.piece_id)
        if query:
            pattern = f"%{query}%"
            base = base.outerjoin(Composer, Composer.id == Piece.composer_id)
            conditions.append(or_(Piece.title.ilike(pattern), Composer.name.ilike(pattern)))

        total_stmt = select(func.count()).select_from(base.where(*conditions).subquery())
        total = int((await self.session.execute(total_stmt)).scalar_one())

        stmt = (
            base.where(*conditions)
            .options(*self.entry_options())
            .order_by(RepertoireEntry.is_top_ten.desc(), Piece.title)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().unique().all())
        meta = PageMeta(total=total, limit=limit, offset=offset, has_more=offset + len(items) < total)
        return items, meta

    async def create(self, user: User, payload: RepertoireEntryCreate) -> RepertoireEntry:
        piece = await self.catalog.resolve_piece(user, payload.piece_id, payload.piece)
        existing = await self.session.execute(
            select(RepertoireEntry).where(
                RepertoireEntry.user_id == user.id, RepertoireEntry.piece_id == piece.id
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("that piece is already in your repertoire")
        entry = RepertoireEntry(
            user_id=user.id,
            piece_id=piece.id,
            status=payload.status,
            is_top_ten=payload.is_top_ten,
            top_ten_rank=payload.top_ten_rank if payload.is_top_ten else None,
            current_tempo_bpm=payload.current_tempo_bpm,
            target_tempo_bpm=payload.target_tempo_bpm,
            started_on=payload.started_on,
            notes=payload.notes,
        )
        self.session.add(entry)
        await self.session.flush()
        hydrated = await self.get(user, entry.id)
        if hydrated.status in LEARNED_STATUSES:
            await self.economy.reward_learning(user, hydrated)
        await self.achievements.evaluate(user)
        return hydrated

    async def update(
        self, user: User, entry_id: uuid.UUID, payload: RepertoireEntryUpdate
    ) -> RepertoireEntry:
        entry = await self.get(user, entry_id)
        changes = payload.model_dump(exclude_unset=True)
        previous = entry.status
        target = changes.get("status")

        if (
            target == RepertoireStatus.PERFORMANCE_READY
            and previous != RepertoireStatus.PERFORMANCE_READY
            and self.requires_grading(entry.piece)
        ):
            best = await self.best_grade(entry_id)
            if best is None or best < GRADED_PASS_SCORE:
                raise PermissionError(
                    f"{entry.piece.title} sits at difficulty {entry.piece.difficulty_score}. "
                    f"Record a full run-through and score {GRADED_PASS_SCORE:.0f} or higher to mark it learnt."
                )

        for field, value in changes.items():
            setattr(entry, field, value)
        if entry.is_top_ten is False:
            entry.top_ten_rank = None
        if entry.status == RepertoireStatus.RETIRED and entry.completed_on is None:
            from datetime import date

            entry.completed_on = date.today()
        await self.session.flush()
        if entry.status in LEARNED_STATUSES and previous not in LEARNED_STATUSES:
            await self.economy.reward_learning(user, entry)
            await self.achievements.evaluate(user)
        return await self.get(user, entry.id)

    async def delete(self, user: User, entry_id: uuid.UUID) -> None:
        entry = await self.get(user, entry_id)
        await self.session.delete(entry)
        await self.session.flush()

    async def maintenance_run(self, user: User, entry_id: uuid.UUID) -> RepertoireEntry:
        entry = await self.get(user, entry_id)
        entry.last_practiced_at = datetime.now(timezone.utc)
        await self.session.flush()
        return entry

    async def stats(self, user: User) -> RepertoireStats:
        rows = await self.session.execute(
            select(RepertoireEntry.status, func.count())
            .where(RepertoireEntry.user_id == user.id)
            .group_by(RepertoireEntry.status)
        )
        by_status = {status.value: int(count) for status, count in rows.all()}
        total = sum(by_status.values())
        active = by_status.get(RepertoireStatus.LEARNING.value, 0) + by_status.get(
            RepertoireStatus.POLISHING.value, 0
        )
        average = await self.session.execute(
            select(func.avg(Piece.difficulty_score))
            .join(RepertoireEntry, RepertoireEntry.piece_id == Piece.id)
            .where(RepertoireEntry.user_id == user.id)
        )
        average_difficulty = average.scalar_one_or_none()
        submissions = await self.session.execute(
            select(func.count())
            .select_from(Submission)
            .join(RepertoireEntry, RepertoireEntry.id == Submission.repertoire_entry_id)
            .where(RepertoireEntry.user_id == user.id)
        )
        pending = await self.session.execute(
            select(func.count())
            .select_from(Submission)
            .join(RepertoireEntry, RepertoireEntry.id == Submission.repertoire_entry_id)
            .where(
                RepertoireEntry.user_id == user.id,
                Submission.processing_status.in_([ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING]),
            )
        )
        return RepertoireStats(
            total=total,
            by_status=by_status,
            active=active,
            submissions=int(submissions.scalar_one()),
            pending_submissions=int(pending.scalar_one()),
            average_difficulty=round(float(average_difficulty), 2) if average_difficulty else None,
        )


class SubmissionService(BaseService):
    SUBTYPES = [TextSubmission, PdfSubmission, AudioSubmission]

    def __init__(self, session: AsyncSession, storage: Optional[Storage] = None) -> None:
        super().__init__(session)
        self.storage = storage or default_storage
        self.repertoire = RepertoireService(session)

    @classmethod
    def polymorphic(cls):
        return selectin_polymorphic(Submission, cls.SUBTYPES)

    async def get(self, user: User, submission_id: uuid.UUID) -> Submission:
        stmt = (
            select(Submission)
            .options(
                self.polymorphic(),
                selectinload(Submission.analyses),
                selectinload(Submission.repertoire_entry),
            )
            .join(RepertoireEntry, RepertoireEntry.id == Submission.repertoire_entry_id)
            .where(Submission.id == submission_id, RepertoireEntry.user_id == user.id)
        )
        result = await self.session.execute(stmt)
        submission = result.scalar_one_or_none()
        if submission is None:
            raise LookupError("submission not found")
        return submission

    async def list_for_entry(self, user: User, entry_id: uuid.UUID) -> list[Submission]:
        await self.repertoire.get(user, entry_id)
        stmt = (
            select(Submission)
            .options(self.polymorphic(), selectinload(Submission.analyses))
            .where(Submission.repertoire_entry_id == entry_id)
            .order_by(Submission.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def analyses(self, user: User, submission_id: uuid.UUID) -> list[Analysis]:
        await self.get(user, submission_id)
        stmt = (
            select(Analysis)
            .options(selectinload(Analysis.passage_assessments).selectinload(PassageAssessment.passage))
            .where(Analysis.submission_id == submission_id)
            .order_by(Analysis.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def add_text(self, user: User, entry_id: uuid.UUID, body: str) -> TextSubmission:
        await self.repertoire.get(user, entry_id)
        submission = TextSubmission(repertoire_entry_id=entry_id, body=body)
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def add_pdf(
        self,
        user: User,
        entry_id: uuid.UUID,
        stream: BinaryIO,
        filename: str,
        content_type: Optional[str],
    ) -> PdfSubmission:
        await self.repertoire.get(user, entry_id)
        ensure_media_type(content_type, PDF_TYPES, "a PDF")
        key = self.storage.build_key(user.id, "scores", filename or "score.pdf")
        self.storage.save(stream, key)
        submission = PdfSubmission(repertoire_entry_id=entry_id, storage_key=key)
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def add_audio(
        self,
        user: User,
        entry_id: uuid.UUID,
        stream: BinaryIO,
        filename: str,
        content_type: Optional[str],
        duration_sec: Optional[int] = None,
        is_full_run_through: bool = False,
        is_verification: bool = False,
        tempo_curve: Optional[dict] = None,
    ) -> AudioSubmission:
        entry = await self.repertoire.get(user, entry_id)
        ensure_media_type(content_type, AUDIO_TYPES, "an audio recording")
        key = self.storage.build_key(user.id, "recordings", filename or "take.wav")
        self.storage.save(stream, key)
        submission = AudioSubmission(
            repertoire_entry_id=entry_id,
            storage_key=key,
            duration_sec=duration_sec,
            is_full_run_through=is_full_run_through,
            is_verification=is_verification,
            tempo_curve={"samples": tempo_curve} if isinstance(tempo_curve, list) else tempo_curve,
        )
        self.session.add(submission)
        entry.last_practiced_at = datetime.now(timezone.utc)
        if is_verification:
            entry.is_verified = True
        await self.session.flush()
        return submission

    async def requeue(self, user: User, submission_id: uuid.UUID) -> Submission:
        submission = await self.get(user, submission_id)
        if submission.processing_status == ProcessingStatus.PROCESSING:
            raise ValueError("that submission is already being processed")
        submission.mark(ProcessingStatus.QUEUED)
        await self.session.flush()
        return submission

    async def delete(self, user: User, submission_id: uuid.UUID) -> None:
        submission = await self.get(user, submission_id)
        key = getattr(submission, "storage_key", None)
        await self.session.delete(submission)
        await self.session.flush()
        if key:
            try:
                self.storage.delete(key)
            except Exception:
                pass
