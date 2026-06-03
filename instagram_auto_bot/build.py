"""PyInstaller build script (spec Stage 8).

Produces a single-file desktop executable.  Run on the *target* OS (build a
Windows .exe on Windows - PyInstaller does not cross-compile):

    python build.py

Build rules enforced here:
* hidden imports for the AI/host SDKs (they're imported lazily at runtime).
* --collect-all for packages that ship data files (CustomTkinter themes,
  Cloudinary, the AI SDKs) so nothing is missed.
* bundles the read-only ``skills/`` manuals via --add-data.
* refuses to bundle secrets: settings.json / .env are never added (and we assert
  they are not in the data list).  Keys are entered by the user at runtime and
  saved to the per-user app-data dir, never baked into the build.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import config

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "InstaAutoBot"
ENTRY = "main.py"
DATA_SEP = ";" if os.name == "nt" else ":"

# SDKs imported lazily inside providers -> declare so PyInstaller bundles them.
HIDDEN_IMPORTS = [
    "anthropic",
    "openai",
    "google.generativeai",
    "cloudinary",
    "cloudinary.uploader",
    "PIL",
    "PIL._tkinter_finder",
    "customtkinter",
    "darkdetect",
]

# Packages that ship data files / many submodules -> collect everything.
COLLECT_ALL = ["customtkinter", "cloudinary"]

# Read-only resources to bundle (src, dest-in-bundle).
DATA = [("skills", "skills")]

# Files that must NEVER be bundled (secrets / per-user runtime state).
FORBIDDEN_IN_BUILD = {"settings.json", ".env", "post_counts.json", "schedule.json"}


def _icon_arg() -> list[str]:
    ico = BASE_DIR / "assets" / "app.ico"
    return ["--icon", str(ico)] if ico.exists() else []


def build_args() -> list[str]:
    """Return the full PyInstaller argument vector (pure - unit testable)."""
    args: list[str] = [
        str(BASE_DIR / ENTRY),
        "--name", APP_NAME,
        "--onefile",
        "--noconfirm",
        "--clean",
        "--windowed",                      # no console window
        "--distpath", str(BASE_DIR / "dist"),
        "--workpath", str(BASE_DIR / "build"),
        "--specpath", str(BASE_DIR / "build"),
    ]
    for mod in HIDDEN_IMPORTS:
        args += ["--hidden-import", mod]
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]
    for src, dest in DATA:
        # Guard: never let a secret/runtime file sneak into --add-data.
        assert Path(src).name not in FORBIDDEN_IN_BUILD, f"refusing to bundle {src}"
        args += ["--add-data", f"{BASE_DIR / src}{DATA_SEP}{dest}"]
    args += _icon_arg()
    return args


def _preflight() -> None:
    """Fail fast if a secret/runtime file is present in the bundle data dirs."""
    for name in FORBIDDEN_IN_BUILD:
        for hit in BASE_DIR.glob(f"skills/**/{name}"):
            raise SystemExit(f"보안 위반: 빌드 대상에 비밀/런타임 파일이 있습니다: {hit}")
    print(f"[build] {APP_NAME} v(api {config.GRAPH_API_VERSION}) - entry {ENTRY}")
    print(f"[build] hidden imports: {', '.join(HIDDEN_IMPORTS)}")


def main() -> int:
    _preflight()
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("PyInstaller가 설치되지 않았습니다. `pip install -r requirements-dev.txt`", file=sys.stderr)
        return 2
    pyi.run(build_args())
    print(f"[build] 완료 → {BASE_DIR / 'dist' / APP_NAME}{'.exe' if os.name == 'nt' else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
