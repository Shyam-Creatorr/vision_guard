from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.models import AnalysisJob, PracticeAttempt, User, UserBadge, UserProfile
from app.db.session import get_db
from app.schemas.gamification import (
    BadgeItem,
    DailyProgressPoint,
    GamificationSummaryResponse,
    LeaderboardEntry,
)
from app.services.gamification import BADGE_CATALOG

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/summary", response_model=GamificationSummaryResponse)
def get_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GamificationSummaryResponse:
    profile = user.profile
    earned_rows = db.scalars(select(UserBadge).where(UserBadge.user_id == user.id)).all()
    earned_map = {b.badge_code: b.awarded_at for b in earned_rows}

    badges = [
        BadgeItem(
            code=code,
            title=meta["title"],
            description=meta["description"],
            earned=code in earned_map,
            awarded_at=earned_map.get(code),
        )
        for code, meta in BADGE_CATALOG.items()
    ]

    # Build 7-day activity chart
    today = datetime.now(timezone.utc).date()
    day_buckets: dict[str, dict[str, int]] = {}
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        day_buckets[d.isoformat()] = {"xp": 0, "sessions": 0}

    start_dt = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    attempts = db.scalars(
        select(PracticeAttempt).where(
            PracticeAttempt.user_id == user.id,
            PracticeAttempt.created_at >= start_dt,
        )
    ).all()
    for att in attempts:
        key = att.created_at.date().isoformat()
        if key in day_buckets:
            day_buckets[key]["xp"] += att.xp_awarded
            day_buckets[key]["sessions"] += 1

    jobs = db.scalars(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user.id,
            AnalysisJob.created_at >= start_dt,
        )
    ).all()
    for j in jobs:
        key = j.created_at.date().isoformat()
        if key in day_buckets:
            day_buckets[key]["xp"] += 35
            day_buckets[key]["sessions"] += 1

    recent_days = [
        DailyProgressPoint(day=k[5:], xp=v["xp"], sessions=v["sessions"])
        for k, v in day_buckets.items()
    ]
    xp_in_level = profile.xp % 250
    return GamificationSummaryResponse(
        xp=profile.xp,
        level=profile.level,
        xp_to_next_level=250 - xp_in_level,
        streak_days=profile.streak_days,
        weekly_goal_target=profile.weekly_goal_target,
        weekly_progress=profile.weekly_progress,
        badges=badges,
        recent_days=recent_days,
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db)) -> list[LeaderboardEntry]:
    profiles = db.scalars(
        select(UserProfile)
        .where(UserProfile.leaderboard_opt_in.is_(True))
        .order_by(UserProfile.xp.desc())
        .limit(20)
    ).all()
    return [
        LeaderboardEntry(
            rank=idx,
            full_name=p.full_name,
            level=p.level,
            xp=p.xp,
            streak_days=p.streak_days,
        )
        for idx, p in enumerate(profiles, start=1)
    ]
