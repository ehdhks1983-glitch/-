"""Stage 8 - build argument vector correctness + secret exclusion."""

from __future__ import annotations

import build


def _values(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag and i + 1 < len(args)]


def test_core_build_flags():
    args = build.build_args()
    assert args[0].endswith("main.py")
    assert _values(args, "--name") == ["InstaAutoBot"]
    assert "--onefile" in args
    assert "--windowed" in args
    assert "--noconfirm" in args


def test_hidden_imports_cover_lazy_sdks():
    hidden = set(_values(build.build_args(), "--hidden-import"))
    for mod in ("anthropic", "openai", "google.generativeai", "cloudinary",
                "customtkinter", "PIL"):
        assert mod in hidden, f"{mod} must be a hidden import (lazy at runtime)"


def test_collect_all_includes_customtkinter():
    assert "customtkinter" in _values(build.build_args(), "--collect-all")


def test_bundles_skills_manual():
    data = _values(build.build_args(), "--add-data")
    assert any(("skills" + build.DATA_SEP) in d and d.endswith("skills") for d in data)


def test_no_secret_files_are_bundled():
    data = _values(build.build_args(), "--add-data")
    for entry in data:
        src = entry.split(build.DATA_SEP)[0]
        assert not any(src.endswith(name) for name in build.FORBIDDEN_IN_BUILD)


def test_icon_arg_absent_without_icon():
    # No assets/app.ico in the repo -> no --icon flag (build must still work).
    assert "--icon" not in build.build_args()
