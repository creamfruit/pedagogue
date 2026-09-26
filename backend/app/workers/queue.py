from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.core.database import session_scope
from app.models.models import ProcessingStatus, SubmissionType
from app.services.analyzers import analyzer_for, load_submission

logger = logging.getLogger("piano.worker")


async def process_submission(submission_id: uuid.UUID | str) -> Optional[str]:
    submission_id = uuid.UUID(str(submission_id))
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
        wants_feedback = submission.submission_type == SubmissionType.AUDIO and submission.processing_status == ProcessingStatus.DONE
    if wants_feedback:
        await run_job("generate_coach_feedback", submission_id)
    return analysis.summary


async def generate_piece_metadata(piece_id: int) -> Optional[str]:
    from app.services.piece_metadata import generate_piece_metadata as run

    return await run(int(piece_id))


async def generate_coach_feedback(submission_id: uuid.UUID | str) -> Optional[str]:
    from app.services.coach_feedback import generate_coach_feedback as run

    return await run(submission_id)


JOBS: dict[str, Callable[..., Awaitable[Any]]] = {
    "process_submission": process_submission,
    "generate_piece_metadata": generate_piece_metadata,
    "generate_coach_feedback": generate_coach_feedback,
}


async def run_job(name: str, *args: Any) -> Any:
    try:
        return await JOBS[name](*args)
    except Exception:
        logger.exception("job %s%r failed", name, args)
        return None


class JobQueue(ABC):
    @abstractmethod
    async def enqueue(self, name: str, *args: Any) -> None: ...


class InlineQueue(JobQueue):
    async def enqueue(self, name: str, *args: Any) -> None:
        await run_job(name, *args)


class BackgroundQueue(JobQueue):
    def __init__(self, background_tasks) -> None:
        self.background_tasks = background_tasks

    async def enqueue(self, name: str, *args: Any) -> None:
        self.background_tasks.add_task(run_job, name, *args)


class RedisQueue(JobQueue):
    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or settings.redis_url
        self._pool = None

    async def pool(self):
        if self._pool is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            self._pool = await create_pool(RedisSettings.from_dsn(self.redis_url))
        return self._pool

    async def enqueue(self, name: str, *args: Any) -> None:
        pool = await self.pool()
        await pool.enqueue_job(name, *[str(arg) for arg in args])


_redis_queue: Optional[RedisQueue] = None


def get_queue(background_tasks=None) -> JobQueue:
    global _redis_queue
    if settings.job_queue == "redis":
        if _redis_queue is None:
            _redis_queue = RedisQueue()
        return _redis_queue
    if settings.job_queue == "inline" or background_tasks is None:
        return InlineQueue()
    return BackgroundQueue(background_tasks)


def _arq_job(name: str):
    async def job(ctx, *args):
        return await run_job(name, *args)

    job.__name__ = name
    job.__qualname__ = name
    return job


class WorkerSettings:
    functions = [_arq_job(name) for name in JOBS]
    max_jobs = 4
    job_timeout = 900
