import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import CurrentUser, SessionDep
from app.core.database import SessionFactory
from app.core.security import tokens
from app.models.models import PracticeMode, PracticeSession, User
from app.schemas.schemas import (
    LiveFeedback,
    LoadAlertRead,
    LoadSummary,
    PageMeta,
    PracticeSessionClose,
    PracticeSessionPage,
    PracticeSessionRead,
    PracticeSessionStart,
    SessionItemCreate,
    SessionItemRead,
)
from app.services.practice import LiveListeningCoach, LoadGuard, PracticeSessionService

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("/sessions", response_model=PracticeSessionRead, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: PracticeSessionStart, user: CurrentUser, session: SessionDep
) -> PracticeSessionRead:
    try:
        practice = await PracticeSessionService(session).start(user, payload.mode, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PracticeSessionRead.model_validate(practice)


@router.get("/sessions", response_model=PracticeSessionPage)
async def list_sessions(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PracticeSessionPage:
    items, total = await PracticeSessionService(session).list(user, limit=limit, offset=offset)
    return PracticeSessionPage(
        meta=PageMeta(total=total, limit=limit, offset=offset, has_more=offset + len(items) < total),
        items=[PracticeSessionRead.model_validate(item) for item in items],
    )


@router.get("/sessions/open", response_model=Optional[PracticeSessionRead])
async def open_session(user: CurrentUser, session: SessionDep):
    practice = await PracticeSessionService(session).open_session(user)
    return PracticeSessionRead.model_validate(practice) if practice else None


@router.get("/sessions/{session_id}", response_model=PracticeSessionRead)
async def get_session(
    session_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PracticeSessionRead:
    try:
        practice = await PracticeSessionService(session).get(user, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return PracticeSessionRead.model_validate(practice)


@router.post("/sessions/{session_id}/items", response_model=SessionItemRead, status_code=status.HTTP_201_CREATED)
async def add_item(
    session_id: uuid.UUID, payload: SessionItemCreate, user: CurrentUser, session: SessionDep
) -> SessionItemRead:
    service = PracticeSessionService(session)
    try:
        item = await service.add_item(
            user,
            session_id,
            minutes=payload.minutes,
            repertoire_entry_id=payload.repertoire_entry_id,
            passage_id=payload.passage_id,
            drill_id=payload.drill_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    refreshed = await service.get(user, session_id)
    stored = next(i for i in refreshed.items if i.id == item.id)
    return SessionItemRead.model_validate(stored)


@router.post("/sessions/{session_id}/close", response_model=PracticeSessionRead)
async def close_session(
    session_id: uuid.UUID, payload: PracticeSessionClose, user: CurrentUser, session: SessionDep
) -> PracticeSessionRead:
    service = PracticeSessionService(session)
    try:
        practice = await service.close(user, session_id, payload.perceived_tension)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await LoadGuard(session).evaluate(user)
    return PracticeSessionRead.model_validate(practice)


@router.get("/load", response_model=LoadSummary)
async def load_summary(
    user: CurrentUser,
    session: SessionDep,
    week_of: Optional[date] = Query(default=None),
) -> LoadSummary:
    summary = await LoadGuard(session).summary(user, week_of)
    return LoadSummary(**summary)


@router.get("/load/alerts", response_model=list[LoadAlertRead])
async def load_alerts(user: CurrentUser, session: SessionDep) -> list[LoadAlertRead]:
    alerts = await LoadGuard(session).list_alerts(user)
    return [LoadAlertRead.model_validate(a) for a in alerts]


@router.post("/load/alerts/{alert_id}/acknowledge", response_model=LoadAlertRead)
async def acknowledge_alert(
    alert_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> LoadAlertRead:
    try:
        alert = await LoadGuard(session).acknowledge(user, alert_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return LoadAlertRead.model_validate(alert)


@router.websocket("/live")
async def live_listening(websocket: WebSocket, token: str = Query(...), target_bpm: Optional[int] = Query(default=None)):
    subject = tokens.subject(token)
    if subject is None:
        await websocket.close(code=4401)
        return
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        await websocket.close(code=4401)
        return

    async with SessionFactory() as db:
        user = await db.get(User, user_id)
        if user is None:
            await websocket.close(code=4401)
            return
        service = PracticeSessionService(db)
        practice = await service.open_session(user)
        if practice is None:
            practice = await service.start(user, PracticeMode.LIVE_LISTENING)
            await db.commit()
        session_id = practice.id

    await websocket.accept()
    coach = LiveListeningCoach(target_bpm)
    try:
        await websocket.send_json({"type": "ready", "session_id": str(session_id), "target_bpm": target_bpm})
        while True:
            payload = await websocket.receive_json()
            if payload.get("type") == "stop":
                break
            feedback = coach.ingest(payload)
            await websocket.send_json({"type": "feedback", **feedback})
    except WebSocketDisconnect:
        pass
    finally:
        report = coach.report()
        if coach.frames:
            async with SessionFactory() as db:
                user = await db.get(User, user_id)
                if user is not None:
                    service = PracticeSessionService(db)
                    try:
                        await service.add_item(user, session_id, minutes=max(1, coach.frames // 60))
                        await service.close(user, session_id, report.get("perceived_tension"))
                        await db.commit()
                    except (LookupError, ValueError):
                        await db.rollback()
        try:
            await websocket.send_json({"type": "report", **report})
            await websocket.close()
        except RuntimeError:
            pass
