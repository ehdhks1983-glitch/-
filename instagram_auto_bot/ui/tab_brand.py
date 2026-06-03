"""Brand-fact settings tab (injected into every content-generation prompt)."""

from __future__ import annotations

from core.forms import BRAND_FIELDS
from core.settings_store import SettingsStore
from ui.widgets import SettingsTab


class BrandTab(SettingsTab):
    def __init__(self, master, store: SettingsStore, on_saved=None) -> None:
        super().__init__(
            master,
            title="브랜드 설정 / Brand Fact",
            subtitle="브랜드 정체성을 콘텐츠 생성 프롬프트에 자동 주입합니다.",
            fields=BRAND_FIELDS,
            store=store,
            on_saved=on_saved,
        )
