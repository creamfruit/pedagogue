from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.schemas.schemas import MeteorCatch, MeteorShowerCreate
from app.services.meteor import MeteorService, piece_card, shower_summary, utcnow

router = APIRouter(tags=["events"])


@router.get("/meteor-showers/current")
async def current_shower(user: CurrentUser, session: SessionDep) -> dict:
    return await MeteorService(session).view(user)


@router.post("/meteor-showers/{shower_id}/catch", status_code=status.HTTP_201_CREATED)
async def catch_meteor(shower_id: int, payload: MeteorCatch, user: CurrentUser, session: SessionDep) -> dict:
    try:
        return await MeteorService(session).catch(user, shower_id, payload.piece_id)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(error))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.get("/admin/meteor-showers")
async def list_showers(admin: AdminUser, session: SessionDep) -> list[dict]:
    now = utcnow()
    showers = await MeteorService(session).recent()
    return [
        {**shower_summary(shower, now), "pieces": [piece_card(link.piece) for link in shower.pieces]}
        for shower in showers
    ]


@router.post("/admin/meteor-showers", status_code=status.HTTP_201_CREATED)
async def create_shower(payload: MeteorShowerCreate, admin: AdminUser, session: SessionDep) -> dict:
    service = MeteorService(session)
    try:
        shower = await service.schedule(**payload.model_dump(), created_by=admin.id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
    fresh = await service.get(shower.id)
    return {**shower_summary(fresh, utcnow()), "pieces": [piece_card(link.piece) for link in fresh.pieces]}


@router.post("/admin/meteor-showers/{shower_id}/end")
async def end_shower(shower_id: int, admin: AdminUser, session: SessionDep) -> dict:
    shower = await MeteorService(session).end(shower_id)
    return {"ended": shower_id, "kept": shower is not None}
