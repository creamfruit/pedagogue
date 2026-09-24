from fastapi import APIRouter

from app.api.v1 import (
    auth,
    coach,
    economy,
    onboarding,
    performance,
    practice,
    progression,
    repertoire,
    submissions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(onboarding.router)
api_router.include_router(onboarding.catalog_router)
api_router.include_router(repertoire.router)
api_router.include_router(submissions.router)
api_router.include_router(progression.router)
api_router.include_router(practice.router)
api_router.include_router(coach.router)
api_router.include_router(performance.router)
api_router.include_router(economy.router)
