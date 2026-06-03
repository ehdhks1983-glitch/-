"""Filesystem path resolution with PyInstaller (``sys.frozen``) awareness.

This module is intentionally dependency-free so it can be imported very early
during start-up (before logging is configured) and unit-tested on any OS.

Layout
------
* ``BASE_DIR``        - directory of the executable (frozen) or this file (dev).
* app-data directory  - per-user writable location for settings + logs.
  On Windows this is ``%LOCALAPPDATA%\\InstaAutoBot`` (per spec). On macOS /
  Linux a platform-appropriate fallback is used so the app is testable and
  runnable cross-platform.  Override with the ``INSTAAUTOBOT_HOME`` env var.

Why app-data and not next to the EXE?  A frozen build installed under
``C:\\Program Files`` cannot write beside its own executable, so settings and
logs must live in a per-user writable directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "InstaAutoBot"
#: Environment variable that, when set, overrides the app-data directory.
HOME_ENV_VAR = "INSTAAUTOBOT_HOME"


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) frozen build."""
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Directory containing the executable (frozen) or this source file (dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled, read-only resource.

    Works both in development and inside a PyInstaller bundle, where data files
    are unpacked to ``sys._MEIPASS``.  Use this for anything added via
    ``--add-data`` (icons, the ``skills/`` manuals, etc.).
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent
    return root.joinpath(*parts)


def appdata_dir() -> Path:
    """Per-user writable directory for settings and logs.

    Resolved fresh on every call so tests can redirect it via the
    ``INSTAAUTOBOT_HOME`` environment variable without re-importing.
    """
    override = os.getenv(HOME_ENV_VAR)
    if override:
        return Path(override)

    # Windows - spec requirement: %LOCALAPPDATA%\InstaAutoBot
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / APP_NAME

    # macOS
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    # Linux / other - honour XDG when present
    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def logs_dir() -> Path:
    """Directory for dated log files (created by :func:`ensure_dirs`)."""
    return appdata_dir() / "logs"


def settings_file() -> Path:
    """Path to the JSON settings/secrets store."""
    return appdata_dir() / "settings.json"


def ensure_dirs() -> None:
    """Create the app-data and logs directories if they do not yet exist."""
    appdata_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)


# Convenience module-level constants (frozen state never changes at runtime).
BASE_DIR = base_dir()
