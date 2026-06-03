"""Pytest bootstrap: make the project root importable and sandbox app-data.

Running ``pytest`` from anywhere under the repo will still resolve ``config``,
``paths``, ``core.*`` and ``providers.*`` as top-level imports (matching how
``main.py`` imports them when frozen).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    """Redirect the app-data directory to an isolated temp dir for a test."""
    home = tmp_path / "appdata"
    monkeypatch.setenv("INSTAAUTOBOT_HOME", str(home))
    return home
