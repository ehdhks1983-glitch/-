"""Create/ensure the initial admin account from SEED_ADMIN_* settings.

Usage:
    python -m app.scripts.seed_admin
"""
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User, UserRole


def main() -> None:
    db = SessionLocal()
    try:
        email = settings.seed_admin_email.lower()
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            print(f"[seed] admin already exists: {email}")
            return
        user = User(
            email=email,
            hashed_password=hash_password(settings.seed_admin_password),
            name=settings.seed_admin_name,
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"[seed] created admin account: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
