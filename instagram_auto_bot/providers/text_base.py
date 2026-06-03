"""Abstract text-AI provider + factory.

Concrete providers (Claude / OpenAI / Gemini) implement :meth:`generate`.  Each
imports its SDK *lazily* inside ``generate`` so this module - and everything
that depends on it - imports cleanly even when an SDK is not installed.  The
factory selects a provider by name; the chosen model defaults per provider when
the user leaves the model field blank.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import config


class ProviderError(Exception):
    """Generic, user-presentable provider failure."""


class ProviderUnavailable(ProviderError):
    """The provider's SDK could not be imported (not installed)."""


class TextProvider(ABC):
    #: short id, also the key into config.DEFAULT_TEXT_MODELS
    name: str = "base"

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key or ""
        self.model = model or config.DEFAULT_TEXT_MODELS.get(self.name, "")

    @abstractmethod
    def generate(self, prompt: str, system: str = "") -> str:
        """Return the model's text completion for ``prompt`` (+ optional system)."""
        raise NotImplementedError

    # -- helpers used by concrete providers ------------------------------- #
    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderError(f"{self.name} API 키가 설정되지 않았습니다 / API key missing.")


def get_text_provider(name: str, api_key: str = "", model: str = "") -> TextProvider:
    """Instantiate a text provider by name (claude | openai | gemini)."""
    key = (name or config.TEXT_PROVIDER).lower()
    if key == "claude":
        from providers.text_claude import ClaudeTextProvider
        return ClaudeTextProvider(api_key, model)
    if key == "openai":
        from providers.text_openai import OpenAITextProvider
        return OpenAITextProvider(api_key, model)
    if key == "gemini":
        from providers.text_gemini import GeminiTextProvider
        return GeminiTextProvider(api_key, model)
    raise ValueError(f"알 수 없는 텍스트 프로바이더: {name!r}")
