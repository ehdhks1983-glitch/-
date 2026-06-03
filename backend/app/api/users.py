from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.core.errors import ApiError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _: AdminUser):
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: DbSession, _: AdminUser):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError(409, "email_exists", "이미 존재하는 이메일입니다.")
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: DbSession, admin: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "사용자를 찾을 수 없습니다.")
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise ApiError(400, "cannot_disable_self", "자기 자신은 비활성화할 수 없습니다.")
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
