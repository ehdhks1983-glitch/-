"""v0.92 — 🛒 상품 링크 자동 수집: 직접 요청 → PC 브라우저 헤드리스 → 정직한 폴백."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from cutdaejang.tools import product_page as pp

FAKE_HTML = """<html><head>
<meta property="og:title" content="프리티케어 무선 물걸레 청소기 3in1">
<meta property="og:description" content="물걸레·진공·자동세척 3in1, 한 번 충전 12시간.">
<meta property="og:image" content="//thumbnail9.coupangcdn.com/thumbnails/remote/492x492ex/image/retail/images/main.jpg">
<title>무시될 타이틀</title></head><body>
<script>var p={"salePrice":257090};</script>
<img src="https://thumbnail1.coupangcdn.com/thumbnails/remote/230x230/image/retail/images/a1.jpg">
<img src="https://thumbnail1.coupangcdn.com/thumbnails/remote/230x230/image/retail/images/a1.jpg">
<img src="//image8.coupangcdn.com/image/vendor_inventory/b2.png">
<img src="https://static.coupangcdn.com/image/common/logo_top.png">
<img src="https://shop-phinf.pstatic.net/20240101/c3.jpg?type=f300">
</body></html>""" + "x" * 3000


def test_is_shop_url():
    for u in ("https://www.coupang.com/vp/products/123", "https://link.coupang.com/a/xyz",
              "https://smartstore.naver.com/shop/products/1", "https://brand.naver.com/x/2",
              "https://coupa.ng/abc"):
        assert pp.is_shop_url(u), u
    for u in ("https://blog.naver.com/abc/1", "https://example.com", "", "not-a-url"):
        assert not pp.is_shop_url(u), u


def test_parse_product_extracts_title_price_images():
    d = pp.parse_product(FAKE_HTML)
    assert d["title"].startswith("프리티케어 무선 물걸레 청소기")
    assert "257,090원" in d["text"] and "3in1" in d["text"]
    imgs = d["images"]
    assert imgs[0].startswith("https://thumbnail9.coupangcdn.com")   # og:image 맨 앞
    assert sum("a1.jpg" in u for u in imgs) == 1                     # 중복 제거
    assert any("vendor_inventory/b2.png" in u for u in imgs)         # // → https 보정
    assert all(u.startswith("https://") for u in imgs)
    assert not any("logo" in u for u in imgs)                        # 로고·아이콘 제외


def test_collect_product_direct_then_browser(monkeypatch):
    # ① 직접 요청 성공 → via 직접
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (FAKE_HTML, u + "?final"))
    d = pp.collect_product("https://link.coupang.com/a/xyz")
    assert d["via"] == "직접" and d["final_url"].endswith("?final") and d["images"]
    # ② 직접 403 → 설치된 브라우저 헤드리스로 성공 → via 브라우저
    def blocked(u, timeout=20.0):
        raise urllib.error.HTTPError(u, 403, "Forbidden", None, None)
    monkeypatch.setattr(pp, "_fetch_html", blocked)
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=45.0: FAKE_HTML)
    d2 = pp.collect_product("https://www.coupang.com/vp/products/9")
    assert d2["via"] == "브라우저" and d2["title"]
    # ③ 둘 다 실패 → 복사→붙여넣기 폴백 안내
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=45.0: "")
    with pytest.raises(pp.ShopBlockedError) as ei:
        pp.collect_product("https://www.coupang.com/vp/products/9")
    assert "Ctrl+V" in str(ei.value)


def test_v092_ui_wired():
    html = webui._HTML
    for tok in ("linkOnly", "링크에서 자동 수집 중", "사진·설명을 자동 수집"):
        assert tok in html, tok


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v092")
    iso = tmp_path_factory.mktemp("iso92")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_shop_link_autocollect_e2e(server, monkeypatch):
    """링크만으로 /api/fetch_url → 사진 다운로드 + 대본까지 (수집은 모킹)."""
    from cutdaejang.tools import fetch_web

    monkeypatch.setattr(pp, "_fetch_html",
                        lambda u, timeout=20.0: (FAKE_HTML, u))
    big = b"\x89PNG\r\n\x1a\n" + b"0" * 20000
    monkeypatch.setattr(fetch_web, "fetch_bytes", lambda url, **kw: big)
    d = _post(server, "/api/fetch_url",
              {"url": "https://www.coupang.com/vp/products/777"})
    assert d.get("ok"), d
    t0, t = time.time(), {}
    while time.time() - t0 < 60:
        with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
            t = json.loads(r.read()).get("weblink_fetch") or {}
        if not t.get("running"):
            break
        time.sleep(0.5)
    assert not t.get("error"), t
    r = t.get("result") or {}
    assert r.get("script_lines"), t                     # 키 없어도 원문 문장 폴백
    assert len(r.get("images") or []) >= 4              # 사진 여러 장 자동 수집
    assert all(p.startswith("/weblink/") for p in r.get("previews") or [])
    assert "자동 수집" in ((r.get("notes") or [""])[0])
