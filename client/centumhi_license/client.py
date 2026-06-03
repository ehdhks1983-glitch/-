"""High-level license client used by bot products."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

import requests

from . import cache
from .errors import NetworkError
from .hwid import get_hwid
from .models import VerifyResult


class LicenseClient:
    def __init__(
        self,
        product_code: str,
        product_secret: str,
        server_url: str,
        *,
        hwid: Optional[str] = None,
        client_version: str = "1.0.0",
        timeout: float = 10.0,
        retries: int = 3,
        offline_grace_days: int = 7,
    ) -> None:
        self.product_code = product_code
        self.product_secret = product_secret
        self.server_url = server_url.rstrip("/")
        self.hwid = hwid or get_hwid()
        self.client_version = client_version
        self.timeout = timeout
        self.retries = max(1, retries)
        self.offline_grace_seconds = offline_grace_days * 86400

    # ---- internals --------------------------------------------------------

    def _sign(self, *parts: str) -> str:
        message = "|".join(parts).encode("utf-8")
        return hmac.new(
            self.product_secret.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

    def _post(self, path: str, body: dict) -> dict:
        url = "{base}{path}".format(base=self.server_url, path=path)
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                resp = requests.post(url, json=body, timeout=self.timeout)
                return resp.json() if resp.content else {}
            except requests.RequestException as exc:  # connection/timeout/etc.
                last_exc = exc
                if attempt < self.retries - 1:
                    time.sleep(min(2 ** attempt, 4))
        raise NetworkError(str(last_exc))

    @staticmethod
    def _to_result(data: dict, *, offline: bool = False) -> VerifyResult:
        if "valid" in data:
            return VerifyResult(
                valid=bool(data["valid"]),
                reason=data.get("reason"),
                status=data.get("status"),
                plan_type=data.get("plan_type"),
                expires_at=data.get("expires_at"),
                days_remaining=data.get("days_remaining"),
                max_hwid_count=data.get("max_hwid_count"),
                offline=offline,
            )
        # unified error envelope: { error_code, message, detail? }
        return VerifyResult(
            valid=False,
            reason=data.get("message") or data.get("error_code") or "unknown error",
            offline=offline,
        )

    def _offline_fallback(self, license_key: str) -> VerifyResult:
        cached = cache.load(self.product_code, license_key)
        if cached and cached.get("valid"):
            age = time.time() - cached.get("_cached_at", 0)
            if age <= self.offline_grace_seconds:
                result = self._to_result(cached, offline=True)
                result.reason = "오프라인 그레이스 기간"
                return result
        return VerifyResult(
            valid=False, reason="네트워크 오류 및 오프라인 캐시 만료", offline=True
        )

    def _cache_if_valid(self, license_key: str, data: dict) -> None:
        if data.get("valid"):
            cache.save(self.product_code, license_key, data)

    # ---- public API -------------------------------------------------------

    def activate(self, license_key: str) -> VerifyResult:
        """Register this HWID and validate the key (first run)."""
        license_key = license_key.strip()
        ts = int(time.time())
        body = {
            "license_key": license_key,
            "hwid": self.hwid,
            "product_code": self.product_code,
            "client_version": self.client_version,
            "timestamp": ts,
            "signature": self._sign(license_key, self.hwid, str(ts)),
        }
        try:
            data = self._post("/api/verify/activate", body)
        except NetworkError:
            return self._offline_fallback(license_key)
        self._cache_if_valid(license_key, data)
        return self._to_result(data)

    def check(self, license_key: str) -> VerifyResult:
        """Periodic re-check while the bot is running."""
        license_key = license_key.strip()
        ts = int(time.time())
        body = {
            "license_key": license_key,
            "hwid": self.hwid,
            "product_code": self.product_code,
            "timestamp": ts,
            "signature": self._sign(license_key, self.hwid, str(ts)),
        }
        try:
            data = self._post("/api/verify/check", body)
        except NetworkError:
            return self._offline_fallback(license_key)
        self._cache_if_valid(license_key, data)
        return self._to_result(data)

    def verify_or_activate(self, user_input_key: str) -> VerifyResult:
        """Convenience entrypoint for bot startup (activate is idempotent)."""
        return self.activate(user_input_key)
