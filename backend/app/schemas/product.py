from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    prefix: str = Field(min_length=2, max_length=4)
    description: str | None = None
    max_hwid_count: int = Field(default=1, ge=1)

    @field_validator("prefix")
    @classmethod
    def upper_prefix(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("code")
    @classmethod
    def lower_code(cls, v: str) -> str:
        return v.strip().lower()


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    max_hwid_count: int | None = Field(default=None, ge=1)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    prefix: str
    description: str | None
    is_active: bool
    max_hwid_count: int
    created_at: datetime


class ProductSecretOut(ProductOut):
    """Includes the HMAC secret — admin-only, single-product responses."""

    secret_key: str
