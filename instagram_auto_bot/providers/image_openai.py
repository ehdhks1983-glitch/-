"""OpenAI image generation provider (SDK imported lazily).

Returns raw image bytes so the ImageEngine can ratio-correct them uniformly,
regardless of which source produced the pixels.
"""

from __future__ import annotations

import base64

import config
from providers.text_base import ProviderError, ProviderUnavailable


class OpenAIImageProvider:
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key or ""
        self.model = model or config.DEFAULT_IMAGE_MODEL

    def generate(self, prompt: str, size: str = "1024x1024") -> bytes:
        if not self.api_key:
            raise ProviderError("OpenAI API 키가 설정되지 않았습니다 / API key missing.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("openai SDK가 설치되지 않았습니다.") from exc
        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.images.generate(model=self.model, prompt=prompt, size=size, n=1)
            item = resp.data[0]
            b64 = getattr(item, "b64_json", None)
            if b64:
                return base64.b64decode(b64)
            url = getattr(item, "url", None)
            if url:
                import requests
                r = requests.get(url, timeout=config.HTTP_TIMEOUT_SEC)
                r.raise_for_status()
                return r.content
            raise ProviderError("이미지 응답에 데이터가 없습니다.")
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"OpenAI 이미지 생성 실패: {exc}") from exc
