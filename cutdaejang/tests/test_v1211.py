"""v1.21.1 — 🔗 naver.me 상품 오판 수정 + 🧹 전체 초기화 (1·2 9차 + 30번).

> "네이버는 크롤링이 안 되고" — naver.me 링크가 '글에서 본문과 사진을 찾지
> 못했어요'(블로그 수집 실패)로 빠짐. 네이버 창(9223)이 ✅ 연결인데도 안 씀.
> "전체 초기화 버튼 같은 게 있어야 — 아니면 다른 링크를 넣으면 대본부터 초기화."

① 오판 원인: 단축링크의 최종 주소를 일반 요청으로만 알아내는데, 그게 막히면
   상품인데도 빈손("") → 블로그 수집으로 흘러가 실패 메시지가 떴다.
   → 일반 판정이 실패하면 **열려 있는 전용 창으로 잠깐 열어** 실제 도착 주소를
   읽는 폴백. 창이 없으면 예전과 동일(블로그 흐름 불변).
② 초기화: 다른 상품 링크로 수집하면 대본·훅·미리보기까지 자동 초기화(같은
   링크 재수집은 직접 다듬은 훅·대본 존중) + [🧹 전체 초기화] 버튼.
"""

from cutdaejang import __version__
from cutdaejang.gui import webui
from cutdaejang.tools import cdp
from cutdaejang.tools import product_page as pp

SMART = "https://smartstore.naver.com/shop/products/123"


def test_version():
    assert __version__ == "1.22.1"


# ── ① naver.me → 전용 창으로 실제 도착 주소 확인 ─────────────────
def test_short_link_resolves_via_naver_window(monkeypatch):
    monkeypatch.setattr(pp, "_landing_url", lambda u, timeout=8.0: "")   # 일반 판정 실패
    monkeypatch.setattr(pp, "shop_window_port",
                        lambda shop: 9223 if shop == "naver" else 0)
    opened = {}

    def fake_dom(port, url, timeout=0, settle_s=0):
        opened.update(port=port, url=url)
        return "<html>...</html>", SMART

    monkeypatch.setattr(cdp, "fetch_dom", fake_dom)
    assert pp.resolve_shop_url("https://naver.me/Fc6Y7YAo") == SMART
    assert opened["port"] == 9223                    # 반드시 네이버 전용 창으로


def test_short_link_blog_stays_blog(monkeypatch):
    """창으로 열어봤더니 블로그면 — 상품으로 우기지 않고 블로그 흐름 그대로."""
    monkeypatch.setattr(pp, "_landing_url", lambda u, timeout=8.0: "")
    monkeypatch.setattr(pp, "shop_window_port", lambda shop: 9223)
    monkeypatch.setattr(cdp, "fetch_dom",
                        lambda *a, **k: ("<html>", "https://blog.naver.com/x/1"))
    assert pp.resolve_shop_url("https://naver.me/blogpost") == ""


def test_short_link_without_window_unchanged(monkeypatch):
    """창이 꺼져 있으면 예전 판정 그대로 — 네트워크 추가 접촉 없음."""
    monkeypatch.setattr(pp, "_landing_url", lambda u, timeout=8.0: "")
    monkeypatch.setattr(pp, "shop_window_port", lambda shop: 0)
    monkeypatch.setattr(cdp, "fetch_dom",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출 금지")))
    assert pp.resolve_shop_url("https://naver.me/Fc6Y7YAo") == ""


def test_plain_landing_still_first(monkeypatch):
    """일반 판정이 되면 창을 건드리지 않는다 (기존 경로 우선)."""
    monkeypatch.setattr(pp, "_landing_url", lambda u, timeout=8.0: SMART)
    monkeypatch.setattr(cdp, "fetch_dom",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출 금지")))
    assert pp.resolve_shop_url("https://naver.me/ok") == SMART


# ── ② 전체 초기화 배선 ───────────────────────────────────────────
def test_reset_wiring():
    html = webui._apply_links(webui._HTML)
    for tok in ("resetShopCard", "🧹 전체 초기화", "쇼핑 카드를 비웠어요",
                "로그인 창은 그대로"):
        assert tok in html, tok
    # 다른 상품이면 대본·훅·미리보기 자동 초기화, 같은 링크 재수집은 존중
    assert "const newProduct = !window._shopLastLink || link !== window._shopLastLink" in html
    i = html.index("const newProduct")
    body = html[i:i + 400]
    assert "$('shopScript').value = ''" in body and "$('shopHook').value = ''" in body
