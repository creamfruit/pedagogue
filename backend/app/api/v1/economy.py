from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.schemas import (
    AchievementRead,
    CosmeticRead,
    LedgerEntryRead,
    LoadoutRead,
    ProfileSummary,
    StreakRead,
    WalletRead,
)
from app.services.economy import AchievementEngine, CosmeticService, EconomyService
from app.services.growth import GrowthService
from app.services.streaks import NudgeService, StreakService

router = APIRouter(tags=["economy"])


@router.get("/wallet", response_model=WalletRead)
async def wallet(user: CurrentUser, session: SessionDep) -> WalletRead:
    return WalletRead.model_validate(await EconomyService(session).wallet(user))


@router.get("/wallet/ledger", response_model=list[LedgerEntryRead])
async def ledger(
    user: CurrentUser, session: SessionDep, limit: int = Query(default=40, ge=1, le=200)
) -> list[LedgerEntryRead]:
    entries = await EconomyService(session).ledger(user, limit)
    return [LedgerEntryRead.model_validate(entry) for entry in entries]


@router.get("/achievements", response_model=list[AchievementRead])
async def achievements(user: CurrentUser, session: SessionDep) -> list[AchievementRead]:
    engine = AchievementEngine(session)
    await engine.evaluate(user)
    return [AchievementRead(**row) for row in await engine.list_for(user)]


@router.get("/shop", response_model=list[CosmeticRead])
async def shop(user: CurrentUser, session: SessionDep) -> list[CosmeticRead]:
    return [CosmeticRead(**row) for row in await CosmeticService(session).catalog(user)]


@router.post("/shop/{cosmetic_id}/buy", response_model=list[CosmeticRead], status_code=status.HTTP_201_CREATED)
async def buy(cosmetic_id: int, user: CurrentUser, session: SessionDep) -> list[CosmeticRead]:
    service = CosmeticService(session)
    try:
        await service.purchase(user, cosmetic_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return [CosmeticRead(**row) for row in await service.catalog(user)]


@router.post("/shop/{cosmetic_id}/equip", response_model=LoadoutRead)
async def equip(cosmetic_id: int, user: CurrentUser, session: SessionDep) -> LoadoutRead:
    service = CosmeticService(session)
    try:
        await service.equip(user, cosmetic_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return LoadoutRead(**await service.loadout(user))


@router.get("/loadout", response_model=LoadoutRead)
async def loadout(user: CurrentUser, session: SessionDep) -> LoadoutRead:
    return LoadoutRead(**await CosmeticService(session).loadout(user))


@router.get("/profile/summary", response_model=ProfileSummary)
async def profile_summary(user: CurrentUser, session: SessionDep) -> ProfileSummary:
    economy = EconomyService(session)
    engine = AchievementEngine(session)
    cosmetics = CosmeticService(session)
    await engine.evaluate(user)
    rows = await engine.list_for(user)
    return ProfileSummary(
        wallet=WalletRead.model_validate(await economy.wallet(user)),
        loadout=LoadoutRead(**await cosmetics.loadout(user)),
        achievements_earned=sum(1 for row in rows if row["earned"]),
        achievements_total=len(rows),
        streak=StreakRead(**(await StreakService(session).stats(user)).as_dict()),
        nudge=await NudgeService(session).nudge(user),
    )


@router.get("/progress/difficulty-history")
async def difficulty_history(user: CurrentUser, session: SessionDep, weeks: int = Query(default=26, ge=4, le=104)) -> dict:
    return await GrowthService(session).difficulty_history(user, weeks)


@router.get("/progress/streak", response_model=StreakRead)
async def streak(user: CurrentUser, session: SessionDep) -> StreakRead:
    return StreakRead(**(await StreakService(session).stats(user)).as_dict())
