"""Anthropic Claude text provider (SDK imported lazily)."""

from __future__ import annotations

from providers.text_base import ProviderError, ProviderUnavailable, TextProvider

MAX_TOKENS = 2048


class ClaudeTextProvider(TextProvider):
    name = "claude"

    def generate(self, prompt: str, system: str = "") -> str:
        self._require_key()
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderUnavailable(
                "anthropic SDK가 설치되지 않았습니다. requirements.txt를 설치하세요."
            ) from exc
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            msg = client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
            )
            parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
            return "\n".join(parts).strip()
        except Exception as exc:  # pragma: no cover - network/runtime
            raise ProviderError(f"Claude 호출 실패: {exc}") from exc
