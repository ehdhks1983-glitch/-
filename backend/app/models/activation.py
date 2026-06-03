from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UtcDateTime, utcnow


class Activation(Base):
    __tablename__ = "activations"
    __table_args__ = (
        UniqueConstraint("license_id", "hwid", name="uq_activation_license_hwid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id"), nullable=False, index=True
    )
    hwid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    activated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    client_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    license: Mapped["License"] = relationship(back_populates="activations")  # noqa: F821
