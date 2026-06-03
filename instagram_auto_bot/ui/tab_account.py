"""Account & API-key settings tab (thin shell over the generic SettingsTab)."""

from __future__ import annotations

from core.forms import ACCOUNT_FIELDS
from core.settings_store import SettingsStore
from ui.widgets import SettingsTab


class AccountTab(SettingsTab):
    def __init__(self, master, store: SettingsStore, on_saved=None) -> None:
        super().__init__(
            master,
            title="계정 · API 키 / Account & Keys",
            subtitle="입력값은 이 PC의 사용자 폴더(AppData)에만 저장됩니다. 빌드에 포함되지 않습니다.",
            fields=ACCOUNT_FIELDS,
            store=store,
            on_saved=on_saved,
        )
