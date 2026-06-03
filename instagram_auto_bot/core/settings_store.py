"""Per-user settings & secrets store (JSON in the app-data directory).

* Every key defaults to an empty string / safe default - nothing secret is
  baked into the build (Principle: keys entered by the user at runtime).
* All file I/O is UTF-8 (Korean paths/content safe).
* Writes are atomic (temp file + ``os.replace``) so a crash mid-write cannot
  corrupt an existing settings file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import config
import paths

# Canonical key set with safe defaults. Adding a key here makes it appear (with
# its default) even for users whose on-disk file predates the key.
DEFAULT_SETTINGS: dict[str, Any] = {
    # --- Instagram / Meta ---
    "ig_access_token": "",
    "ig_user_id": "",
    "ig_token_obtained_at": "",     # ISO timestamp, set by token_manager.
    "ig_token_expires_at": "",      # ISO timestamp.
    # --- Text AI provider ---
    "text_provider": config.TEXT_PROVIDER,
    "text_model": config.TEXT_MODEL,
    "text_api_key": "",
    # --- Image AI provider ---
    "image_provider": config.IMAGE_PROVIDER,
    "image_model": config.IMAGE_MODEL,
    "openai_api_key": "",
    # --- Image hosting ---
    "host_provider": config.HOST_PROVIDER,
    "cloudinary_cloud_name": "",
    "cloudinary_api_key": "",
    "cloudinary_api_secret": "",
    "imgbb_api_key": "",
    # --- Brand fact (injected into every generation prompt) ---
    "brand_name": "",
    "brand_tone": "",
    "brand_target": "",
    "brand_core_message": "",
    "brand_concept": "",
    "brand_banned_expressions": "",
    # --- User-tunable safety knobs (mirror config defaults) ---
    "max_posts_per_day": config.MAX_POSTS_PER_DAY,
    "hashtag_count": config.IG_HASHTAG_COUNT,
}

# Keys that hold secrets - masked when displayed / logged.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "ig_access_token",
        "text_api_key",
        "openai_api_key",
        "cloudinary_api_secret",
        "cloudinary_api_key",
        "imgbb_api_key",
    }
)


def mask_secret(value: str, visible: int = 4) -> str:
    """Return a masked form of a secret for safe display/logging."""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


class SettingsStore:
    """Load / mutate / persist user settings.

    Parameters
    ----------
    path:
        Optional explicit settings file path (mainly for tests). Defaults to
        :func:`paths.settings_file`, resolved lazily on first use.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._explicit_path = path
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)

    # -- path -------------------------------------------------------------- #
    @property
    def path(self) -> Path:
        return self._explicit_path if self._explicit_path is not None else paths.settings_file()

    # -- load / save ------------------------------------------------------- #
    def load(self) -> "SettingsStore":
        """Load from disk, merging on top of defaults. Missing file => defaults."""
        merged = dict(DEFAULT_SETTINGS)
        p = self.path
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as fh:
                    on_disk = json.load(fh)
                if isinstance(on_disk, dict):
                    merged.update({k: v for k, v in on_disk.items()})
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable file: fall back to defaults rather than crash.
                # (token_manager / UI will prompt the user to re-enter keys.)
                merged = dict(DEFAULT_SETTINGS)
        self._data = merged
        return self

    def save(self) -> None:
        """Atomically persist current settings as UTF-8 JSON."""
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)  # atomic on POSIX & Windows.

    # -- accessors --------------------------------------------------------- #
    def get(self, key: str, default: Any = "") -> Any:
        return self._data.get(key, default)

    def get_str(self, key: str) -> str:
        return str(self._data.get(key, "") or "")

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._data.get(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)

    def as_dict(self, *, redact_secrets: bool = False) -> dict[str, Any]:
        if not redact_secrets:
            return dict(self._data)
        out: dict[str, Any] = {}
        for k, v in self._data.items():
            out[k] = mask_secret(str(v)) if k in SECRET_KEYS and v else v
        return out

    # -- convenience ------------------------------------------------------- #
    def is_configured_for_publish(self) -> bool:
        """Minimum keys present to attempt a publish."""
        return bool(self.get_str("ig_access_token") and self.get_str("ig_user_id"))

    def __contains__(self, key: str) -> bool:
        return key in self._data
