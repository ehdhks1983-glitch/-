"""Application entry point.

Boots logging + paths, then launches the CustomTkinter UI.  The UI import is
deferred and guarded so that running on a machine without Tk produces a clear
message instead of an opaque traceback (the core/business logic does not need
Tk and is fully usable/testable headless).
"""

from __future__ import annotations

import sys

import paths
from core.logging_setup import get_logger, install_excepthook, setup_logging


def main() -> int:
    paths.ensure_dirs()
    log = setup_logging()
    install_excepthook(log)
    log.info("Starting %s", "Instagram Auto Bot")
    log.info("BASE_DIR=%s | APPDATA=%s | frozen=%s", paths.BASE_DIR, paths.appdata_dir(), paths.is_frozen())

    try:
        from ui.app_window import AppWindow
    except Exception:  # pragma: no cover - environment dependent
        get_logger().exception("Failed to import the UI layer")
        print(
            "이 프로그램은 데스크톱 환경(Tk 포함)이 필요합니다.\n"
            "This program requires a desktop environment with Tk/CustomTkinter installed.",
            file=sys.stderr,
        )
        return 2

    app = AppWindow()
    app.mainloop()
    log.info("Application closed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
