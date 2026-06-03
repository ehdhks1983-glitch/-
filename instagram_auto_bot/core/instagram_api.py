"""Meta Graph API publishing (spec Stage 5).

Three-step container flow for every post:
  1. POST /{ig-user-id}/media         -> creation_id (image_url / REELS+video_url
                                          / CAROUSEL+children)
  2. GET  /{container-id}?status_code -> poll until FINISHED   (defends err 9007)
  3. POST /{ig-user-id}/media_publish -> media_id

Network calls go through an injectable ``session`` (requests.Session-like) and an
injectable ``sleep``/``clock`` so the entire flow - retries, polling, the daily
quota guard - is unit-testable offline with a fake session.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import requests

import config
import paths
from core.logging_setup import get_logger

log = get_logger("ig_api")


# --------------------------------------------------------------------------- #
# Errors / result
# --------------------------------------------------------------------------- #
class InstagramAPIError(Exception):
    def __init__(self, message, code=None, subcode=None, fbtrace=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.fbtrace = fbtrace
        self.http_status = http_status


class RateLimitError(InstagramAPIError):
    """Rate / quota related failure (Meta transient codes or self-imposed cap)."""


class AuthError(InstagramAPIError):
    """Token/permission failure - needs user re-authentication, not a retry."""


class SecurityCheckpointError(AuthError):
    """A security/validation checkpoint was detected. Never bypassed - alert user."""


class MediaNotReadyError(InstagramAPIError):
    """Meta error 9007 - publish attempted before the container FINISHED."""


@dataclass
class PublishResult:
    media_id: str
    container_id: str
    permalink: Optional[str] = None


# --------------------------------------------------------------------------- #
# Daily post quota guard (self-imposed cap, separate from Meta's 100/24h)
# --------------------------------------------------------------------------- #
class DailyPostGuard:
    def __init__(self, *, max_per_day: Optional[int] = None,
                 counts_path: Optional[Path] = None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.max = max_per_day if max_per_day is not None else config.MAX_POSTS_PER_DAY
        self._path = counts_path or (paths.appdata_dir() / "post_counts.json")
        self._clock = clock or datetime.now

    def _today(self) -> str:
        return self._clock().strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # keep only the most recent ~14 day keys
        if len(data) > 14:
            for k in sorted(data)[:-14]:
                data.pop(k, None)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def count_today(self) -> int:
        return int(self._load().get(self._today(), 0))

    def remaining(self) -> int:
        return max(0, self.max - self.count_today())

    def check(self) -> None:
        if self.count_today() >= self.max:
            raise RateLimitError(f"자체 일일 게시 한도({self.max}건)를 초과했습니다.")

    def record(self) -> None:
        data = self._load()
        t = self._today()
        data[t] = int(data.get(t, 0)) + 1
        self._save(data)


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #
class InstagramAPI:
    def __init__(self, access_token: str, ig_user_id: str, *,
                 session=None, sleep: Optional[Callable[[float], None]] = None,
                 poll_interval: Optional[float] = None, poll_max: Optional[int] = None,
                 retries: Optional[int] = None) -> None:
        self.token = access_token
        self.ig_user_id = str(ig_user_id)
        self.session = session or requests.Session()
        self._sleep = sleep or time.sleep
        self.poll_interval = config.STATUS_POLL_SEC if poll_interval is None else poll_interval
        self.poll_max = config.STATUS_POLL_MAX if poll_max is None else poll_max
        self.retries = config.RETRY_COUNT if retries is None else retries

    # ---- low level ------------------------------------------------------ #
    def _backoff(self, attempt: int) -> None:
        self._sleep(min(config.RETRY_BACKOFF_BASE ** (attempt - 1), 8))

    @staticmethod
    def _parse_json(resp) -> dict:
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}
        except ValueError:
            return {"_raw": getattr(resp, "text", "")}

    @staticmethod
    def _error_for(code, msg, sub, fb, status) -> InstagramAPIError:
        if code == config.ERR_MEDIA_NOT_READY:
            return MediaNotReadyError(msg, code, sub, fb, status)
        if sub in config.CHECKPOINT_SUBCODES:
            return SecurityCheckpointError(msg, code, sub, fb, status)
        if code in config.AUTH_ERROR_CODES:
            return AuthError(msg, code, sub, fb, status)
        if code in config.TRANSIENT_ERROR_CODES:
            return RateLimitError(msg, code, sub, fb, status)
        return InstagramAPIError(msg, code, sub, fb, status)

    def _request(self, method: str, url: str, params: Optional[dict] = None) -> dict:
        params = dict(params or {})
        params.setdefault("access_token", self.token)
        last: Optional[InstagramAPIError] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.request(method, url, params=params,
                                            timeout=config.HTTP_TIMEOUT_SEC)
            except requests.RequestException as exc:
                last = InstagramAPIError(f"네트워크 오류: {exc}")
                log.warning("API 네트워크 오류(%d/%d): %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    self._backoff(attempt)
                continue

            payload = self._parse_json(resp)
            err = payload.get("error") if isinstance(payload, dict) else None
            if err:
                code, sub = err.get("code"), err.get("error_subcode")
                msg, fb = err.get("message", ""), err.get("fbtrace_id")
                exc = self._error_for(code, msg, sub, fb, getattr(resp, "status_code", None))
                if isinstance(exc, RateLimitError) and attempt < self.retries:
                    log.warning("일시적 API 오류 code=%s 재시도(%d/%d): %s", code, attempt, self.retries, msg)
                    last = exc
                    self._backoff(attempt)
                    continue
                raise exc

            status = getattr(resp, "status_code", 200)
            if status >= 500 and attempt < self.retries:
                last = InstagramAPIError(f"서버 오류 {status}")
                self._backoff(attempt)
                continue
            if status >= 400:
                raise InstagramAPIError(f"HTTP {status}: {payload}", http_status=status)
            return payload
        raise last or InstagramAPIError("요청 실패")

    def _creation_id(self, data: dict) -> str:
        cid = data.get("id")
        if not cid:
            raise InstagramAPIError(f"컨테이너 ID가 응답에 없습니다: {data}")
        return str(cid)

    # ---- containers ----------------------------------------------------- #
    def create_image_container(self, image_url: str, caption: Optional[str] = None) -> str:
        params = {"image_url": image_url}
        if caption is not None:
            params["caption"] = caption
        return self._creation_id(self._request("POST", config.graph_url(self.ig_user_id, "media"), params))

    def create_reels_container(self, video_url: str, caption: Optional[str] = None,
                               cover_url: Optional[str] = None) -> str:
        params = {"media_type": "REELS", "video_url": video_url}
        if caption is not None:
            params["caption"] = caption
        if cover_url:
            params["cover_url"] = cover_url
        return self._creation_id(self._request("POST", config.graph_url(self.ig_user_id, "media"), params))

    def create_carousel_item(self, image_url: str) -> str:
        params = {"image_url": image_url, "is_carousel_item": "true"}
        return self._creation_id(self._request("POST", config.graph_url(self.ig_user_id, "media"), params))

    def create_carousel_container(self, children_ids: Sequence[str],
                                  caption: Optional[str] = None) -> str:
        params = {"media_type": "CAROUSEL", "children": ",".join(children_ids)}
        if caption is not None:
            params["caption"] = caption
        return self._creation_id(self._request("POST", config.graph_url(self.ig_user_id, "media"), params))

    # ---- status / publish ----------------------------------------------- #
    def get_status(self, container_id: str) -> str:
        data = self._request("GET", config.graph_url(container_id), {"fields": "status_code"})
        return data.get("status_code", "")

    def wait_until_finished(self, container_id: str, *, control=None) -> None:
        """Poll status_code until FINISHED. Raises on ERROR/EXPIRED/timeout."""
        for i in range(1, self.poll_max + 1):
            if control is not None:
                control.checkpoint()
            status = self.get_status(container_id)
            if status == config.IG_STATUS_FINISHED:
                log.info("컨테이너 준비 완료: %s", container_id)
                return
            if status in (config.IG_STATUS_ERROR, config.IG_STATUS_EXPIRED):
                raise InstagramAPIError(f"컨테이너 처리 실패(status={status}): {container_id}")
            log.info("컨테이너 처리 중(%d/%d) status=%s", i, self.poll_max, status or "?")
            self._sleep(self.poll_interval)
        raise InstagramAPIError(f"컨테이너 폴링 타임아웃({self.poll_max}회): {container_id}")

    def publish(self, creation_id: str) -> str:
        data = self._request("POST", config.graph_url(self.ig_user_id, "media_publish"),
                             {"creation_id": creation_id})
        mid = data.get("id")
        if not mid:
            raise InstagramAPIError(f"게시 응답에 미디어 ID가 없습니다: {data}")
        return str(mid)

    def _publish_with_retry(self, container_id: str, *, control=None) -> str:
        for attempt in range(1, self.retries + 1):
            try:
                return self.publish(container_id)
            except MediaNotReadyError:
                log.warning("게시 시 9007(미준비), 재폴링(%d/%d)", attempt, self.retries)
                if attempt >= self.retries:
                    raise
                self._sleep(self.poll_interval)
                self.wait_until_finished(container_id, control=control)
        raise InstagramAPIError("게시 재시도 실패")  # pragma: no cover

    def get_permalink(self, media_id: str) -> Optional[str]:
        try:
            data = self._request("GET", config.graph_url(media_id), {"fields": "permalink"})
            return data.get("permalink")
        except InstagramAPIError:
            return None

    # ---- high level ----------------------------------------------------- #
    def publish_image(self, image_url: str, caption: str, *, control=None) -> PublishResult:
        cid = self.create_image_container(image_url, caption)
        self.wait_until_finished(cid, control=control)
        mid = self._publish_with_retry(cid, control=control)
        return PublishResult(mid, cid, self.get_permalink(mid))

    def publish_carousel(self, image_urls: Sequence[str], caption: str, *, control=None) -> PublishResult:
        if not (config.CAROUSEL_MIN <= len(image_urls) <= config.CAROUSEL_MAX):
            raise ValueError(f"캐러셀은 {config.CAROUSEL_MIN}~{config.CAROUSEL_MAX}장이어야 합니다.")
        children: List[str] = []
        for url in image_urls:
            if control is not None:
                control.checkpoint()
            children.append(self.create_carousel_item(url))
        cid = self.create_carousel_container(children, caption)
        self.wait_until_finished(cid, control=control)
        mid = self._publish_with_retry(cid, control=control)
        return PublishResult(mid, cid, self.get_permalink(mid))

    def publish_reels(self, video_url: str, caption: str, cover_url: Optional[str] = None,
                      *, control=None) -> PublishResult:
        cid = self.create_reels_container(video_url, caption, cover_url)
        self.wait_until_finished(cid, control=control)
        mid = self._publish_with_retry(cid, control=control)
        return PublishResult(mid, cid, self.get_permalink(mid))
