from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditEventType


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: AuditEventType
    user_id: int | None
    hwid: str | None
    ip_address: str | None
    detail: dict[str, Any] | None
    created_at: datetime
