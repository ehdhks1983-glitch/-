"""Audit log helper. Adds a row to the session; the caller commits."""
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType, AuditLog


def record(
    db: Session,
    event_type: AuditEventType,
    *,
    license_id: int | None = None,
    user_id: int | None = None,
    hwid: str | None = None,
    ip_address: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        event_type=event_type,
        license_id=license_id,
        user_id=user_id,
        hwid=hwid,
        ip_address=ip_address,
        detail=detail,
    )
    db.add(log)
    return log
