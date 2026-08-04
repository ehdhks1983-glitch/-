"""v1.15 — 🔌 로그인해 둔 **그 크롬 창**으로 수집 (회원님 지적, 크롤링 5차).

> "블로그 구조는 일단 크롬을 실행해. 그리고 로그인을 해. 그다음에 크롤링을 해."

정확한 지적이었다. v1.12~v1.13.1은 로그인 창과 **별도의** 헤드리스 크롬을 띄우고
프로필(쿠키)만 복사했는데, 최신 크롬은 쿠키를 앱에 묶어 암호화해서 복사본을 다른
프로세스가 풀지 못한다 → 로그인해 둬도 수집은 로그아웃 상태였다.
이제 로그인 창을 원격 제어(CDP) 포트와 함께 띄우고, 수집은 **그 창에 탭을 열어**
페이지를 그린 뒤 DOM만 가져온다(탭은 바로 닫는다).
"""

import http.server
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang.gui import webui
from cutdaejang.tools import cdp
from cutdaejang.tools import product_page as pp

CHROME = "/opt/pw-browsers/chromium"
requires_chrome = pytest.mark.skipif(
    not Path(CHROME).exists(), reason="테스트용 크로미움이 없는 환경")

PAD = "<div class='prod-detail'><p>상품 상세 설명 문단입니다. 길게 채웁니다.</p></div>" * 80


def test_version():
    assert __version__ == "1.37.0"


# ── 최소 WebSocket/CDP 구현 자체 ────────────────────────────────
def test_read_debug_port(tmp_path):
    assert cdp.read_debug_port(tmp_path) == 0          # 창이 꺼져 있으면 0
    (tmp_path / cdp.DEVTOOLS_PORT_FILE).write_text("54321\n/devtools/browser/x",
                                                   encoding="utf-8")
    assert cdp.read_debug_port(tmp_path) == 54321
    (tmp_path / cdp.DEVTOOLS_PORT_FILE).write_text("이상한값", encoding="utf-8")
    assert cdp.read_debug_port(tmp_path) == 0          # 깨진 값도 예외 없이 0


def test_is_alive_false_on_dead_port():
    assert cdp.is_alive(0) is False
    assert cdp.is_alive(9) is False                    # 아무도 안 듣는 포트


def test_login_window_port_zero_without_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "login_profile_dir", lambda: tmp_path / "none")
    assert pp.login_window_port() == 0
    assert pp.login_debug()["window"] is False


def test_open_login_browser_opens_debug_port(tmp_path, monkeypatch):
    """로그인 창은 반드시 원격 제어 포트를 열고 뜬다 — 수집이 그 창을 쓰려면 필수."""
    exe = tmp_path / "chrome.exe"
    exe.write_bytes(b"x")
    prof = tmp_path / "prof"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    monkeypatch.setattr(pp, "_browser_candidates", lambda: [str(exe)])
    calls = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda a, **k: calls.append(list(a)))
    assert pp.open_login_browser("https://example.com/") == ""
    args = calls[0]
    assert "--remote-debugging-port=0" in args          # 포트는 크롬이 골라 파일에 적음
    assert f"--user-data-dir={prof}" in args
    assert any(a.startswith("--remote-allow-origins=http://127.0.0.1") for a in args)


# ── 실제 크롬으로 E2E: 크롬 실행 → 로그인 → 그 창으로 수집 ──────
class _Handler(http.server.BaseHTTPRequestHandler):
    """쿠키(로그인)가 있어야 사진이 보이는 가짜 상품 페이지."""

    def do_GET(self):  # noqa: N802
        if self.path == "/login":
            self.send_response(200)
            self.send_header("Set-Cookie", "sess=OK; Path=/")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>ok</body></html>")
            return
        logged = "sess=OK" in (self.headers.get("Cookie") or "")
        imgs = "".join(
            f"<img src='https://img.coupangcdn.com/thumb/p{i}_492x492.jpg'>"
            for i in range(5))
        body = ("<html><head><title>테스트 상품 3종 세트</title>"
                "<meta property='og:title' content='테스트 상품 3종 세트'></head><body>"
                + ((imgs + PAD) if logged else "<p>로그인이 필요합니다</p>" + PAD)
                + "<script>document.body.dataset.js='1'</script></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):  # noqa: D102 — 테스트 출력 조용히
        pass


@pytest.fixture()
def shop_site():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture()
def login_window(tmp_path, monkeypatch, shop_site):
    """컨테이너에서 실제 크로미움을 띄운다 (창 없는 환경이라 headless 플래그 추가)."""
    prof = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof)
    monkeypatch.setattr(pp, "_browser_candidates", lambda: [CHROME])
    real_popen = subprocess.Popen
    monkeypatch.setattr(
        subprocess, "Popen",
        lambda a, **k: real_popen(
            list(a) + ["--no-sandbox", "--headless=new", "--disable-gpu"], **k))
    assert pp.open_login_browser(shop_site + "/item") == ""
    monkeypatch.setattr(subprocess, "Popen", real_popen)   # 수집은 원래 코드 그대로
    # 크롬이 DevToolsActivePort 파일을 쓰기까지는 부하에 따라 수 초 걸린다 —
    # 전체 스위트 직후처럼 CPU가 바쁠 때 즉시 읽으면 헛손질 (1회 일시 실패 사례)
    import time
    port = 0
    for _ in range(120):
        port = pp.login_window_port()
        if port:
            break
        time.sleep(0.25)
    assert port, "로그인 창이 원격 제어 포트를 열지 못했어요 (30초 대기)"
    yield port
    try:
        cdp._http_json(port, "/json/close", timeout=2.0)
    except Exception:  # noqa: BLE001 — 정리 실패는 무해
        pass
    subprocess.run(["pkill", "-f", str(prof)], check=False)


@requires_chrome
def test_collect_uses_logged_in_window(shop_site, login_window):
    """① 크롬 실행 → ② 그 창에서 로그인 → ③ 같은 창으로 수집 = 사진이 들어온다."""
    # ② 로그인 전에는 사진이 안 보인다 (사이트가 로그인 안내만 준다)
    with pytest.raises(pp.ShopBlockedError) as e:
        pp.collect_product(shop_site + "/item")
    assert "로그인창 0장" in str(e.value)          # 창으로 읽었지만 로그인 전이라 0장

    # ② 회원님이 그 창에서 로그인 (사람이 하는 일 = 그 창의 탭으로 로그인 주소 방문)
    cdp.fetch_dom(login_window, shop_site + "/login")

    # ③ 같은 창으로 수집 → 쿠키가 살아 있어 사진이 보인다
    prod = pp.collect_product(shop_site + "/item")
    assert len(prod["images"]) == 5
    assert prod["title"] == "테스트 상품 3종 세트"
    assert prod["via"] == "로그인 창"                # 화면에 어느 길로 됐는지 표시
    assert "로그인창 5장" in (prod.get("via_detail") or "")
    assert prod["photo_note"] == ""                 # 사진이 있으면 경고 없음


@requires_chrome
def test_cdp_runs_javascript_and_closes_tab(shop_site, login_window):
    """페이지의 JS까지 실행된 DOM을 받고, 쓰고 난 탭은 남기지 않는다."""
    before = len(cdp._http_json(login_window, "/json/list") or [])
    html, final = cdp.fetch_dom(login_window, shop_site + "/item")
    assert "data-js=\"1\"" in html or "data-js='1'" in html   # JS 실행 결과가 DOM에
    assert final.endswith("/item")
    after = len(cdp._http_json(login_window, "/json/list") or [])
    assert after <= before                        # 탭이 쌓이지 않는다


@requires_chrome
def test_login_debug_reports_open_window(login_window):
    d = pp.login_debug()
    assert d["window"] is True                    # 화면이 "창 연결됨"으로 보여준다


# ── 화면 안내가 새 순서를 말한다 ───────────────────────────────
def test_ui_explains_window_flow():
    html = webui._apply_links(webui._HTML)
    assert "쿠팡·네이버 로그인 창 준비" in html                # v1.21 ①단계 (창 먼저)
    # v1.24: 6줄 벽글을 ①②③ 개조식으로 바꿨다 — 순서 자체는 그대로 설명한다
    assert "① <b>[창 열기]</b>를 누르고" in html
    assert "창은 <b>켜 둔 채</b>" in html
    assert "창 연결됨" in html                     # 상태줄의 성공 표시
    assert "창을 켜 둔 채 " in html                # 창을 열었을 때 안내(배너)
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "login_window_port()" in src           # 사진 0장 메시지에도 창 상태
