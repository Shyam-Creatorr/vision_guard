from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "visionguard-tutor"}


@router.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> dict[str, str | bool]:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError("DB_UNAVAILABLE", "Database readiness check failed.", status_code=503) from exc
    return {
        "status": "ready",
        "database": "ok",
        "ai_configured": bool(settings.GEMINI_API_KEY.strip()),
        "demo_mode_available": True,
    }
