from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Optional

from app.core.database import session_scope
from app.models.models import ProcessingStatus
from app.services.analyzers import analyzer_for, load_submission

logger = logging.getLogger("piano.worker")


async def process_submission(submission_id: uuid.UUID) -> Optional[str]:
    async with session_scope() as session:
        submission = await load_submission(session, submission_id)
        if submission is None:
            logger.warning("submission %s vanished before processing", submission_id)
            return None
        if submission.processing_status not in {ProcessingStatus.QUEUED, ProcessingStatus.FAILED}:
            logger.info("submission %s already %s", submission_id, submission.processing_status.value)
            return submission.processing_status.value
        analyzer = analyzer_for(submission, session)
        analysis = await analyzer.run(submission)
        logger.info("submission %s -> %s", submission_id, submission.processing_status.value)
        return analysis.summary


class JobQueue(ABC):
    @abstractmethod
    async def enqueue(self, submission_id: uuid.UUID) -> None: ...


class InlineQueue(JobQueue):
    async def enqueue(self, submission_id: uuid.UUID) -> None:
        await process_submission(submission_id)


class BackgroundQueue(JobQueue):
    def __init__(self, background_tasks) -> None:
        self.background_tasks = background_tasks

    async def enqueue(self, submission_id: uuid.UUID) -> None:
        self.background_tasks.add_task(process_submission, submission_id)


class RedisQueue(JobQueue):
    def __init__(self, redis_url: Optional[str] = None) -> None:
        from app.core.config import settings

        self.redis_url = redis_url or settings.redis_url
        self._pool = None

    async def pool(self):
        if self._pool is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            self._pool = await create_pool(RedisSettings.from_dsn(self.redis_url))
        return self._pool

    async def enqueue(self, submission_id: uuid.UUID) -> None:
        pool = await self.pool()
        await pool.enqueue_job("process_submission", str(submission_id))


async def arq_process_submission(ctx, submission_id: str) -> Optional[str]:
    return await process_submission(uuid.UUID(submission_id))


class WorkerSettings:
    functions = [arq_process_submission]
    max_jobs = 4
    job_timeout = 900
