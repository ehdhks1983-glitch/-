"""Local cache for offline grace periods."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional


def _cache_dir() -> Path:
    base = os.environ.get("CENTUMHI_CACHE_DIR")
    directory = Path(base) if base else Path.home() / ".centumhi"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cache_file(product_code: str, license_key: str) -> Path:
    digest = hashlib.sha256(f"{product_code}:{license_key}".encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest[:16]}.json"


def load(product_code: str, license_key: str) -> Optional[dict]:
    path = _cache_file(product_code, license_key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save(product_code: str, license_key: str, data: dict) -> None:
    payload = dict(data)
    payload["_cached_at"] = int(time.time())
    try:
        _cache_file(product_code, license_key).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    except Exception:
        # caching is best-effort; never break the bot over a cache write
        pass
