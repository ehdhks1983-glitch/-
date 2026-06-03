import enum
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UtcDateTime, utcnow


class PlanType(str, enum.Enum):
    trial_7 = "trial_7"
    monthly_30 = "monthly_30"
    unlimited = "unlimited"
    custom = "custom"


class LicenseStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    plan_type: Mapped[PlanType] = mapped_column(
        SAEnum(PlanType, name="plan_type"), nullable=False
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    status: Mapped[LicenseStatus] = mapped_column(
        SAEnum(LicenseStatus, name="license_status"),
        nullable=False,
        default=LicenseStatus.active,
    )
    issued_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Overrides product.max_hwid_count when set.
    max_hwid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    product: Mapped["Product"] = relationship(back_populates="licenses")  # noqa: F821
    activations: Mapped[list["Activation"]] = relationship(  # noqa: F821
        back_populates="license", cascade="all, delete-orphan"
    )
    issued_by: Mapped["User | None"] = relationship()  # noqa: F821

    @property
    def effective_max_hwid(self) -> int:
        if self.max_hwid_count is not None:
            return self.max_hwid_count
        return self.product.max_hwid_count if self.product else 1
