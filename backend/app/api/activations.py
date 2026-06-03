from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.activation import Activation
from app.models.license import License
from app.models.product import Product
from app.schemas.activation import ActivationListItem
from app.schemas.common import Page

router = APIRouter(prefix="/activations", tags=["activations"])


@router.get("", response_model=Page[ActivationListItem])
def list_activations(
    db: DbSession,
    _: CurrentUser,
    conflicts_only: bool = False,
    page: int = 1,
    page_size: int = 50,
):
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    # HWIDs active on more than one distinct license = conflict.
    conflict_hwids = {
        row[0]
        for row in db.execute(
            select(Activation.hwid)
            .where(Activation.is_active.is_(True))
            .group_by(Activation.hwid)
            .having(func.count(func.distinct(Activation.license_id)) > 1)
        ).all()
    }

    stmt = (
        select(Activation, License, Product)
        .join(License, Activation.license_id == License.id)
        .join(Product, License.product_id == Product.id)
    )
    if conflicts_only:
        if not conflict_hwids:
            return Page(items=[], total=0, page=page, page_size=page_size)
        stmt = stmt.where(Activation.hwid.in_(conflict_hwids))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Activation.last_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        ActivationListItem(
            id=a.id,
            license_id=a.license_id,
            license_key_prefix=lic.key_prefix,
            product_id=p.id,
            product_code=p.code,
            hwid=a.hwid,
            activated_at=a.activated_at,
            last_seen_at=a.last_seen_at,
            ip_address=a.ip_address,
            client_version=a.client_version,
            is_active=a.is_active,
            is_conflict=a.hwid in conflict_hwids,
        )
        for (a, lic, p) in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
