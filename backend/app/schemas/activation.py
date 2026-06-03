from datetime import datetime

from pydantic import BaseModel


class ActivationListItem(BaseModel):
    id: int
    license_id: int
    license_key_prefix: str
    product_id: int
    product_code: str | None
    hwid: str
    activated_at: datetime
    last_seen_at: datetime
    ip_address: str | None
    client_version: str | None
    is_active: bool
    is_conflict: bool
