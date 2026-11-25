from fastapi import APIRouter
from app.api.v1 import (
    analyses,
    auth,
    gamification,
    health,
    library,
    practice,
    teacher,
    uploads,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(uploads.router)
api_router.include_router(analyses.router)
api_router.include_router(practice.router)
api_router.include_router(library.router)
api_router.include_router(gamification.router)
api_router.include_router(teacher.router)
