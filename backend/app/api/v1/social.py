import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, SessionDep
from app.services.leaderboard import FriendService, LeaderboardService, practice_week_board, roulette_board
from app.services.roulette import RouletteService, utc_today
from app.services.streaks import zone_for

router = APIRouter(tags=["social"])


class FriendRequest(BaseModel):
    email: EmailStr


class RouletteAnswers(BaseModel):
    answers: list[Optional[str]] = Field(max_length=32)


@router.get("/friends")
async def friends(user: CurrentUser, session: SessionDep) -> dict:
    return await FriendService(session).overview(user)


@router.post("/friends/requests", status_code=status.HTTP_202_ACCEPTED)
async def request_friend(payload: FriendRequest, user: CurrentUser, session: SessionDep) -> dict:
    await FriendService(session).request(user, payload.email)
    return {"detail": "If that address belongs to a pianist here, they'll see your request."}


@router.post("/friends/requests/{friendship_id}/{decision}", status_code=status.HTTP_204_NO_CONTENT)
async def respond_friend(friendship_id: uuid.UUID, decision: Literal["accept", "decline"], user: CurrentUser, session: SessionDep) -> Response:
    try:
        await FriendService(session).respond(user, friendship_id, decision == "accept")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/friends/{friendship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(friendship_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    try:
        await FriendService(session).remove(user, friendship_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/leaderboards/practice-week")
async def practice_week(user: CurrentUser, session: SessionDep, scope: Literal["friends", "global"] = Query(default="friends")) -> dict:
    from datetime import datetime

    today = datetime.now(zone_for(user)).date()
    return await LeaderboardService(session).standings(practice_week_board(today), user, scope)


@router.get("/leaderboards/roulette")
async def roulette_standings(user: CurrentUser, session: SessionDep, scope: Literal["friends", "global"] = Query(default="global")) -> dict:
    return await LeaderboardService(session).standings(roulette_board(utc_today()), user, scope)


@router.get("/roulette/today")
async def roulette_today(user: CurrentUser, session: SessionDep) -> dict:
    return await RouletteService(session).today(user)


@router.post("/roulette/today/start")
async def roulette_start(user: CurrentUser, session: SessionDep) -> dict:
    return await RouletteService(session).start(user)


@router.post("/roulette/today/submit")
async def roulette_submit(payload: RouletteAnswers, user: CurrentUser, session: SessionDep) -> dict:
    try:
        return await RouletteService(session).submit(user, payload.answers)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
