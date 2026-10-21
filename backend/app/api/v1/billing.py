from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.billing import PlanOut
from app.services.billing import PlanService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plan", response_model=PlanOut)
async def current_plan(user: CurrentUser, session: SessionDep) -> PlanOut:
    return PlanOut(**await PlanService(session).entitlements(user.id))
