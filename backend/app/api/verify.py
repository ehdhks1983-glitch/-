"""Public bot-client verification API (HMAC authenticated)."""
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, client_ip
from app.config import settings
from app.core.errors import ApiError
from app.core.hmac_verify import is_timestamp_fresh, verify_signature
from app.core.key_generator import hash_license_key
from app.models.activation import Activation
from app.models.audit_log import AuditEventType
from app.models.base import utcnow
from app.models.license import License, LicenseStatus
from app.models.product import Product
from app.schemas.verify import (
    ActivateRequest,
    ActivateResponse,
    CheckRequest,
    CheckResponse,
)
from app.services import audit, license_service

router = APIRouter(prefix="/verify", tags=["verify"])


def _get_product_or_fail(db: Session, product_code: str) -> Product:
    product = db.scalar(
        select(Product).where(
            Product.code == product_code, Product.is_active.is_(True)
        )
    )
    if product is None:
        raise ApiError(404, "product_not_found", "알 수 없는 제품입니다.")
    return product


def _authenticate(product: Product, parts: list[str], signature: str, timestamp: int) -> None:
    if not is_timestamp_fresh(timestamp, settings.verify_timestamp_tolerance_sec):
        raise ApiError(401, "stale_timestamp", "요청 타임스탬프가 유효 범위를 벗어났습니다.")
    if not verify_signature(product.secret_key, parts, signature):
        raise ApiError(401, "invalid_signature", "서명 검증에 실패했습니다.")


def _find_license(db: Session, license_key: str, product: Product) -> License | None:
    lic = db.scalar(
        select(License).where(License.key_hash == hash_license_key(license_key))
    )
    if lic is None or lic.product_id != product.id:
        return None
    return lic


@router.post("/activate", response_model=ActivateResponse)
def activate(payload: ActivateRequest, request: Request, db: DbSession):
    ip = client_ip(request)
    product = _get_product_or_fail(db, payload.product_code)
    _authenticate(
        product,
        [payload.license_key, payload.hwid, str(payload.timestamp)],
        payload.signature,
        payload.timestamp,
    )

    lic = _find_license(db, payload.license_key, product)
    if lic is None:
        audit.record(
            db,
            AuditEventType.verify_fail,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"reason": "not_found", "product_code": payload.product_code},
        )
        db.commit()
        return ActivateResponse(valid=False, reason="라이선스 키를 찾을 수 없습니다.")

    license_service.refresh_expiry_status(db, lic)
    if lic.status != LicenseStatus.active:
        audit.record(
            db,
            AuditEventType.verify_fail,
            license_id=lic.id,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"reason": lic.status.value},
        )
        db.commit()
        return ActivateResponse(valid=False, reason=f"라이선스 상태: {lic.status.value}")

    # Detect the same HWID bound to a different license (informational).
    conflict = db.scalar(
        select(Activation).where(
            Activation.hwid == payload.hwid,
            Activation.license_id != lic.id,
            Activation.is_active.is_(True),
        )
    )
    if conflict is not None:
        audit.record(
            db,
            AuditEventType.hwid_conflict,
            license_id=lic.id,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"other_license_id": conflict.license_id},
        )

    existing = db.scalar(
        select(Activation).where(
            Activation.license_id == lic.id, Activation.hwid == payload.hwid
        )
    )
    if existing is None:
        used = license_service.active_hwid_count(db, lic.id)
        if used >= lic.effective_max_hwid:
            audit.record(
                db,
                AuditEventType.verify_fail,
                license_id=lic.id,
                hwid=payload.hwid,
                ip_address=ip,
                detail={"reason": "hwid_limit", "used": used, "max": lic.effective_max_hwid},
            )
            db.commit()
            return ActivateResponse(
                valid=False, reason="등록 가능한 기기 수를 초과했습니다."
            )
        db.add(
            Activation(
                license_id=lic.id,
                hwid=payload.hwid,
                ip_address=ip,
                client_version=payload.client_version,
            )
        )
        audit.record(
            db,
            AuditEventType.hwid_register,
            license_id=lic.id,
            hwid=payload.hwid,
            ip_address=ip,
        )
    else:
        existing.last_seen_at = utcnow()
        existing.is_active = True
        if payload.client_version:
            existing.client_version = payload.client_version
        if ip:
            existing.ip_address = ip
        db.add(existing)

    audit.record(
        db,
        AuditEventType.verify_success,
        license_id=lic.id,
        hwid=payload.hwid,
        ip_address=ip,
    )
    db.commit()
    db.refresh(lic)
    return ActivateResponse(
        valid=True,
        expires_at=lic.expires_at,
        plan_type=lic.plan_type,
        max_hwid_count=lic.effective_max_hwid,
        days_remaining=license_service.days_remaining(lic),
    )


@router.post("/check", response_model=CheckResponse)
def check(payload: CheckRequest, request: Request, db: DbSession):
    ip = client_ip(request)
    product = _get_product_or_fail(db, payload.product_code)
    _authenticate(
        product,
        [payload.license_key, payload.hwid, str(payload.timestamp)],
        payload.signature,
        payload.timestamp,
    )

    lic = _find_license(db, payload.license_key, product)
    if lic is None:
        audit.record(
            db,
            AuditEventType.verify_fail,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"reason": "not_found"},
        )
        db.commit()
        return CheckResponse(valid=False, reason="라이선스 키를 찾을 수 없습니다.")

    license_service.refresh_expiry_status(db, lic)
    if lic.status != LicenseStatus.active:
        audit.record(
            db,
            AuditEventType.verify_fail,
            license_id=lic.id,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"reason": lic.status.value},
        )
        db.commit()
        return CheckResponse(
            valid=False,
            reason=f"라이선스 상태: {lic.status.value}",
            status=lic.status,
            expires_at=lic.expires_at,
            days_remaining=license_service.days_remaining(lic),
        )

    activation = db.scalar(
        select(Activation).where(
            Activation.license_id == lic.id,
            Activation.hwid == payload.hwid,
            Activation.is_active.is_(True),
        )
    )
    if activation is None:
        audit.record(
            db,
            AuditEventType.verify_fail,
            license_id=lic.id,
            hwid=payload.hwid,
            ip_address=ip,
            detail={"reason": "hwid_not_registered"},
        )
        db.commit()
        return CheckResponse(
            valid=False,
            reason="등록되지 않은 기기입니다. 재활성화가 필요합니다.",
            status=lic.status,
            expires_at=lic.expires_at,
        )

    activation.last_seen_at = utcnow()
    db.add(activation)
    audit.record(
        db,
        AuditEventType.verify_success,
        license_id=lic.id,
        hwid=payload.hwid,
        ip_address=ip,
    )
    db.commit()
    db.refresh(lic)
    return CheckResponse(
        valid=True,
        status=lic.status,
        expires_at=lic.expires_at,
        days_remaining=license_service.days_remaining(lic),
    )
