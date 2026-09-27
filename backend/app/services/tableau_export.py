from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectin_polymorphic, selectinload

from app.models.models import (
    AudioSubmission,
    Composer,
    LedgerEntry,
    Piece,
    PracticeSession,
    ReadinessScore,
    RepertoireEntry,
    Submission,
    Technique,
    User,
    UserTechniqueProfile,
)
from app.services.coach_feedback import tier_for
from app.services.onboarding import BaseService

SCHEMA = "Extract"
NO_ENTRY = uuid.UUID(int=0)


class ExportUnavailable(RuntimeError):
    pass


@dataclass
class Table:
    name: str
    columns: list[tuple[str, str]]
    rows: list[list[Any]] = field(default_factory=list)


def plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    if value is not None and not isinstance(value, (str, int, float, bool, date, datetime)):
        return str(value)
    return value


def title_of(entry: Optional[RepertoireEntry]) -> Optional[str]:
    return entry.piece.title if entry and entry.piece else None


class TableauExportService(BaseService):
    async def entries(self, user: User) -> list[RepertoireEntry]:
        stmt = (
            select(RepertoireEntry)
            .options(
                selectinload(RepertoireEntry.piece).selectinload(Piece.composer).selectinload(Composer.era),
                selectinload(RepertoireEntry.piece).selectinload(Piece.genre),
            )
            .where(RepertoireEntry.user_id == user.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def collect(self, user: User) -> list[Table]:
        entries = await self.entries(user)
        by_id = {entry.id: entry for entry in entries}

        repertoire = Table(
            "repertoire",
            [
                ("entry_id", "text"), ("piece_id", "int"), ("title", "text"), ("composer", "text"), ("era", "text"),
                ("genre", "text"), ("status", "text"), ("difficulty", "double"), ("is_top_ten", "bool"),
                ("started_on", "date"), ("completed_on", "date"), ("last_practiced_at", "timestamp"),
                ("current_tempo_bpm", "int"), ("target_tempo_bpm", "int"), ("is_verified", "bool"),
                ("is_custom", "bool"), ("caught_in_meteor_shower", "bool"),
            ],
        )
        for entry in entries:
            piece = entry.piece
            repertoire.rows.append([
                str(entry.id), piece.id, piece.title, piece.composer.name if piece.composer else None,
                piece.composer.era.name if piece.composer and piece.composer.era else None,
                piece.genre.name if piece.genre else None, entry.status.value, plain(piece.difficulty_score),
                entry.is_top_ten, entry.started_on, entry.completed_on, entry.last_practiced_at,
                entry.current_tempo_bpm, entry.target_tempo_bpm, entry.is_verified, piece.is_user_created,
                entry.meteor_shower_id is not None,
            ])

        sessions = (
            await self.session.execute(
                select(PracticeSession)
                .options(selectinload(PracticeSession.items))
                .where(PracticeSession.user_id == user.id)
                .order_by(PracticeSession.started_at)
            )
        ).scalars().all()
        practice = Table(
            "practice_sessions",
            [
                ("session_id", "text"), ("started_at", "timestamp"), ("ended_at", "timestamp"), ("mode", "text"),
                ("duration_minutes", "int"), ("logged_minutes", "int"), ("pieces", "int"),
                ("perceived_tension", "int"),
            ],
        )
        items = Table(
            "practice_items",
            [
                ("session_id", "text"), ("started_at", "timestamp"), ("entry_id", "text"), ("title", "text"),
                ("minutes", "int"), ("load_units", "double"),
            ],
        )
        for practice_session in sessions:
            practice.rows.append([
                str(practice_session.id), practice_session.started_at, practice_session.ended_at,
                practice_session.mode.value, practice_session.duration_min, practice_session.logged_minutes,
                len({item.repertoire_entry_id for item in practice_session.items if item.repertoire_entry_id}),
                practice_session.perceived_tension,
            ])
            for item in practice_session.items:
                entry = by_id.get(item.repertoire_entry_id)
                items.rows.append([
                    str(practice_session.id), practice_session.started_at,
                    str(item.repertoire_entry_id) if item.repertoire_entry_id else None, title_of(entry),
                    item.minutes, plain(item.load_units),
                ])

        submissions_rows = (
            await self.session.execute(
                select(Submission)
                .options(selectin_polymorphic(Submission, [AudioSubmission]))
                .where(Submission.repertoire_entry_id.in_(list(by_id) or [NO_ENTRY]))
                .order_by(Submission.created_at)
            )
        ).scalars().all()
        scores = {
            score.audio_submission_id: score
            for score in (
                await self.session.execute(
                    select(ReadinessScore).where(ReadinessScore.repertoire_entry_id.in_(list(by_id) or [NO_ENTRY]))
                )
            ).scalars().all()
            if score.audio_submission_id
        }
        submissions = Table(
            "submissions",
            [
                ("submission_id", "text"), ("created_at", "timestamp"), ("entry_id", "text"), ("title", "text"),
                ("type", "text"), ("status", "text"), ("duration_sec", "int"), ("full_run_through", "bool"),
                ("verification", "bool"), ("overall_score", "double"), ("tempo_stability", "double"),
                ("restarts", "int"), ("memory_slips", "int"),
            ],
        )
        for submission in submissions_rows:
            audio = submission if isinstance(submission, AudioSubmission) else None
            score = scores.get(submission.id)
            submissions.rows.append([
                str(submission.id), submission.created_at, str(submission.repertoire_entry_id),
                title_of(by_id.get(submission.repertoire_entry_id)), submission.submission_type.value,
                submission.processing_status.value, audio.duration_sec if audio else None,
                audio.is_full_run_through if audio else None, audio.is_verification if audio else None,
                plain(score.overall_score) if score else None, plain(score.tempo_stability) if score else None,
                score.restart_count if score else None, score.memory_slip_count if score else None,
            ])

        techniques = {technique.id: technique for technique in (await self.session.execute(select(Technique))).scalars().all()}
        profiles = (
            await self.session.execute(select(UserTechniqueProfile).where(UserTechniqueProfile.user_id == user.id))
        ).scalars().all()
        mastery = Table(
            "technique_mastery",
            [
                ("technique", "text"), ("category", "text"), ("tier", "text"), ("proficiency", "double"),
                ("self_rating", "text"), ("is_strength", "bool"), ("is_weakness", "bool"), ("updated_at", "timestamp"),
            ],
        )
        for profile in profiles:
            technique = techniques.get(profile.technique_id)
            mastery.rows.append([
                technique.name if technique else str(profile.technique_id),
                technique.category.value if technique else None, tier_for(profile.proficiency_score),
                plain(profile.proficiency_score), profile.self_rating.value, profile.is_strength,
                profile.is_weakness, profile.updated_at,
            ])

        ledger_rows = (
            await self.session.execute(
                select(LedgerEntry).where(LedgerEntry.user_id == user.id).order_by(LedgerEntry.created_at, LedgerEntry.id)
            )
        ).scalars().all()
        wallet = Table(
            "wallet_history",
            [
                ("created_at", "timestamp"), ("reason", "text"), ("detail", "text"), ("xp_change", "int"),
                ("gold_change", "int"), ("xp_earned_to_date", "int"), ("gold_balance", "int"),
            ],
        )
        from app.services.economy import EconomyService

        current = await EconomyService(self.session).wallet(user)
        xp_offset = current.lifetime_xp - sum(max(row.delta_xp, 0) for row in ledger_rows)
        gold_offset = current.gold - sum(row.delta_gold for row in ledger_rows)
        xp_total = xp_offset
        gold_total = gold_offset
        for row in ledger_rows:
            xp_total += max(row.delta_xp, 0)
            gold_total += row.delta_gold
            wallet.rows.append([
                row.created_at, row.reason.value, row.detail, row.delta_xp, row.delta_gold, xp_total, gold_total,
            ])

        return [repertoire, practice, items, submissions, mastery, wallet]


def write_hyper(path: str, tables: list[Table], log_dir: str) -> dict[str, int]:
    try:
        from tableauhyperapi import (
            NULLABLE,
            Connection,
            CreateMode,
            HyperProcess,
            Inserter,
            SqlType,
            TableDefinition,
            TableName,
            Telemetry,
        )
    except ImportError as error:
        raise ExportUnavailable("the Tableau export needs the tableauhyperapi package on the server") from error

    types = {
        "text": SqlType.text(),
        "int": SqlType.big_int(),
        "double": SqlType.double(),
        "bool": SqlType.bool(),
        "date": SqlType.date(),
        "timestamp": SqlType.timestamp_tz(),
    }
    counts: dict[str, int] = {}
    with HyperProcess(
        telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_dir": log_dir}
    ) as hyper:
        with Connection(hyper.endpoint, path, CreateMode.CREATE_AND_REPLACE) as connection:
            connection.catalog.create_schema(SCHEMA)
            for table in tables:
                definition = TableDefinition(
                    TableName(SCHEMA, table.name),
                    [TableDefinition.Column(name, types[kind], NULLABLE) for name, kind in table.columns],
                )
                connection.catalog.create_table(definition)
                if table.rows:
                    with Inserter(connection, definition) as inserter:
                        inserter.add_rows(table.rows)
                        inserter.execute()
                counts[table.name] = len(table.rows)
    return counts


def build_file(tables: list[Table]) -> tuple[str, str]:
    workdir = tempfile.mkdtemp(prefix="pp-tableau-")
    path = os.path.join(workdir, "export.hyper")
    try:
        write_hyper(path, tables, workdir)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return path, workdir
