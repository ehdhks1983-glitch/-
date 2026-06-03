"""Hardware ID derivation.

Windows MachineGuid is preferred (stable across reinstalls of the app);
other platforms fall back to a hash of the MAC address + hostname.
"""
from __future__ import annotations

import hashlib
import platform
import uuid
from typing import Optional


def _windows_machine_guid() -> Optional[str]:
    try:
        import winreg  # type: ignore

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return None


def _raw_machine_identity() -> str:
    guid = _windows_machine_guid()
    if guid:
        return "win:" + guid
    mac = uuid.getnode()
    return "{sys}:{node}:{mac:012x}".format(
        sys=platform.system(), node=platform.node(), mac=mac
    )


def get_hwid() -> str:
    """Return a stable, opaque 32-char uppercase hex HWID for this machine."""
    raw = _raw_machine_identity()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32].upper()
