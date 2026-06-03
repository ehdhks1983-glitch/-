"""Notification service.

Phase 1 ships a logging stub. Phase 3 will wire this to the existing Kakao
Flask skill server / email provider behind the same interface.
"""
import logging

from app.models.license import License

logger = logging.getLogger("centumhi.notifications")


def send_kakao(contact: str, message: str) -> bool:
    logger.info("[KAKAO stub] to=%s | %s", contact, message)
    return True


def send_email(to: str, subject: str, body: str) -> bool:
    logger.info("[EMAIL stub] to=%s | %s", to, subject)
    return True


def notify_expiring(lic: License, days_left: int) -> None:
    contact = lic.customer_contact or "(연락처 없음)"
    name = lic.customer_name or "고객"
    send_kakao(
        contact,
        f"[센텀하이] {name}님, 라이선스({lic.key_prefix}…)가 {days_left}일 후 만료됩니다.",
    )
