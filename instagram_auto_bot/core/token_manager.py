"""Access-token lifetime tracking + long-lived token refresh (spec Stage 5/#3).

Long-lived IG tokens last ~60 days.  This tracks obtained/expiry timestamps in
the settings store, reports when a refresh is due, and performs the refresh via
the Instagram Graph ``refresh_access_token`` endpoint.  Session + clock are
injectable for offline testing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple

import requests

import config
from core.logging_setup import get_logger
from core.settings_store import SettingsStore

log = get_logger("token")

_ISO = "%Y-%m-%dT%H:%M:%S"


class TokenManager:
    def __init__(self, store: SettingsStore, *, session=None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.store = store
        self.session = session or requests
        self._clock = clock or datetime.now

    # -- timestamps ------------------------------------------------------- #
    @staticmethod
    def _parse(ts: str) -> Optional[datetime]:
        if not ts:
            return None
        try:
            return datetime.strptime(ts, _ISO)
        except ValueError:
            return None

    def expires_at(self) -> Optional[datetime]:
        return self._parse(self.store.get_str("ig_token_expires_at"))

    def days_until_expiry(self) -> Optional[float]:
        exp = self.expires_at()
        if exp is None:
            return None
        return (exp - self._clock()).total_seconds() / 86400.0

    def needs_refresh(self, within_days: Optional[int] = None) -> bool:
        """True when expiry is unknown-but-token-present, or within the window."""
        if not self.store.get_str("ig_access_token"):
            return False
        days = self.days_until_expiry()
        if days is None:
            return True  # have a token but no expiry recorded -> establish one
        within = config.TOKEN_REFRESH_BEFORE_DAYS if within_days is None else within_days
        return days <= within

    def is_expired(self) -> bool:
        days = self.days_until_expiry()
        return days is not None and days <= 0

    # -- mutation --------------------------------------------------------- #
    def set_token(self, token: str, lifetime_days: float = config.TOKEN_LIFETIME_DAYS,
                  *, persist: bool = True) -> None:
        now = self._clock()
        self.store.set("ig_access_token", token)
        self.store.set("ig_token_obtained_at", now.strftime(_ISO))
        self.store.set("ig_token_expires_at", (now + timedelta(days=lifetime_days)).strftime(_ISO))
        if persist:
            self.store.save()
        log.info("토큰 갱신 기록: 만료 예정 %.0f일 후", lifetime_days)

    # -- refresh ---------------------------------------------------------- #
    def refresh(self, *, persist: bool = True) -> bool:
        """Refresh the long-lived token. Returns True on success."""
        token = self.store.get_str("ig_access_token")
        if not token:
            log.warning("갱신할 토큰이 없습니다.")
            return False
        url = f"{config.INSTAGRAM_GRAPH_URL}/{config.TOKEN_REFRESH_PATH}"
        try:
            resp = self.session.get(
                url,
                params={"grant_type": "ig_refresh_token", "access_token": token},
                timeout=config.HTTP_TIMEOUT_SEC,
            )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.error("토큰 갱신 요청 실패: %s", exc)
            return False

        new_token = data.get("access_token")
        if not new_token:
            log.error("토큰 갱신 응답에 access_token이 없습니다: %s", data)
            return False
        expires_in = data.get("expires_in")
        lifetime = (expires_in / 86400.0) if expires_in else config.TOKEN_LIFETIME_DAYS
        self.set_token(new_token, lifetime_days=lifetime, persist=persist)
        return True

    def status_summary(self) -> Tuple[bool, Optional[float]]:
        """(has_token, days_until_expiry) for UI display."""
        return bool(self.store.get_str("ig_access_token")), self.days_until_expiry()
