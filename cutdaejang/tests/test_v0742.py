"""v0.74.2 — 파일 선택 창을 Windows에서 PowerShell(WinForms)로 전환.

기존엔 sys.executable 을 별도 파이썬으로 다시 띄워 tkinter 를 열었는데, 사용자
PC의 파이썬이 시작에 실패하면 'Failed to start embedded python interpreter!'
네이티브 오류창이 떴다. Windows에선 PowerShell 대화상자를 써서 그 실패를 없앤다.
"""
import base64
import subprocess
import sys

import pytest

from cutdaejang.gui import webui


class _FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_pick_windows_decodes_base64_path(monkeypatch):
    path = r"C:\Users\나\Videos\내 영상.mp4"
    out = base64.b64encode(path.encode("utf-8"))

    def fake_run(cmd, **kw):
        assert cmd[0] == "powershell"
        assert "-EncodedCommand" in cmd and "-STA" in cmd
        return _FakeProc(0, out, b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert webui._pick_windows("video", 5.0) == path


def test_pick_windows_multiselect_semicolon(monkeypatch):
    joined = r"C:\사진\a b.png;C:\사진\c.png"
    out = base64.b64encode(joined.encode("utf-8"))
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(0, out, b""))
    assert webui._pick_windows("images", 5.0) == joined


def test_pick_windows_cancel_returns_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(0, b"", b""))
    assert webui._pick_windows("image", 5.0) is None


def test_pick_windows_nonzero_raises_friendly(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(1, b"", b"boom"))
    with pytest.raises(RuntimeError) as ei:
        webui._pick_windows("audio", 5.0)
    assert "붙여넣" in str(ei.value)  # 경로 직접 붙여넣기 안내


def test_pick_windows_powershell_missing_raises_friendly(monkeypatch):
    def boom(cmd, **kw):
        raise FileNotFoundError("powershell not found")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(RuntimeError) as ei:
        webui._pick_windows("folder", 5.0)
    assert "붙여넣" in str(ei.value)


def test_pick_path_routes_to_powershell_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(webui, "_pick_windows", lambda kind, timeout: f"WIN:{kind}")
    # 비 Windows 경로가 잘못 불리면 실패하도록
    monkeypatch.setattr(webui, "_pick_tkinter", lambda kind, timeout: pytest.fail("tk"))
    assert webui.pick_path("audio") == "WIN:audio"


def test_pick_path_routes_to_tkinter_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(webui, "_pick_tkinter", lambda kind, timeout: f"TK:{kind}")
    monkeypatch.setattr(webui, "_pick_windows", lambda kind, timeout: pytest.fail("ps"))
    assert webui.pick_path("image") == "TK:image"


def test_pick_path_normalizes_unknown_kind(monkeypatch):
    seen = {}
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(webui, "_pick_windows",
                        lambda kind, timeout: seen.setdefault("kind", kind))
    webui.pick_path("evil'; Remove-Item C:\\ -Recurse")
    assert seen["kind"] == "video"  # 화이트리스트 밖 → 안전 기본값


def test_ps_template_substitutes_every_kind():
    for k in webui._PICK_KINDS:
        script = webui._PS_PICK_TEMPLATE.replace("@KIND@", k)
        assert "@KIND@" not in script
        assert f"$kind = '{k}'" in script
        # UTF-16LE base64 (PowerShell -EncodedCommand 형식)로 왕복 가능
        enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        assert base64.b64decode(enc).decode("utf-16-le") == script
    assert "OpenFileDialog" in webui._PS_PICK_TEMPLATE
    assert "FolderBrowserDialog" in webui._PS_PICK_TEMPLATE


def test_pick_video_file_delegates_to_pick_path(monkeypatch):
    monkeypatch.setattr(webui, "pick_path",
                        lambda kind="video", timeout=600.0: f"P:{kind}")
    assert webui.pick_video_file() == "P:video"
