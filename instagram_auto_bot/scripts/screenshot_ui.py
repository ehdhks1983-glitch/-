"""Render the AppWindow and save a PNG of the root display (run under xvfb)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("INSTAAUTOBOT_HOME", tempfile.mkdtemp(prefix="insta_shot_"))

from ui.app_window import AppWindow  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/insta_ui.png"


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        app.update_idletasks()
        time.sleep(0.02)


app = AppWindow()
app.geometry("1100x720+0+0")
pump(app, 0.6)
app._on_start()           # show it mid-run with live logs
pump(app, 1.2)
app.update_idletasks()
subprocess.run(["import", "-window", "root", OUT], check=True)
print("saved", OUT)
app._on_stop()
pump(app, 0.3)
app._on_close()
