from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import _to_user_response
from app.api.v1.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import UpdateProfileRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    return _to_user_response(user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    p = user.profile
    if payload.full_name is not None:
        p.full_name = payload.full_name.strip()
    if payload.grade_level is not None:
        p.grade_level = payload.grade_level.strip()
    if payload.subjects is not None:
        p.subjects_json = [s.strip() for s in payload.subjects if s.strip()]
    if payload.learning_goal is not None:
        p.learning_goal = payload.learning_goal.strip()
    if payload.preferred_language is not None:
        p.preferred_language = payload.preferred_language
    if payload.theme is not None:
        p.theme = payload.theme
    if payload.leaderboard_opt_in is not None:
        p.leaderboard_opt_in = payload.leaderboard_opt_in
    if payload.weekly_goal_target is not None:
        p.weekly_goal_target = payload.weekly_goal_target
    if payload.onboarding_completed is not None:
        p.onboarding_completed = payload.onboarding_completed

    db.add(p)
    db.commit()
    db.refresh(user)
    return _to_user_response(user)
