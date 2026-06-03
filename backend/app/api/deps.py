"""Shared FastAPI dependencies: DB session, auth, role guards."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import ACCESS, decode_token
from app.database import get_db
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    if creds is None or not creds.credentials:
        raise ApiError(401, "unauthorized", "인증이 필요합니다.")
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        raise ApiError(401, "invalid_token", "유효하지 않거나 만료된 토큰입니다.")
    if payload.get("type") != ACCESS:
        raise ApiError(401, "invalid_token", "액세스 토큰이 아닙니다.")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "invalid_token", "토큰 정보가 올바르지 않습니다.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "inactive_user", "비활성화되었거나 존재하지 않는 계정입니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.admin:
        raise ApiError(403, "forbidden", "관리자 권한이 필요합니다.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
