"""HMAC-SHA256 request signing for the bot verify endpoints.

signature = HMAC-SHA256(product.secret_key, "field1|field2|...")
"""
import hashlib
import hmac
import time


def build_signature(secret: str, parts: list[str]) -> str:
    message = "|".join(parts)
    return hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_signature(secret: str, parts: list[str], signature: str) -> bool:
    expected = build_signature(secret, parts)
    return hmac.compare_digest(expected, (signature or "").lower())


def is_timestamp_fresh(ts: int, tolerance_sec: int) -> bool:
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return False
    return abs(int(time.time()) - ts_int) <= tolerance_sec
