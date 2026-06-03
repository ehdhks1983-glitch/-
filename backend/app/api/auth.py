from fastapi import APIRouter, Request
from jose import JWTError
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, client_ip
from app.core.errors import ApiError
from app.core.security import (
    REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.audit_log import AuditEventType
from app.models.base import utcnow
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.user import UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DbSession):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise ApiError(
            401, "invalid_credentials", "이메일 또는 비밀번호가 올바르지 않습니다."
        )
    if not user.is_active:
        raise ApiError(403, "inactive_user", "비활성화된 계정입니다.")
    user.last_login_at = utcnow()
    audit.record(db, AuditEventType.login, user_id=user.id, ip_address=client_ip(request))
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest, db: DbSession):
    try:
        data = decode_token(payload.refresh_token)
    except JWTError:
        raise ApiError(401, "invalid_token", "유효하지 않거나 만료된 토큰입니다.")
    if data.get("type") != REFRESH:
        raise ApiError(401, "invalid_token", "리프레시 토큰이 아닙니다.")
    try:
        user_id = int(data["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "invalid_token", "토큰 정보가 올바르지 않습니다.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "inactive_user", "계정을 찾을 수 없습니다.")
    return AccessTokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser):
    return current
