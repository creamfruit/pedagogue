from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import Storage
from app.models.models import AIGeneration, AudioSubmission, PdfSubmission, RepertoireEntry, User
from app.services import coach_feedback

logger = logging.getLogger("piano.account")


@dataclass
class DeletionReport:
    user_id: uuid.UUID
    files_found: int
    files_removed: int
    file_errors: int


async def stored_keys(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    pdf_rows = await session.execute(
        select(PdfSubmission.storage_key, PdfSubmission.musicxml_key)
        .join(RepertoireEntry, PdfSubmission.repertoire_entry_id == RepertoireEntry.id)
        .where(RepertoireEntry.user_id == user_id)
    )
    audio_rows = await session.execute(
        select(AudioSubmission.storage_key, AudioSubmission.midi_key)
        .join(RepertoireEntry, AudioSubmission.repertoire_entry_id == RepertoireEntry.id)
        .where(RepertoireEntry.user_id == user_id)
    )
    keys = [key for row in [*pdf_rows.all(), *audio_rows.all()] for key in row if key]
    return list(dict.fromkeys(keys))


async def audio_submission_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(AudioSubmission.id)
        .join(RepertoireEntry, AudioSubmission.repertoire_entry_id == RepertoireEntry.id)
        .where(RepertoireEntry.user_id == user_id)
    )
    return list(result.scalars().all())


def remove_files(storage: Storage, user_id: uuid.UUID, keys: list[str]) -> tuple[int, int]:
    removed = 0
    errors = 0
    for key in keys:
        try:
            if storage.delete(key):
                removed += 1
        except Exception:
            errors += 1
            logger.exception("could not delete %s for removed account %s", key, user_id)
    try:
        removed += storage.delete_user_files(user_id)
    except Exception:
        errors += 1
        logger.exception("could not purge stored files for removed account %s", user_id)
    return removed, errors


async def delete_account(session: AsyncSession, user: User, storage: Storage) -> DeletionReport:
    user_id = user.id
    keys = await stored_keys(session, user_id)
    coach_keys = [coach_feedback.subject_key(sid) for sid in await audio_submission_ids(session, user_id)]
    if coach_keys:
        await session.execute(
            delete(AIGeneration).where(
                AIGeneration.purpose == coach_feedback.PURPOSE, AIGeneration.subject_key.in_(coach_keys)
            )
        )
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
    session.expunge_all()
    removed, errors = remove_files(storage, user_id, keys)
    logger.info("deleted account %s, %s stored files removed", user_id, removed)
    return DeletionReport(user_id=user_id, files_found=len(keys), files_removed=removed, file_errors=errors)
