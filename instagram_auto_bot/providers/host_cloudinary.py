"""Cloudinary image/video host (SDK imported lazily)."""

from __future__ import annotations

from core.uploader import HostProvider, UploadError


class CloudinaryHost(HostProvider):
    name = "cloudinary"

    def __init__(self, store) -> None:
        self.cloud_name = store.get_str("cloudinary_cloud_name")
        self.api_key = store.get_str("cloudinary_api_key")
        self.api_secret = store.get_str("cloudinary_api_secret")

    def _require_creds(self) -> None:
        if not (self.cloud_name and self.api_key and self.api_secret):
            raise UploadError("Cloudinary 자격 증명이 설정되지 않았습니다.")

    def upload(self, file_path: str) -> str:
        self._require_creds()
        try:
            import cloudinary
            import cloudinary.uploader as cup
        except ImportError as exc:  # pragma: no cover
            raise UploadError("cloudinary SDK가 설치되지 않았습니다.") from exc
        try:
            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                secure=True,
            )
            result = cup.upload(file_path, resource_type="auto")
            url = result.get("secure_url") or result.get("url")
            if not url:
                raise UploadError("Cloudinary 응답에 URL이 없습니다.")
            return url
        except UploadError:
            raise
        except Exception as exc:  # pragma: no cover
            raise UploadError(f"Cloudinary 업로드 실패: {exc}") from exc
