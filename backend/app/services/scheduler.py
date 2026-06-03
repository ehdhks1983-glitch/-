"""APScheduler job: daily expiry sweep + expiring-soon notifications."""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.base import utcnow
from app.models.license import License, LicenseStatus
from app.services import notification_service

logger = logging.getLogger("centumhi.scheduler")

_scheduler: BackgroundScheduler | None = None


def expire_and_notify_job() -> None:
    db = SessionLocal()
    try:
        now = utcnow()

        expired = list(
            db.scalars(
                select(License).where(
                    License.status == LicenseStatus.active,
                    License.expires_at.is_not(None),
                    License.expires_at <= now,
                )
            )
        )
        for lic in expired:
            lic.status = LicenseStatus.expired
            db.add(lic)

        soon = now + timedelta(days=settings.expiry_notify_days)
        expiring = list(
            db.scalars(
                select(License).where(
                    License.status == LicenseStatus.active,
                    License.expires_at.is_not(None),
                    License.expires_at > now,
                    License.expires_at <= soon,
                )
            )
        )
        for lic in expiring:
            notification_service.notify_expiring(lic, (lic.expires_at - now).days)

        db.commit()
        logger.info(
            "expiry job: %d expired, %d expiring-soon notified",
            len(expired),
            len(expiring),
        )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("expiry job failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        expire_and_notify_job,
        trigger="cron",
        hour=3,
        minute=0,
        id="expire_and_notify",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("scheduler started (daily expiry sweep @ 03:00 UTC)")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
