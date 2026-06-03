"""ImgBB image host fallback (uses the simple HTTP API; images only)."""

from __future__ import annotations

import base64

import requests

import config
from core.uploader import HostProvider, UploadError

IMGBB_ENDPOINT = "https://api.imgbb.com/1/upload"


class ImgbbHost(HostProvider):
    name = "imgbb"

    def __init__(self, store) -> None:
        self.api_key = store.get_str("imgbb_api_key")

    def upload(self, file_path: str) -> str:
        if not self.api_key:
            raise UploadError("ImgBB API 키가 설정되지 않았습니다.")
        try:
            with open(file_path, "rb") as fh:
                payload = base64.b64encode(fh.read())
            resp = requests.post(
                IMGBB_ENDPOINT,
                data={"key": self.api_key, "image": payload},
                timeout=config.HTTP_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data = resp.json()
            url = data.get("data", {}).get("url") or data.get("data", {}).get("display_url")
            if not url:
                raise UploadError("ImgBB 응답에 URL이 없습니다.")
            return url
        except UploadError:
            raise
        except Exception as exc:  # pragma: no cover
            raise UploadError(f"ImgBB 업로드 실패: {exc}") from exc
