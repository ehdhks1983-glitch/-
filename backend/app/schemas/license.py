from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.license import LicenseStatus, PlanType


class IssueLicenseRequest(BaseModel):
    product_id: int
    plan_type: PlanType
    duration_days: int | None = Field(default=None, ge=1, le=36500)
    customer_name: str | None = None
    customer_contact: str | None = None
    memo: str | None = None
    max_hwid_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_custom(self) -> "IssueLicenseRequest":
        if self.plan_type == PlanType.custom and not self.duration_days:
            raise ValueError("custom 플랜은 duration_days가 필요합니다.")
        return self


class IssueBulkRequest(IssueLicenseRequest):
    count: int = Field(ge=1, le=1000)


class ActivationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hwid: str
    activated_at: datetime
    last_seen_at: datetime
    ip_address: str | None
    client_version: str | None
    is_active: bool


class LicenseOut(BaseModel):
    id: int
    key_prefix: str
    product_id: int
    product_code: str | None = None
    plan_type: PlanType
    duration_days: int | None
    issued_at: datetime
    expires_at: datetime | None
    status: LicenseStatus
    customer_name: str | None
    customer_contact: str | None
    memo: str | None
    hwid_used: int
    hwid_max: int
    issued_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class LicenseDetailOut(LicenseOut):
    activations: list[ActivationOut] = []


class LicenseIssueResponse(BaseModel):
    license_id: int
    raw_key: str
    key_prefix: str
    product_id: int
    plan_type: PlanType
    expires_at: datetime | None


class BulkIssueResponse(BaseModel):
    count: int
    keys: list[LicenseIssueResponse]


class ExtendRequest(BaseModel):
    days: int = Field(ge=1, le=36500)


class MemoUpdateRequest(BaseModel):
    memo: str | None = None
