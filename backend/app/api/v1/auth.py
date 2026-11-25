from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.deps import require_csrf
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_random_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import PasswordResetToken, RefreshToken, User, UserProfile
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    UserProfileResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _to_user_response(user: User) -> UserResponse:
    p = user.profile
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        profile=UserProfileResponse(
            full_name=p.full_name,
            grade_level=p.grade_level,
            subjects=list(p.subjects_json or []),
            learning_goal=p.learning_goal,
            preferred_language=p.preferred_language,  # type: ignore[arg-type]
            theme=p.theme,  # type: ignore[arg-type]
            leaderboard_opt_in=p.leaderboard_opt_in,
            xp=p.xp,
            level=p.level,
            streak_days=p.streak_days,
            weekly_goal_target=p.weekly_goal_target,
            weekly_progress=p.weekly_progress,
            onboarding_completed=p.onboarding_completed,
        ),
    )


def _issue_session_cookies(
    response: Response,
    db: Session,
    user: User,
    family_id: str | None = None,
) -> str:
    settings = get_settings()
    raw_refresh = generate_random_token(32)
    csrf_token = generate_csrf_token()
    fid = family_id or str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            family_id=fid,
            expires_at=expires_at,
        )
    )

    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key="vg_refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key="vg_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    access_token = create_access_token(user.id, user.role)
    response.set_cookie(
        key="vg_access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/api/v1",
    )
    return access_token


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    email_norm = payload.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email_norm))
    if existing:
        raise AppError("EMAIL_EXISTS", "An account with this email already exists.", status_code=409)

    user = User(
        email=email_norm,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    user.profile = UserProfile(full_name=payload.full_name.strip())
    db.add(user)
    db.flush()

    access_token = _issue_session_cookies(response, db, user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=access_token, user=_to_user_response(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    email_norm = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email_norm))
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Incorrect email or password.", status_code=401)
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED", "This account has been disabled.", status_code=403)

    access_token = _issue_session_cookies(response, db, user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=access_token, user=_to_user_response(user))


@router.post("/refresh", response_model=AuthResponse, dependencies=[Depends(require_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    raw_refresh = request.cookies.get("vg_refresh_token")
    if not raw_refresh:
        raise AppError("MISSING_REFRESH_TOKEN", "Refresh session cookie is missing.", status_code=401)

    token_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh)))
    if not token_row:
        raise AppError("INVALID_REFRESH_TOKEN", "Refresh session is invalid.", status_code=401)

    now = datetime.now(timezone.utc)
    # Reuse detection: if already revoked, invalidate entire family
    if token_row.revoked_at is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token_row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        raise AppError("TOKEN_REUSE_DETECTED", "Session was revoked for security. Please sign in again.", status_code=401)

    expires_at = token_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise AppError("REFRESH_EXPIRED", "Session expired. Please sign in again.", status_code=401)

    user = db.get(User, token_row.user_id)
    if not user or not user.is_active:
        raise AppError("USER_NOT_FOUND", "User account not found.", status_code=401)

    token_row.revoked_at = now
    access_token = _issue_session_cookies(response, db, user, family_id=token_row.family_id)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=access_token, user=_to_user_response(user))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, bool]:
    raw_refresh = request.cookies.get("vg_refresh_token")
    if raw_refresh:
        token_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh)))
        if token_row:
            now = datetime.now(timezone.utc)
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            db.commit()

    response.delete_cookie("vg_refresh_token", path="/api/v1/auth")
    response.delete_cookie("vg_access_token", path="/api/v1")
    response.delete_cookie("vg_csrf_token", path="/")
    return {"logged_out": True}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str | bool]:
    settings = get_settings()
    email_norm = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email_norm))
    dev_token = None
    if user:
        raw_token = generate_random_token(24)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        db.commit()
        if settings.APP_ENV == "development":
            dev_token = raw_token

    res: dict[str, str | bool] = {
        "sent": True,
        "message": "If an account exists for that email, reset instructions are ready.",
    }
    if dev_token:
        res["dev_reset_token"] = dev_token
    return res


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict[str, bool]:
    token_row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(payload.token))
    )
    now = datetime.now(timezone.utc)
    if not token_row or token_row.used_at is not None:
        raise AppError("INVALID_RESET_TOKEN", "Password reset token is invalid or already used.", status_code=400)

    exp = token_row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now:
        raise AppError("EXPIRED_RESET_TOKEN", "Password reset token has expired.", status_code=400)

    user = db.get(User, token_row.user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "Associated account not found.", status_code=404)

    user.password_hash = hash_password(payload.new_password)
    token_row.used_at = now
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
    return {"reset": True}


@router.post("/google")
def google_signin(payload: GoogleAuthRequest) -> dict:
    settings = get_settings()
    if not settings.GOOGLE_AUTH_ENABLED:
        raise AppError(
            "FEATURE_DISABLED",
            "Google Sign-In is disabled in this environment. Use email and password.",
            status_code=501,
        )
    raise AppError(
        "GOOGLE_AUTH_UNCONFIGURED",
        "Google Client ID verification requires production OAuth credentials.",
        status_code=501,
    )
