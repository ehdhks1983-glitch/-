from datetime import datetime

from pydantic import BaseModel

from app.models.license import LicenseStatus, PlanType


class ActivateRequest(BaseModel):
    license_key: str
    hwid: str
    product_code: str
    client_version: str | None = None
    timestamp: int
    signature: str


class ActivateResponse(BaseModel):
    valid: bool
    reason: str | None = None
    expires_at: datetime | None = None
    plan_type: PlanType | None = None
    max_hwid_count: int | None = None
    days_remaining: int | None = None


class CheckRequest(BaseModel):
    license_key: str
    hwid: str
    product_code: str
    timestamp: int
    signature: str


class CheckResponse(BaseModel):
    valid: bool
    reason: str | None = None
    status: LicenseStatus | None = None
    expires_at: datetime | None = None
    days_remaining: int | None = None
