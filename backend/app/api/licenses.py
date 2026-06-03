import csv
import io
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, DbSession, client_ip
from app.core.errors import ApiError
from app.models.activation import Activation
from app.models.audit_log import AuditEventType, AuditLog
from app.models.license import License, LicenseStatus
from app.models.product import Product
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page
from app.schemas.license import (
    ActivationOut,
    BulkIssueResponse,
    ExtendRequest,
    IssueBulkRequest,
    IssueLicenseRequest,
    LicenseDetailOut,
    LicenseIssueResponse,
    LicenseOut,
    MemoUpdateRequest,
)
from app.services import audit, license_service
from fastapi import Request

router = APIRouter(prefix="/licenses", tags=["licenses"])


# ---- helpers ---------------------------------------------------------------

def _get_license_or_404(db: Session, license_id: int) -> License:
    lic = db.get(License, license_id)
    if lic is None:
        raise ApiError(404, "not_found", "라이선스를 찾을 수 없습니다.")
    return lic


def _get_active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise ApiError(404, "product_not_found", "유효한 제품을 찾을 수 없습니다.")
    return product


def _to_out(db: Session, lic: License, *, detail: bool = False) -> LicenseOut:
    data = dict(
        id=lic.id,
        key_prefix=lic.key_prefix,
        product_id=lic.product_id,
        product_code=lic.product.code if lic.product else None,
        plan_type=lic.plan_type,
        duration_days=lic.duration_days,
        issued_at=lic.issued_at,
        expires_at=lic.expires_at,
        status=lic.status,
        customer_name=lic.customer_name,
        customer_contact=lic.customer_contact,
        memo=lic.memo,
        hwid_used=license_service.active_hwid_count(db, lic.id),
        hwid_max=lic.effective_max_hwid,
        issued_by_user_id=lic.issued_by_user_id,
        created_at=lic.created_at,
        updated_at=lic.updated_at,
    )
    if detail:
        activations = [ActivationOut.model_validate(a) for a in lic.activations]
        return LicenseDetailOut(**data, activations=activations)
    return LicenseOut(**data)


def _issue_response(lic: License, raw_key: str) -> LicenseIssueResponse:
    return LicenseIssueResponse(
        license_id=lic.id,
        raw_key=raw_key,
        key_prefix=lic.key_prefix,
        product_id=lic.product_id,
        plan_type=lic.plan_type,
        expires_at=lic.expires_at,
    )


# ---- endpoints -------------------------------------------------------------

@router.get("", response_model=Page[LicenseOut])
def list_licenses(
    db: DbSession,
    _: CurrentUser,
    product_id: int | None = None,
    status: LicenseStatus | None = None,
    expires_before: datetime | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    stmt = select(License).options(selectinload(License.product))
    conds = []
    if product_id is not None:
        conds.append(License.product_id == product_id)
    if status is not None:
        conds.append(License.status == status)
    if expires_before is not None:
        conds.append(License.expires_at.is_not(None))
        conds.append(License.expires_at <= expires_before)
    if search:
        like = f"%{search}%"
        conds.append(
            or_(
                License.customer_name.ilike(like),
                License.customer_contact.ilike(like),
                License.memo.ilike(like),
                License.key_prefix.ilike(like),
            )
        )
    if conds:
        stmt = stmt.where(*conds)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(License.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[_to_out(db, lic) for lic in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/issue", response_model=LicenseIssueResponse, status_code=201)
def issue(payload: IssueLicenseRequest, db: DbSession, user: CurrentUser):
    product = _get_active_product(db, payload.product_id)
    lic, raw_key = license_service.issue_license(
        db,
        product=product,
        user=user,
        plan_type=payload.plan_type,
        duration_days=payload.duration_days,
        customer_name=payload.customer_name,
        customer_contact=payload.customer_contact,
        memo=payload.memo,
        max_hwid_count=payload.max_hwid_count,
    )
    db.commit()
    db.refresh(lic)
    return _issue_response(lic, raw_key)


@router.post("/issue-bulk", response_model=BulkIssueResponse)
def issue_bulk(
    payload: IssueBulkRequest,
    db: DbSession,
    user: CurrentUser,
    format: str = "json",
):
    product = _get_active_product(db, payload.product_id)
    issued: list[tuple[License, str]] = []
    for _ in range(payload.count):
        lic, raw_key = license_service.issue_license(
            db,
            product=product,
            user=user,
            plan_type=payload.plan_type,
            duration_days=payload.duration_days,
            customer_name=payload.customer_name,
            customer_contact=payload.customer_contact,
            memo=payload.memo,
            max_hwid_count=payload.max_hwid_count,
        )
        issued.append((lic, raw_key))
    db.commit()

    results = [_issue_response(lic, raw_key) for lic, raw_key in issued]

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["license_id", "product_code", "key", "plan_type", "expires_at"])
        for r in results:
            writer.writerow(
                [
                    r.license_id,
                    product.code,
                    r.raw_key,
                    r.plan_type.value,
                    r.expires_at.isoformat() if r.expires_at else "",
                ]
            )
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=licenses_{product.code}.csv"
            },
        )

    return BulkIssueResponse(count=len(results), keys=results)


@router.get("/{license_id}", response_model=LicenseDetailOut)
def get_license(license_id: int, db: DbSession, _: CurrentUser):
    lic = _get_license_or_404(db, license_id)
    license_service.refresh_expiry_status(db, lic)
    db.commit()
    return _to_out(db, lic, detail=True)


@router.get("/{license_id}/logs", response_model=list[AuditLogOut])
def license_logs(license_id: int, db: DbSession, _: CurrentUser, limit: int = 100):
    _get_license_or_404(db, license_id)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.license_id == license_id)
        .order_by(AuditLog.id.desc())
        .limit(min(limit, 500))
    )
    return list(rows)


@router.patch("/{license_id}", response_model=LicenseOut)
def update_license_memo(
    license_id: int, payload: MemoUpdateRequest, db: DbSession, _: CurrentUser
):
    lic = _get_license_or_404(db, license_id)
    lic.memo = payload.memo
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return _to_out(db, lic)


@router.post("/{license_id}/revoke", response_model=LicenseOut)
def revoke(license_id: int, db: DbSession, user: CurrentUser):
    lic = _get_license_or_404(db, license_id)
    license_service.revoke_license(db, lic, user)
    db.commit()
    db.refresh(lic)
    return _to_out(db, lic)


@router.post("/{license_id}/extend", response_model=LicenseOut)
def extend(license_id: int, payload: ExtendRequest, db: DbSession, user: CurrentUser):
    lic = _get_license_or_404(db, license_id)
    license_service.extend_license(db, lic, payload.days, user)
    db.commit()
    db.refresh(lic)
    return _to_out(db, lic)


@router.delete("/{license_id}/activations/{activation_id}")
def release_hwid(
    license_id: int,
    activation_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    """Release a registered HWID (e.g. reinstall case)."""
    activation = db.get(Activation, activation_id)
    if activation is None or activation.license_id != license_id:
        raise ApiError(404, "not_found", "활성화 기록을 찾을 수 없습니다.")
    hwid = activation.hwid
    db.delete(activation)
    audit.record(
        db,
        AuditEventType.hwid_release,
        license_id=license_id,
        user_id=user.id,
        hwid=hwid,
        ip_address=client_ip(request),
    )
    db.commit()
    return {"ok": True, "released_hwid": hwid}
