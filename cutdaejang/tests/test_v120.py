"""v1.20 — 🔌 쇼핑 수집 6차: 사이트별 전용 로그인 창(고정 포트 9222/9223).

> "블로그 기준으로 포트 9222·9223 이런 식으로, 쿠팡이면 쿠팡파트너스, 네이버면
>  쇼핑커넥트 창이 떠. 본인이 직접 로그인하고 크롤링 버튼을 누르면 그걸 기반으로
>  크롤링하는데 — 지금 꺼는 순서도 순서지만 크롤링 자체가 아예 안 돼."

6차에서 찾은 결함 2개(코드 검증으로 확정):
  ① [내 크롬 열기]를 **다시** 누르면 포트 기록부터 지우는데, 같은 프로필의 창이
     이미 떠 있으면 크로미움은 새 탭 신호만 보내고 즉시 종료한다 → 기록이 다시
     안 적혀 **창은 떠 있는데 연결만 끊긴 상태**가 됐다 (연결이 "영영" 안 됨).
  ② 그 상태에서 수집이 **조용히 헤드리스로 폴백** — 최신 크롬의 앱 결합 암호화
     때문에 로그아웃 페이지(사진 0장)만 읽어 "아예 안 되는" 체감을 만들었다.
개편: 쿠팡 9222·네이버 9223 전용 창(살아 있으면 재사용, 절대 재실행 안 함),
창이 없으면 폴백 대신 ①창 열기 ②로그인 ③수집 순서를 그대로 안내한다.
"""

import http.server
import socketserver
import subprocess
import threading
import time
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
    assert __version__ == "1.24.0"


# ── 사이트 → 전용 창 매핑 ────────────────────────────────────────
def test_shop_for_url_mapping():
    assert pp.shop_for_url("https://www.coupang.com/vp/products/1") == "coupang"
    assert pp.shop_for_url("https://link.coupang.com/a/xyz") == "coupang"
    assert pp.shop_for_url("https://smartstore.naver.com/shop/products/2") == "naver"
    assert pp.shop_for_url("https://naver.me/xyz") == "naver"
    assert pp.shop_for_url("https://www.11st.co.kr/products/3") == ""   # 기타 몰은 기존 경로
    assert pp.shop_for_url("not-a-url") == ""


def test_shop_windows_spec():
    """블로그 툴과 같은 규칙 — 쿠팡 9222·네이버 9223, 로그인은 파트너스/쇼핑커넥트."""
    assert pp.SHOP_WINDOWS["coupang"]["port"] == 9222
    assert pp.SHOP_WINDOWS["naver"]["port"] == 9223
    assert "partners.coupang.com" in pp.SHOP_WINDOWS["coupang"]["login_url"]
    assert "brandconnect.naver.com" in pp.SHOP_WINDOWS["naver"]["login_url"]


def test_login_debug_has_window_states(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "login_profile_dir", lambda: tmp_path / "none")
    d = pp.login_debug()
    assert d["windows"] == {"coupang": 0, "naver": 0}


# ── 창이 없으면 조용한 폴백 대신 ①②③ 안내 ──────────────────────
def test_dump_raises_stepwise_guidance_without_window(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "login_profile_dir", lambda: tmp_path / "prof")
    with pytest.raises(pp.ShopLoginNeededError) as e:
        pp._browser_dump("https://www.coupang.com/vp/products/1")
    msg = str(e.value)
    for tok in ("쿠팡", "9222", "🛒 쿠팡 창 열기", "①", "②", "③", "로그인"):
        assert tok in msg, tok
    with pytest.raises(pp.ShopLoginNeededError) as e2:
        pp._browser_dump("https://smartstore.naver.com/x/products/9")
    assert "9223" in str(e2.value) and "네이버" in str(e2.value)


def _rich_html(n_imgs: int) -> str:
    imgs = "".join(
        f"<img src='https://thumbnail1.coupangcdn.com/t/p{i}_492x492.jpg'>"
        for i in range(n_imgs))
    return ("<html><head><title>수집 테스트 상품</title>"
            "<meta property='og:description' content='설명이 서른 글자를 넘는 상품 설명 문장입니다'>"
            "</head><body>" + imgs + PAD + "</body></html>")


def test_collect_survives_closed_window_when_script_possible(tmp_path, monkeypatch):
    """대본이 되는 상태면 창이 꺼져 있어도 죽지 않는다 — 안내만 남기고 진행."""
    monkeypatch.setattr(pp, "login_profile_dir", lambda: tmp_path / "prof")
    monkeypatch.setattr(pp, "_fetch_html",
                        lambda url, **k: (_rich_html(1), url))
    prod = pp.collect_product("https://www.coupang.com/vp/products/77")
    assert prod["title"] == "수집 테스트 상품"
    assert prod["images"]                          # 직접 경로의 사진은 유지
    assert "전용 창 꺼짐" in (prod.get("via_detail") or "")


def test_collect_raises_guidance_when_nothing_usable(tmp_path, monkeypatch):
    """직접·모바일이 다 막히고 창도 없으면 — ①②③ 안내가 그대로 올라온다."""
    def _blocked(url, **k):
        raise OSError("blocked")

    monkeypatch.setattr(pp, "login_profile_dir", lambda: tmp_path / "prof")
    monkeypatch.setattr(pp, "_fetch_html", _blocked)
    with pytest.raises(pp.ShopLoginNeededError) as e:
        pp.collect_product("https://www.coupang.com/vp/products/88")
    assert "9222" in str(e.value) and "쿠팡" in str(e.value)


# ── 실제 크로미움 — 고정 포트로 열리고, 다시 누르면 재사용 ───────
class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = ("<html><head><title>전용 창 테스트</title></head><body>"
                "<p>로그인이 필요합니다</p>" + PAD + "</body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):  # noqa: D102
        pass


@pytest.fixture()
def local_site():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture()
def shop_window(tmp_path, monkeypatch, local_site):
    """쿠팡 전용 창을 실제 크로미움으로 (창 없는 환경이라 headless 플래그 추가)."""
    prof_base = tmp_path / "browser_profile"
    monkeypatch.setattr(pp, "login_profile_dir", lambda: prof_base)
    monkeypatch.setattr(pp, "_browser_candidates", lambda: [CHROME])
    monkeypatch.setitem(pp.SHOP_WINDOWS["coupang"], "login_url", local_site + "/login")
    real_popen = subprocess.Popen
    launches = []

    def _popen(a, **k):
        launches.append(list(a))
        return real_popen(list(a) + ["--no-sandbox", "--headless=new",
                                     "--disable-gpu"], **k)

    monkeypatch.setattr(subprocess, "Popen", _popen)
    assert pp.open_shop_window("coupang") == ""
    port = 0
    for _ in range(120):                      # 부하 시 포트 파일이 늦게 적힌다 (30초)
        port = pp.shop_window_port("coupang")
        if port:
            break
        time.sleep(0.25)
    assert port, "쿠팡 전용 창이 원격 제어 포트를 열지 못했어요 (30초 대기)"
    yield port, launches
    monkeypatch.setattr(subprocess, "Popen", real_popen)
    subprocess.run(["pkill", "-f", str(pp.shop_profile_dir('coupang'))], check=False)


@requires_chrome
def test_shop_window_fixed_port_and_reuse(shop_window):
    """고정 포트(9222 계열)로 열리고, 버튼을 다시 눌러도 **새로 띄우지 않는다**."""
    port, launches = shop_window
    assert port == 9222, port                  # 블로그 툴과 같은 고정 포트
    n = len(launches)
    assert pp.open_shop_window("coupang") == ""   # 살아 있으면 그대로 재사용
    assert len(launches) == n                      # ← 6차 결함 ①의 재발 방지 핵심
    assert pp.shop_window_port("coupang") == port
    assert pp.login_debug()["windows"]["coupang"] == port


@requires_chrome
def test_dump_routes_shop_url_to_its_window(shop_window, local_site, monkeypatch):
    """쿠팡 주소는 쿠팡 전용 창으로 읽는다 — via 표시도 '쿠팡 창'."""
    port, _ = shop_window
    monkeypatch.setitem(pp.SHOP_WINDOWS["coupang"], "hosts",
                        ("coupang.com", "127.0.0.1"))
    html = pp._browser_dump(local_site + "/item")
    assert "로그인이 필요합니다" in html
    assert pp._LAST_DUMP_VIA == "쿠팡 창"


# ── 화면·라우트 배선 ─────────────────────────────────────────────
def test_ui_and_route_wiring():
    html = webui._apply_links(webui._HTML)
    for tok in ("🛒 쿠팡 창 열기", "🟢 네이버 창 열기", "9222", "9223",
                "openShopLogin(event,'coupang')", "openShopLogin(event,'naver')",
                "g.windows", "쿠팡 창(", "네이버 창("):
        assert tok in html, tok
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "open_shop_window(shop)" in src and "shop_window_port(shop)" in src
    assert src.count("로그인: 없음") >= 2          # 사진 0장 진단 문구 유지
    psrc = open("cutdaejang/tools/product_page.py", encoding="utf-8").read()
    assert "ShopLoginNeededError" in psrc and "SHOP_WINDOWS" in psrc
    assert psrc.count("9222") >= 1 and "재사용" in psrc
