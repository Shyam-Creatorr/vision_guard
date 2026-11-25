from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, UserBadge

BADGE_CATALOG = {
    "first_audit": {
        "title": "First Guarded Audit",
        "description": "Completed your first scientific diagram audit.",
    },
    "sharp_eye": {
        "title": "Sharp Eye",
        "description": "Caught and respected UNVERIFIED ambiguity warnings without guessing.",
    },
    "quiz_ace": {
        "title": "Blank-Label Ace",
        "description": "Scored 80%+ on a Blank-Label Practice Mode challenge.",
    },
    "streak_3": {
        "title": "3-Day Science Streak",
        "description": "Practiced scientific diagrams 3 days in a row.",
    },
    "multilingual_explorer": {
        "title": "Polyglot Scientist",
        "description": "Studied a diagram in Hindi or Kannada.",
    },
}


def award_xp_and_badges(
    db: Session,
    user: User,
    xp_gain: int,
    badge_codes: list[str] | None = None,
    count_weekly_goal: bool = False,
) -> list[str]:
    profile = user.profile
    today = datetime.now(timezone.utc).date()

    if profile.last_active_date:
        delta = (today - profile.last_active_date).days
        if delta == 1:
            profile.streak_days += 1
        elif delta > 1:
            profile.streak_days = 1
    profile.last_active_date = today

    profile.xp += max(0, xp_gain)
    profile.level = 1 + (profile.xp // 250)
    if count_weekly_goal:
        profile.weekly_progress += 1

    candidates = list(badge_codes or [])
    if profile.streak_days >= 3:
        candidates.append("streak_3")

    existing = set(
        db.scalars(select(UserBadge.badge_code).where(UserBadge.user_id == user.id)).all()
    )
    newly_awarded: list[str] = []
    for code in candidates:
        if code in BADGE_CATALOG and code not in existing:
            db.add(UserBadge(user_id=user.id, badge_code=code))
            existing.add(code)
            newly_awarded.append(code)

    db.add(profile)
    return newly_awarded
