import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import decode_access_token, verify_csrf_token
from app.db.models import User
from app.db.session import get_db


def _extract_user_from_token(token: str, db: Session) -> User | None:
    try:
        payload = decode_access_token(token)
        user = db.get(User, payload.get("sub"))
        return user if user and user.is_active else None
    except jwt.PyJWTError:
        return None


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif request.cookies.get("vg_access_token"):
        token = request.cookies.get("vg_access_token")

    if not token:
        raise AppError("UNAUTHORIZED", "Authentication credentials were not provided.", status_code=401)
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_TOKEN", "Session token is invalid or expired.", status_code=401) from exc

    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise AppError("USER_NOT_FOUND", "Authenticated account no longer exists or is inactive.", status_code=401)
    return user


def get_optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif request.cookies.get("vg_access_token"):
        token = request.cookies.get("vg_access_token")

    if not token:
        return None
    return _extract_user_from_token(token, db)


def require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "teacher":
        raise AppError("FORBIDDEN", "Teacher role is required for this action.", status_code=403)
    return user


def require_csrf(request: Request, x_csrf_token: str | None = Header(default=None)) -> None:
    cookie_token = request.cookies.get("vg_csrf_token")
    if not verify_csrf_token(cookie_token, x_csrf_token):
        raise AppError("CSRF_FAILED", "CSRF validation failed.", status_code=403)
