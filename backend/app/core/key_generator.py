"""License key generation, checksum, and hashing.

Format: ``{PREFIX}-{PLAN}-{RANDOM_8}-{RANDOM_8}-{CHECKSUM_4}``
  - PREFIX   : per-product 2 letters (CW, CT, CC, CM, CB ...)
  - PLAN     : T07 (7d), M30 (30d), U00 (unlimited), C{days} (custom)
  - RANDOM_8 : two blocks of 8 unambiguous chars (secrets backed)
  - CHECKSUM : 4 chars derived from CRC32 of the body

Only the SHA-256 hash + a short prefix are stored in the DB; the raw key is
returned exactly once at issue time.
"""
import hashlib
import secrets
import zlib

# Unambiguous uppercase alphabet (no I, L, O, 0, 1) for human-typeable keys.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

PLAN_CODES: dict[str, str] = {
    "trial_7": "T07",
    "monthly_30": "M30",
    "unlimited": "U00",
}

PREFIX_LEN = 12  # number of leading chars stored as key_prefix for lookup


def plan_code(plan_type: str, duration_days: int | None) -> str:
    """Map a plan type to its short code. ``custom`` becomes ``C{days}``."""
    if plan_type in PLAN_CODES:
        return PLAN_CODES[plan_type]
    days = duration_days or 0
    return f"C{days:02d}"


def _rand_block(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _checksum(body: str, length: int = 4) -> str:
    crc = zlib.crc32(body.encode("utf-8")) & 0xFFFFFFFF
    out: list[str] = []
    base = len(ALPHABET)
    for _ in range(length):
        out.append(ALPHABET[crc % base])
        crc //= base
    return "".join(out)


def generate_license_key(
    product_prefix: str, plan_type: str, duration_days: int | None
) -> str:
    body = (
        f"{product_prefix.upper()}-{plan_code(plan_type, duration_days)}-"
        f"{_rand_block()}-{_rand_block()}"
    )
    return f"{body}-{_checksum(body)}"


def verify_checksum(key: str) -> bool:
    """Validate the trailing checksum of a license key (cheap pre-check)."""
    body, _, checksum = key.rpartition("-")
    if not body or not checksum:
        return False
    return _checksum(body) == checksum


def key_prefix(raw_key: str) -> str:
    return raw_key[:PREFIX_LEN]


def hash_license_key(raw_key: str) -> str:
    """SHA-256 hex digest stored in the DB (keys are never stored in plaintext)."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()
