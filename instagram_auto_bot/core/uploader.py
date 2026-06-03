"""Public-URL image/video hosting abstraction (spec Stage 4 - never skip).

Meta's Graph API cannot accept local files; it fetches a *public* URL.  This
module uploads a local file to a host (Cloudinary by default, ImgBB fallback),
then verifies the resulting URL is actually reachable over HTTP - pre-empting
Meta error 9004 (media URL unreachable).

The orchestration (retry -> verify -> fallback) is Tk/SDK-free and unit-tested
with injected fake providers + verifier.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

import requests

import config
from core.logging_setup import get_logger

log = get_logger("uploader")


class UploadError(Exception):
    """Raised when a file could not be hosted at a verified public URL."""


class HostProvider(ABC):
    """Uploads a local file and returns a public URL."""

    name: str = "base"

    @abstractmethod
    def upload(self, file_path: str) -> str:
        raise NotImplementedError


def get_host_provider(name: str, store) -> HostProvider:
    key = (name or config.HOST_PROVIDER).lower()
    if key == "cloudinary":
        from providers.host_cloudinary import CloudinaryHost
        return CloudinaryHost(store)
    if key == "imgbb":
        from providers.host_imgbb import ImgbbHost
        return ImgbbHost(store)
    raise ValueError(f"알 수 없는 호스트 프로바이더: {name!r}")


def verify_public_url(url: str, timeout: int = config.HTTP_TIMEOUT_SEC) -> bool:
    """True if ``url`` responds 200 (HEAD, falling back to a ranged GET)."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return True
        # Some CDNs don't implement HEAD - try a tiny GET.
        r = requests.get(url, timeout=timeout, stream=True,
                         headers={"Range": "bytes=0-0"})
        return r.status_code in (200, 206)
    except requests.RequestException as exc:
        log.warning("URL 접근성 검증 실패: %s (%s)", url, exc)
        return False


class Uploader:
    """Tries the primary host (with retries + verification), then the fallback."""

    def __init__(
        self,
        store,
        *,
        primary: Optional[HostProvider] = None,
        fallback: Optional[HostProvider] = None,
        verifier: Optional[Callable[[str], bool]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        retries: Optional[int] = None,
    ) -> None:
        self.store = store
        self._primary = primary
        self._fallback = fallback
        self._fallback_set = fallback is not None
        self.verify = verifier or verify_public_url
        self._sleep = sleep or time.sleep
        self.retries = config.RETRY_COUNT if retries is None else retries

    # Resolve providers lazily so construction never needs SDKs/creds.
    @property
    def primary(self) -> HostProvider:
        if self._primary is None:
            self._primary = get_host_provider(self.store.get_str("host_provider"), self.store)
        return self._primary

    @property
    def fallback(self) -> Optional[HostProvider]:
        if not self._fallback_set:
            # Default fallback is ImgBB, but only if it isn't already primary.
            if (self.store.get_str("host_provider") or config.HOST_PROVIDER).lower() != "imgbb":
                try:
                    self._fallback = get_host_provider("imgbb", self.store)
                except Exception:  # pragma: no cover - defensive
                    self._fallback = None
            self._fallback_set = True
        return self._fallback

    def upload(self, file_path: str) -> str:
        """Return a verified public URL or raise :class:`UploadError`."""
        providers: List[HostProvider] = [self.primary]
        fb = self.fallback
        if fb is not None and fb is not self.primary:
            providers.append(fb)

        last_error = "unknown"
        for provider in providers:
            for attempt in range(1, self.retries + 1):
                try:
                    url = provider.upload(file_path)
                    if url and self.verify(url):
                        log.info("업로드 성공(%s): %s", provider.name, url)
                        return url
                    last_error = f"{provider.name}: URL 접근 불가"
                    log.warning("업로드 URL 검증 실패(%s, 시도 %d/%d)",
                                provider.name, attempt, self.retries)
                except Exception as exc:  # noqa: BLE001
                    last_error = f"{provider.name}: {exc}"
                    log.warning("업로드 실패(%s, 시도 %d/%d): %s",
                                provider.name, attempt, self.retries, exc)
                if attempt < self.retries:
                    self._sleep(min(config.RETRY_BACKOFF_BASE ** (attempt - 1), 8))
            log.warning("호스트 %s 모든 시도 실패 → 폴백 전환", provider.name)

        raise UploadError(f"공개 URL 호스팅 실패: {last_error}")
