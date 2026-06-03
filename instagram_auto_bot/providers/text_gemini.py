"""Google Gemini text provider (SDK imported lazily)."""

from __future__ import annotations

from providers.text_base import ProviderError, ProviderUnavailable, TextProvider


class GeminiTextProvider(TextProvider):
    name = "gemini"

    def generate(self, prompt: str, system: str = "") -> str:
        self._require_key()
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable(
                "google-generativeai SDK가 설치되지 않았습니다. requirements.txt를 설치하세요."
            ) from exc
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model, system_instruction=system or None)
            resp = model.generate_content(prompt)
            return (getattr(resp, "text", "") or "").strip()
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Gemini 호출 실패: {exc}") from exc
