from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.config import settings
from app.models.activation import Activation
from app.models.base import utcnow
from app.models.license import License, LicenseStatus
from app.models.product import Product
from app.schemas.stats import ProductDistribution, RevenueOut, RevenuePoint, SummaryOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=SummaryOut)
def summary(db: DbSession, _: CurrentUser):
    now = utcnow()

    total_active = (
        db.scalar(select(func.count(License.id)).where(License.status == LicenseStatus.active))
        or 0
    )

    soon = now + timedelta(days=settings.expiry_notify_days)
    expiring_soon = (
        db.scalar(
            select(func.count(License.id)).where(
                License.status == LicenseStatus.active,
                License.expires_at.is_not(None),
                License.expires_at > now,
                License.expires_at <= soon,
            )
        )
        or 0
    )

    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    issued_today = (
        db.scalar(select(func.count(License.id)).where(License.issued_at >= start_today))
        or 0
    )

    active_hwids = (
        db.scalar(
            select(func.count(func.distinct(Activation.hwid))).where(
                Activation.is_active.is_(True)
            )
        )
        or 0
    )

    rows = db.execute(
        select(Product.id, Product.code, Product.name, func.count(License.id))
        .join(License, License.product_id == Product.id)
        .where(License.status == LicenseStatus.active)
        .group_by(Product.id, Product.code, Product.name)
    ).all()
    by_product = [
        ProductDistribution(
            product_id=r[0], product_code=r[1], product_name=r[2], active_count=r[3]
        )
        for r in rows
    ]

    return SummaryOut(
        total_active=total_active,
        expiring_soon=expiring_soon,
        issued_today=issued_today,
        active_hwids=active_hwids,
        by_product=by_product,
    )


@router.get("/revenue", response_model=RevenueOut)
def revenue(db: DbSession, _: CurrentUser, granularity: str = "day", days: int = 30):
    """Issuance trend. Aggregated in Python for SQLite/PostgreSQL portability."""
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    now = utcnow()
    start = now - timedelta(days=days)
    licenses = db.scalars(select(License).where(License.issued_at >= start))

    counts: dict[str, int] = {}
    for lic in licenses:
        d = lic.issued_at
        if granularity == "month":
            key = d.strftime("%Y-%m")
        elif granularity == "week":
            iso = d.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
        else:
            key = d.strftime("%Y-%m-%d")
        counts[key] = counts.get(key, 0) + 1

    points = [RevenuePoint(period=k, count=v) for k, v in sorted(counts.items())]
    return RevenueOut(granularity=granularity, points=points)
