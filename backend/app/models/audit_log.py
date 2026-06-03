import enum
from datetime import datetime

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UtcDateTime, utcnow


class AuditEventType(str, enum.Enum):
    issue = "issue"
    verify_success = "verify_success"
    verify_fail = "verify_fail"
    revoke = "revoke"
    extend = "extend"
    hwid_register = "hwid_register"
    hwid_conflict = "hwid_conflict"
    hwid_release = "hwid_release"
    login = "login"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[AuditEventType] = mapped_column(
        SAEnum(AuditEventType, name="audit_event_type"), nullable=False, index=True
    )
    license_id: Mapped[int | None] = mapped_column(
        ForeignKey("licenses.id"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    hwid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, index=True
    )
