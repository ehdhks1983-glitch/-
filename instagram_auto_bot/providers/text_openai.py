"""OpenAI text provider (SDK imported lazily)."""

from __future__ import annotations

from providers.text_base import ProviderError, ProviderUnavailable, TextProvider


class OpenAITextProvider(TextProvider):
    name = "openai"

    def generate(self, prompt: str, system: str = "") -> str:
        self._require_key()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable(
                "openai SDK가 설치되지 않았습니다. requirements.txt를 설치하세요."
            ) from exc
        try:
            client = OpenAI(api_key=self.api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(model=self.model, messages=messages)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"OpenAI 호출 실패: {exc}") from exc
