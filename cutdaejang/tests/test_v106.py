"""v1.06 — 🛒 바로가기 링크 + 📱 블로그봇 방식(모바일 레시피) 상품 수집 (사용자 요청 2건).

"파트너스·쇼핑커넥트 들어가기가 힘들어" → 화면에 ↗ 바로가기.
"블로그봇의 쿠팡·네이버 크롤링을 적용시키라고" → 블로그가 5장 잘 되는 이유인
fetch_web의 모바일 UA(+cutdaejang 표식)·Referer 레시피를 상품 수집에도 적용:
데스크톱 요청이 3장 미만이면 m.coupang.com 모바일 페이지를 같은 레시피로 읽는다.
"""

from cutdaejang.gui import webui
from cutdaejang.tools import fetch_web
from cutdaejang.tools import product_page as pp


def test_quick_links_in_shop_card():
    html = webui._HTML
    for tok in ('href="https://partners.coupang.com"',
                'href="https://shoppingconnect.naver.com"',
                'href="https://developers.naver.com/apps/#/register"',
                "↗ 파트너스 열기", "↗ 쇼핑커넥트 열기", "↗ 앱 등록 페이지"):
        assert tok in html, tok


def test_mobile_variant_mapping():
    assert (pp._mobile_variant("https://www.coupang.com/vp/products/1?itemId=2")
            == "https://m.coupang.com/vp/products/1?itemId=2")
    assert pp._mobile_variant("https://smartstore.naver.com/x/products/1") == ""
    assert pp._mobile_variant("주소아님") == ""


def test_mobile_pass_uses_blog_recipe_and_merges(monkeypatch):
    """데스크톱 1장 → 모바일 페이지를 블로그 UA·Referer로 읽어 합류, 브라우저 생략."""
    desktop = ('<html><meta property="og:title" content="무선 청소기">'
               '<meta property="og:image" content="https://thumbnail1.coupangcdn.com/t/main.jpg">'
               '<p>' + "설명 " * 20 + '</p></html>')
    mobile = ('<html><meta property="og:title" content="무선 청소기">'
              '<img src="https://thumbnail2.coupangcdn.com/t/m1.jpg">'
              '<img src="https://thumbnail3.coupangcdn.com/t/m2.jpg">'
              '<img src="https://thumbnail4.coupangcdn.com/t/m3.jpg"></html>')
    calls = []

    def fake_fetch(url, timeout=20.0, ua="", referer=""):
        calls.append({"url": url, "ua": ua, "referer": referer})
        if url.startswith("https://m.coupang.com/"):
            return mobile, url
        return desktop, "https://www.coupang.com/vp/products/7"

    monkeypatch.setattr(pp, "_fetch_html", fake_fetch)
    monkeypatch.setattr(pp, "_browser_dump",
                        lambda u, timeout=50.0: (_ for _ in ()).throw(
                            AssertionError("모바일로 충분한데 브라우저를 띄움")))
    out = pp.collect_product("https://link.coupang.com/re/AFF1")
    assert len(out["images"]) == 4                    # 모바일 3 + 데스크톱 1 합류
    m_call = next(c for c in calls if c["url"].startswith("https://m.coupang.com/"))
    assert m_call["ua"] == fetch_web._UA              # 블로그와 같은 레시피
    assert "cutdaejang" in m_call["ua"]               # 표식 유지 (위장 아님)
    assert m_call["referer"] == "https://www.coupang.com/vp/products/7"


def test_mobile_fail_falls_through_to_browser(monkeypatch):
    """모바일도 실패하면 기존 v1.04 브라우저 재시도로 넘어간다."""
    desktop = ('<html><meta property="og:title" content="상품">'
               '<p>' + "설명 " * 20 + '</p></html>')

    def fake_fetch(url, timeout=20.0, ua="", referer=""):
        if url.startswith("https://m.coupang.com/"):
            raise OSError("모바일 차단")
        return desktop, "https://www.coupang.com/vp/products/8"

    dumped = ('<html><meta property="og:title" content="상품">'
              '<img src="https://thumbnail5.coupangcdn.com/t/b1.jpg"></html>')
    monkeypatch.setattr(pp, "_fetch_html", fake_fetch)
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=50.0: dumped)
    out = pp.collect_product("https://www.coupang.com/vp/products/8")
    assert out["via"] == "브라우저" and len(out["images"]) == 1
