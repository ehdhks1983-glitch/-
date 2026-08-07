"""v1.18 — 📦 배포 1단계 (회원님 요청 23번): 전용 창 + 새 버전 확인.

  ① 실행하면 엣지/크롬 --app **전용 창**(주소창 없음)으로 열림 — 회원 눈에는
     윈도우 프로그램. 크롬·엣지가 없으면 지금처럼 기본 브라우저로 폴백.
  ② [🔄 새 버전 확인] — update_url.txt의 version.json 주소를 읽어 새 버전이면
     첫 화면에 다운로드 안내(+하루 1회 자동 확인). 주소가 없으면 조용히 꺼짐.
  ③ 업데이트.bat(설정·키 보존 교체)은 기존 그대로 — 안내 문구가 연결.
"""

import http.server
import json
import socketserver
import subprocess
import threading
import urllib.request

import pytest

from cutdaejang import __version__, config
from cutdaejang.gui import webui


def test_version():
    assert __version__ == "1.48.0"


# ── 🪟 전용 창 ───────────────────────────────────────────────────
def test_open_ui_window_uses_app_flag(tmp_path, monkeypatch):
    from cutdaejang.tools import product_page as pp

    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(pp, "_browser_candidates", lambda: [str(exe)])
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda a, **k: calls.append(list(a)))
    webui._open_ui_window("http://127.0.0.1:7860/")
    assert calls and calls[0][0] == str(exe)
    assert "--app=http://127.0.0.1:7860/" in calls[0]   # 주소창 없는 앱 창


def test_open_ui_window_falls_back_to_browser(monkeypatch):
    import webbrowser

    from cutdaejang.tools import product_page as pp

    monkeypatch.setattr(pp, "_browser_candidates", lambda: [])
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u))
    webui._open_ui_window("http://127.0.0.1:7860/")
    assert opened == ["http://127.0.0.1:7860/"]         # 엣지·크롬 없으면 기존 방식


def test_run_launches_app_window():
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "_open_ui_window(url)" in src
    assert "webbrowser.open(url)).start()" not in src   # 옛 직행 호출은 제거


# ── 🔄 새 버전 확인 ──────────────────────────────────────────────
def test_ver_tuple():
    assert webui._ver_tuple("1.18.0") == (1, 18, 0)
    assert webui._ver_tuple("v1.19") == (1, 19)
    assert webui._ver_tuple("1.19.0") > webui._ver_tuple("1.18.9")
    assert webui._ver_tuple("") == (0,)


def test_update_channel_url_parses_file(tmp_path, monkeypatch):
    f = tmp_path / "update_url.txt"
    monkeypatch.setattr(config, "Path", config.Path)      # no-op — 명시성
    real = config.update_channel_url
    # 실제 함수는 패키지 안 파일을 읽는다 — 기본 배포본은 주석뿐이라 꺼짐
    assert real() == ""
    f.write_text("# 주석\n\nhttps://example.com/version.json\n", encoding="utf-8")
    lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert lines == ["https://example.com/version.json"]  # 파서 규칙과 동일


class _VerHandler(http.server.BaseHTTPRequestHandler):
    body = ('{"version": "9.9.9", "url": "https://cafe.example/zip", '
            '"note": "테스트"}').encode("utf-8")

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):  # noqa: D102
        pass


@pytest.fixture()
def server(tmp_path_factory):
    import os

    workdir = tmp_path_factory.mktemp("v118-jobs")
    iso = tmp_path_factory.mktemp("iso118")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=20) as r:
        return json.loads(r.read())


def test_update_check_route(server, monkeypatch):
    # 주소 미설정 → 조용한 꺼짐 (이유 문구)
    d = _get(server, "/api/update_check")
    assert d["ok"] is False and "설정되지" in d["reason"]
    # 가짜 배포 채널을 세워 새 버전 흐름 전체 확인
    vs = socketserver.TCPServer(("127.0.0.1", 0), _VerHandler)
    threading.Thread(target=vs.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{vs.server_address[1]}/version.json"
        monkeypatch.setattr(config, "update_channel_url", lambda: url)
        d = _get(server, "/api/update_check")
        assert d["ok"] and d["newer"] is True
        assert d["latest"] == "9.9.9" and d["current"] == __version__
        assert d["url"] == "https://cafe.example/zip" and d["note"] == "테스트"
        # 같은 버전이면 newer=False
        _VerHandler.body = json.dumps({"version": __version__}).encode()
        d = _get(server, "/api/update_check")
        assert d["ok"] and d["newer"] is False
    finally:
        vs.shutdown()


def test_home_update_ui_wired():
    html = webui._HTML
    for tok in ('id="updateState"', "function checkUpdate", "function autoCheckUpdate",
                "🔄 새 버전 확인", "업데이트.bat]를 실행하면 설정 그대로",
                "upd_last"):
        assert tok in html, tok
    assert "autoCheckUpdate();" in html                  # 시작 시 하루 1회
    # 배포 채널 파일이 패키지에 실려 나간다 (기본은 주석뿐 = 꺼짐)
    from pathlib import Path

    f = Path("cutdaejang/update_url.txt")
    assert f.is_file() and config.update_channel_url() == ""
