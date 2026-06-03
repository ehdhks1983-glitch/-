from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UtcDateTime, utcnow


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 2-letter key prefix (CW, CT, ...). Required by the license key format.
    prefix: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # HMAC secret shared with the bot client (admin-only visibility).
    secret_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_hwid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )

    licenses: Mapped[list["License"]] = relationship(  # noqa: F821
        back_populates="product"
    )
