"""v0.97 — 🖼 상품 링크 사진 수집 신뢰성: 전용 프로필 헤드리스 + 사진 0장 재시도."""

import urllib.error

from cutdaejang.tools import product_page as pp
from tests.test_v092 import FAKE_HTML

TEXT_ONLY_HTML = """<html><head>
<meta property="og:title" content="프리티케어 무선 물걸레 청소기 3in1">
<meta property="og:description" content="물걸레·진공·자동세척 3in1, 한 번 충전 12시간 씁니다.">
</head><body>사진은 JS로 늦게 그려져 원본 HTML에는 없음</body></html>""" + "x" * 3000


def test_browser_args_use_dedicated_profile():
    """엣지/크롬이 이미 떠 있어도 독립 헤드리스가 뜨도록 전용 프로필 필수.

    (같은 프로필이면 새 프로세스가 기존 창에 신호만 보내고 빈손 종료 —
    사용자 리포트 '사진이 안 들어와'의 주범)
    """
    args = pp._browser_args("/usr/bin/msedge", "https://www.coupang.com/vp/1")
    joined = " ".join(args)
    assert "--user-data-dir=" in joined and "cutdaejang_headless" in joined
    assert "--headless=new" in joined and "--dump-dom" in joined
    assert "--virtual-time-budget" in joined          # 늦은 로딩 사진 대기


def test_collect_retries_browser_when_no_images(monkeypatch):
    """직접 요청이 '글만' 주면(사진 0장) 성공으로 치지 않고 브라우저로 재시도한다."""
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (TEXT_ONLY_HTML, u))
    calls = []

    def fake_dump(u, timeout=50.0):
        calls.append(u)
        return FAKE_HTML

    monkeypatch.setattr(pp, "_browser_dump", fake_dump)
    d = pp.collect_product("https://www.coupang.com/vp/products/1")
    assert calls, "사진 0장인데 브라우저 재시도를 건너뜀"
    assert d["via"] == "브라우저" and len(d["images"]) >= 3


def test_collect_keeps_direct_when_images_present(monkeypatch):
    """직접 요청에 사진이 있으면 브라우저를 띄우지 않는다 (불필요한 30초 방지)."""
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (FAKE_HTML, u))

    def boom(u, timeout=50.0):
        raise AssertionError("사진이 이미 있는데 브라우저 실행")

    monkeypatch.setattr(pp, "_browser_dump", boom)
    d = pp.collect_product("https://www.coupang.com/vp/products/2")
    assert d["via"] == "직접" and d["images"]


def test_collect_text_only_fallback_still_usable(monkeypatch):
    """브라우저도 사진을 못 주면: 글이라도 살리고(성공), 사진 폴백은 호출측 안내."""
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (TEXT_ONLY_HTML, u))
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=50.0: "")
    d = pp.collect_product("https://www.coupang.com/vp/products/3")
    assert d["title"] and d["images"] == []
    # webui가 이 경우 페이지를 열고 복사→붙여넣기 안내를 띄운다
    src = open(__import__("cutdaejang.gui.webui", fromlist=["webui"]).__file__,
               encoding="utf-8").read()
    assert "사진은 자동으로 못 가져왔어요" in src
