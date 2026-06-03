"""Declarative form field specs (Tk-free) shared by the settings tabs.

Keeping these as plain data lets the UI build widgets generically *and* lets the
test-suite assert that every secret key is masked and every field maps to a real
settings key - without importing Tk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import config


@dataclass(frozen=True)
class FieldSpec:
    key: str                              # maps to a SettingsStore key
    label: str                            # UI label
    secret: bool = False                  # render masked
    multiline: bool = False               # render as textbox
    options: Optional[Tuple[str, ...]] = None  # render as dropdown
    placeholder: str = ""
    help: str = ""


TEXT_PROVIDER_OPTIONS: Tuple[str, ...] = ("claude", "openai", "gemini")
HOST_PROVIDER_OPTIONS: Tuple[str, ...] = ("cloudinary", "imgbb")


# ----------------------------- Account / keys ----------------------------- #
ACCOUNT_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec("ig_user_id", "Instagram User ID (ig-user-id)",
              placeholder="178414xxxxxxxxxxx"),
    FieldSpec("ig_access_token", "Access Token", secret=True,
              help="Meta long-lived token (~60일). 만료 임박 시 자동 갱신."),
    FieldSpec("text_provider", "Text AI Provider", options=TEXT_PROVIDER_OPTIONS),
    FieldSpec("text_model", "Text Model",
              placeholder="비워두면 프로바이더 기본값 사용"),
    FieldSpec("text_api_key", "Text AI API Key", secret=True),
    FieldSpec("openai_api_key", "OpenAI API Key (이미지 생성)", secret=True),
    FieldSpec("image_model", "Image Model",
              placeholder="비워두면 기본값(gpt-image-1)"),
    FieldSpec("host_provider", "Image Host", options=HOST_PROVIDER_OPTIONS),
    FieldSpec("cloudinary_cloud_name", "Cloudinary Cloud Name"),
    FieldSpec("cloudinary_api_key", "Cloudinary API Key", secret=True),
    FieldSpec("cloudinary_api_secret", "Cloudinary API Secret", secret=True),
    FieldSpec("imgbb_api_key", "ImgBB API Key (폴백)", secret=True),
)


# --------------------------- Brand fact (brandfact) ----------------------- #
BRAND_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec("brand_name", "브랜드명 / Brand Name"),
    FieldSpec("brand_tone", "톤앤매너 / Tone",
              placeholder="예: 친근하고 신뢰감 있는"),
    FieldSpec("brand_target", "타겟 / Target Audience",
              placeholder="예: 30-40대 직장인"),
    FieldSpec("brand_core_message", "핵심 메시지 / Core Message", multiline=True),
    FieldSpec("brand_concept", "콘텐츠 컨셉 / Concept", multiline=True),
    FieldSpec("brand_banned_expressions", "추가 금지 표현 / Banned Expressions",
              multiline=True,
              help="쉼표로 구분. 콘텐츠 규칙의 기본 금지어에 더해 차단됩니다."),
)


def default_for(spec: FieldSpec) -> str:
    """Convenience: a provider field's first option, else empty string."""
    if spec.options:
        if spec.key == "text_provider":
            return config.TEXT_PROVIDER
        if spec.key == "host_provider":
            return config.HOST_PROVIDER
        return spec.options[0]
    return ""
