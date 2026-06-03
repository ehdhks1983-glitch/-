"""Core license business logic: issuing, revoking, extending, expiry."""
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.key_generator import generate_license_key, hash_license_key, key_prefix
from app.models.activation import Activation
from app.models.audit_log import AuditEventType
from app.models.base import utcnow
from app.models.license import License, LicenseStatus, PlanType
from app.models.product import Product
from app.models.user import User
from app.services import audit

PLAN_FIXED_DAYS: dict[PlanType, int] = {
    PlanType.trial_7: 7,
    PlanType.monthly_30: 30,
}


def resolve_duration_days(plan_type: PlanType, duration_days: int | None) -> int | None:
    if plan_type in PLAN_FIXED_DAYS:
        return PLAN_FIXED_DAYS[plan_type]
    if plan_type == PlanType.unlimited:
        return None
    return duration_days  # custom


def compute_expiry(issued_at: datetime, eff_days: int | None) -> datetime | None:
    return issued_at + timedelta(days=eff_days) if eff_days else None


def days_remaining(lic: License) -> int | None:
    if lic.expires_at is None:
        return None
    seconds = (lic.expires_at - utcnow()).total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)


def active_hwid_count(db: Session, license_id: int) -> int:
    return (
        db.scalar(
            select(func.count(Activation.id)).where(
                Activation.license_id == license_id,
                Activation.is_active.is_(True),
            )
        )
        or 0
    )


def _generate_unique_key(
    db: Session, prefix: str, plan_value: str, eff_days: int | None
) -> tuple[str, str, str]:
    for _ in range(6):
        raw = generate_license_key(prefix, plan_value, eff_days)
        key_hash = hash_license_key(raw)
        if not db.scalar(select(License.id).where(License.key_hash == key_hash)):
            return raw, key_hash, key_prefix(raw)
    raise ApiError(
        500, "key_generation_failed", "키 생성에 실패했습니다. 다시 시도해 주세요."
    )


def issue_license(
    db: Session,
    *,
    product: Product,
    user: User | None,
    plan_type: PlanType,
    duration_days: int | None = None,
    customer_name: str | None = None,
    customer_contact: str | None = None,
    memo: str | None = None,
    max_hwid_count: int | None = None,
) -> tuple[License, str]:
    eff_days = resolve_duration_days(plan_type, duration_days)
    issued_at = utcnow()
    raw_key, key_hash, prefix = _generate_unique_key(
        db, product.prefix, plan_type.value, eff_days
    )
    lic = License(
        key_hash=key_hash,
        key_prefix=prefix,
        product_id=product.id,
        plan_type=plan_type,
        duration_days=eff_days,
        issued_at=issued_at,
        expires_at=compute_expiry(issued_at, eff_days),
        status=LicenseStatus.active,
        issued_by_user_id=user.id if user else None,
        customer_name=customer_name,
        customer_contact=customer_contact,
        memo=memo,
        max_hwid_count=max_hwid_count,
    )
    db.add(lic)
    db.flush()
    audit.record(
        db,
        AuditEventType.issue,
        license_id=lic.id,
        user_id=user.id if user else None,
        detail={"plan_type": plan_type.value, "product_code": product.code},
    )
    return lic, raw_key


def revoke_license(db: Session, lic: License, user: User | None = None) -> License:
    if lic.status != LicenseStatus.revoked:
        lic.status = LicenseStatus.revoked
        db.add(lic)
        audit.record(
            db,
            AuditEventType.revoke,
            license_id=lic.id,
            user_id=user.id if user else None,
        )
    return lic


def extend_license(
    db: Session, lic: License, days: int, user: User | None = None
) -> License:
    if lic.plan_type == PlanType.unlimited or lic.expires_at is None:
        raise ApiError(
            400, "cannot_extend_unlimited", "무제한 라이선스는 연장할 수 없습니다."
        )
    if lic.status == LicenseStatus.revoked:
        raise ApiError(400, "cannot_extend_revoked", "취소된 라이선스는 연장할 수 없습니다.")
    now = utcnow()
    base = lic.expires_at if lic.expires_at > now else now
    lic.expires_at = base + timedelta(days=days)
    if lic.status == LicenseStatus.expired and lic.expires_at > now:
        lic.status = LicenseStatus.active
    db.add(lic)
    audit.record(
        db,
        AuditEventType.extend,
        license_id=lic.id,
        user_id=user.id if user else None,
        detail={"days": days, "new_expires_at": lic.expires_at.isoformat()},
    )
    return lic


def refresh_expiry_status(db: Session, lic: License) -> License:
    """Lazily flip an active-but-past-expiry license to ``expired``."""
    if (
        lic.status == LicenseStatus.active
        and lic.expires_at is not None
        and lic.expires_at <= utcnow()
    ):
        lic.status = LicenseStatus.expired
        db.add(lic)
    return lic
