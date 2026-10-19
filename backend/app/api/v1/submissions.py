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
from app.core.rate_limit import enforce
from app.core.storage import SCORE_MEDIA, FileTooLarge, QuotaExceeded, UnsupportedMediaType, score_format, storage
from app.schemas.schemas import (
    AnalysisDetail,
    SubmissionAccepted,
    SubmissionDetail,
    SubmissionRead,
    TextSubmissionCreate,
)
from app.services.coach_feedback import feedback_for
from app.services.repertoire import SubmissionService
from app.workers.queue import get_queue

router = APIRouter(tags=["submissions"])


DIGITAL_SCORE_SUFFIXES = (".musicxml", ".xml", ".mxl", ".mid", ".midi", ".kar")


def is_pdf_score(submission) -> bool:
    key = (getattr(submission, "storage_key", None) or "").lower()
    return key.startswith("scores/") and not getattr(submission, "musicxml_key", None) and not key.endswith(DIGITAL_SCORE_SUFFIXES)


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
    await get_queue(background_tasks).enqueue("process_submission", submission_id)


@router.get("/repertoire/{entry_id}/submissions", response_model=list[SubmissionDetail])
async def list_submissions(
    entry_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[SubmissionDetail]:
    try:
        submissions = await SubmissionService(session).list_for_entry(user, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    feedback = await feedback_for(session, submissions)
    return [SubmissionDetail.model_validate(s).model_copy(update={"coach_feedback": feedback.get(s.id)}) for s in submissions]


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
    "/repertoire/{entry_id}/submissions/score",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
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
    await enforce("upload", str(user.id))
    try:
        kind = score_format(file.file, file.filename)
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    if kind == "pdf":
        await enforce("pdf_analysis", str(user.id))
    service = SubmissionService(session)
    try:
        submission = await service.add_pdf(
            user, entry_id, file.file, file.filename or "", file.content_type
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except (FileTooLarge, QuotaExceeded) as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    await enqueue(session, submission.id, background_tasks)
    return accepted(submission, background_tasks)


def audio_guard() -> None:
    if not settings.audio_features_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audio recordings are coming soon.")


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
    audio_guard()
    await enforce("upload", str(user.id))
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
    except (FileTooLarge, QuotaExceeded) as exc:
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
    feedback = await feedback_for(session, [submission])
    return SubmissionDetail.model_validate(submission).model_copy(update={"coach_feedback": feedback.get(submission.id)})


@router.get("/submissions/{submission_id}/file")
async def submission_file(submission_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    try:
        submission = await SubmissionService(session).get(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    key = getattr(submission, "storage_key", None)
    if not key or not storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    suffix = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
    with storage.open(key) as handle:
        data = handle.read()
    media = SCORE_MEDIA.get(suffix, "application/octet-stream")
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="score{suffix}"', "Cache-Control": "private, max-age=3600"},
    )


@router.get("/submissions/{submission_id}/crops/{index}")
async def submission_crop(submission_id: uuid.UUID, index: int, user: CurrentUser, session: SessionDep) -> Response:
    try:
        submission = await SubmissionService(session).get(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    crops = []
    for analysis in sorted(submission.analyses, key=lambda item: item.created_at, reverse=True):
        crops = (analysis.raw_result or {}).get("crops") or []
        if crops:
            break
    if not 0 <= index < len(crops) or not storage.exists(crops[index]["key"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crop not found")
    with storage.open(crops[index]["key"]) as handle:
        data = handle.read()
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


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
        existing = await service.get(user, submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if is_pdf_score(existing):
        await enforce("pdf_analysis", str(user.id))
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
