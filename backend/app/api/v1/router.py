from fastapi import APIRouter

from app.api.v1 import (
    auth,
    billing,
    coach,
    economy,
    events,
    export,
    keyboard,
    onboarding,
    performance,
    practice,
    progression,
    repertoire,
    social,
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
api_router.include_router(keyboard.router)
api_router.include_router(billing.router)
api_router.include_router(billing.admin_router)
api_router.include_router(coach.router)
api_router.include_router(performance.router)
api_router.include_router(economy.router)
api_router.include_router(social.router)
api_router.include_router(events.router)
api_router.include_router(export.router)
