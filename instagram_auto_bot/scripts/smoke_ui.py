"""Headless UI smoke test (run under xvfb).

Boots the real CustomTkinter AppWindow, drives Start -> Pause -> Resume -> Stop
by pumping the Tk event loop manually, and asserts the controller reaches the
expected states and that the live-log panel received lines.  Prints SMOKE_OK on
success.  Not a pytest file (needs a display); invoked from CI/build via xvfb.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("INSTAAUTOBOT_HOME", tempfile.mkdtemp(prefix="insta_smoke_"))

from core.automation_controller import WorkerState  # noqa: E402
from ui.app_window import AppWindow  # noqa: E402


def pump(app, seconds: float, until=None) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        app.update_idletasks()
        if until is not None and until():
            return
        time.sleep(0.02)


def main() -> int:
    app = AppWindow()
    pump(app, 0.3)

    # Tab switching must not raise (incl. Create + Schedule status refresh).
    app._show("brand")
    app._show("create")
    pump(app, 0.2)
    app._show("schedule")
    pump(app, 0.2)
    assert "create" in app._tabs and "schedule" in app._tabs
    app._show("account")
    pump(app, 0.2)

    app._on_start()
    pump(app, 1.0, until=lambda: app.controller.state == WorkerState.RUNNING)
    assert app.controller.state == WorkerState.RUNNING, app.controller.state

    app._on_pause()
    pump(app, 0.4, until=lambda: app.controller.state == WorkerState.PAUSED)
    assert app.controller.state == WorkerState.PAUSED, app.controller.state

    app._on_pause()  # resume
    pump(app, 0.4, until=lambda: app.controller.state == WorkerState.RUNNING)
    assert app.controller.state == WorkerState.RUNNING, app.controller.state

    app._on_stop()
    pump(app, 3.0, until=lambda: app.controller.state == WorkerState.IDLE)
    assert app.controller.state == WorkerState.IDLE, app.controller.state

    # The log panel should have rendered some text by now.
    text = app.log_panel._box.get("1.0", "end")
    assert "데모" in text or "ready" in text or "start" in text, repr(text[:200])

    app._on_close()
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
