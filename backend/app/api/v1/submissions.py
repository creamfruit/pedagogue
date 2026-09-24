import json
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.storage import FileTooLarge, UnsupportedMediaType
from app.schemas.schemas import (
    AnalysisDetail,
    SubmissionAccepted,
    SubmissionDetail,
    SubmissionRead,
    TextSubmissionCreate,
)
from app.services.repertoire import SubmissionService
from app.workers.queue import BackgroundQueue

router = APIRouter(tags=["submissions"])


def poll_url(submission_id: uuid.UUID) -> str:
    return f"{settings.api_v1_prefix}/submissions/{submission_id}"


def accepted(submission, background_tasks: BackgroundTasks) -> SubmissionAccepted:
    return SubmissionAccepted(
        submission=SubmissionRead.model_validate(submission),
        queued=True,
        poll_url=poll_url(submission.id),
    )


async def enqueue(session, submission_id: uuid.UUID, background_tasks: BackgroundTasks) -> None:
    await session.commit()
    await BackgroundQueue(background_tasks).enqueue(submission_id)


@router.get("/repertoire/{entry_id}/submissions", response_model=list[SubmissionDetail])
async def list_submissions(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[SubmissionDetail]:
    try:
        submissions = await SubmissionService(session).list_for_entry(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return [SubmissionDetail.model_validate(s) for s in submissions]


@router.post(
    "/repertoire/{entry_id}/submissions/text",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_text(
    entry_id: uuid.UUID,
    payload: TextSubmissionCreate,
    user: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> SubmissionAccepted:
    service = SubmissionService(session)
    try:
        submission = await service.add_text(user, entry_id, payload.body)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    await enqueue(session, submission.id, background_tasks)
    return accepted(submission, background_tasks)


@router.post(
    "/repertoire/{entry_id}/submissions/pdf",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_pdf(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> SubmissionAccepted:
    service = SubmissionService(session)
    try:
        submission = await service.add_pdf(
            user, entry_id, file.file, file.filename or "score.pdf", file.content_type
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except FileTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    await enqueue(session, submission.id, background_tasks)
    return accepted(submission, background_tasks)


@router.post(
    "/repertoire/{entry_id}/submissions/audio",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_audio(
    entry_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    duration_sec: Optional[int] = Form(default=None),
    is_full_run_through: bool = Form(default=False),
    is_verification: bool = Form(default=False),
    tempo_curve: Optional[str] = Form(default=None),
) -> SubmissionAccepted:
    service = SubmissionService(session)
    try:
        parsed_curve = json.loads(tempo_curve) if tempo_curve else None
    except ValueError:
        parsed_curve = None
    try:
        submission = await service.add_audio(
            user,
            entry_id,
            file.file,
            file.filename or "take.wav",
            file.content_type,
            duration_sec=duration_sec,
            is_full_run_through=is_full_run_through,
            is_verification=is_verification,
            tempo_curve=parsed_curve,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except FileTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    await enqueue(session, submission.id, background_tasks)
    return accepted(submission, background_tasks)


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
    submission_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> SubmissionDetail:
    try:
        submission = await SubmissionService(session).get(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return SubmissionDetail.model_validate(submission)


@router.get("/submissions/{submission_id}/analyses", response_model=list[AnalysisDetail])
async def get_analyses(
    submission_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[AnalysisDetail]:
    try:
        analyses = await SubmissionService(session).analyses(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return [AnalysisDetail.model_validate(a) for a in analyses]


@router.post(
    "/submissions/{submission_id}/retry",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_submission(
    submission_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> SubmissionAccepted:
    service = SubmissionService(session)
    try:
        submission = await service.requeue(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await enqueue(session, submission.id, background_tasks)
    return accepted(submission, background_tasks)


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_submission(
    submission_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    try:
        await SubmissionService(session).delete(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
