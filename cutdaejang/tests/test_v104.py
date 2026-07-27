"""v1.04 — 🛒 쇼핑 링크 사진 수집 강화 + 훅 문구 상시 노출 (사용자 리포트 2건).

리포트: "아직도 한 장만 들어오네" + "후킹 문구 넣는 설정은 없어?"
① 상품 사진이 JSON 안에 \\/ 이스케이프로 실려 정규식이 못 긁던 것(대표 1장의
  주범)을 해제 + 대형몰 CDN 4종 추가 + 3장 미만이면 브라우저 재시도·합집합.
② 훅 제목 입력이 대본 생성 후에만 보이던 것을 상시 노출 + [🪝 AI 추천] 신설.
"""

from cutdaejang.gui import webui
from cutdaejang.tools import product_page as pp


def test_escaped_json_image_urls_are_extracted():
    """JSON 이스케이프(https:\\/\\/…)·\\u002F 주소도 긁는다 — '한 장만'의 주범."""
    html = (
        '{"images":["https:\\/\\/thumbnail7.coupangcdn.com\\/thumbnails\\/a1.jpg",'
        '"https:\\/\\/thumbnail8.coupangcdn.com\\/thumbnails\\/a2.jpg"],'
        '"more":"https:\\u002F\\u002Fshop-phinf.pstatic.net\\u002Fmain\\u002Fb1.png"}'
    )
    urls = pp.extract_image_urls(html)
    assert "https://thumbnail7.coupangcdn.com/thumbnails/a1.jpg" in urls
    assert "https://thumbnail8.coupangcdn.com/thumbnails/a2.jpg" in urls
    assert "https://shop-phinf.pstatic.net/main/b1.png" in urls


def test_more_mall_cdns_and_junk_filter():
    html = ('<img src="https://gdimg.gmarket.co.kr/goods/300001.jpg">'
            '<img src="https://sitem.ssgcdn.com/12/34/item.jpg">'
            '<img src="https://cdn.011st.com/11st/prod/99.png">'
            '<img src="https://image.auction.co.kr/itemimage/x.webp">'
            '<img src="https://thumbnail1.coupangcdn.com/common/logo.png">')
    urls = pp.extract_image_urls(html)
    hosts = " ".join(urls)
    for h in ("gdimg.gmarket.co.kr", "sitem.ssgcdn.com", "cdn.011st.com",
              "image.auction.co.kr"):
        assert h in hosts, hosts
    assert "logo" not in hosts                       # 정크 필터 유지


def test_browser_retry_when_few_images_and_merge(monkeypatch):
    """직접 요청이 1장이면 브라우저로 재시도하고 두 결과를 합친다 (v0.97은 0장만)."""
    direct = ('<html><meta property="og:title" content="무선 청소기">'
              '<meta property="og:image" content="https://thumbnail1.coupangcdn.com/t/main.jpg">'
              '<p>' + "설명 " * 20 + '</p></html>')
    dumped = ('<html><meta property="og:title" content="무선 청소기">'
              '<img src="https://thumbnail2.coupangcdn.com/t/g1.jpg">'
              '<img src="https://thumbnail3.coupangcdn.com/t/g2.jpg">'
              '<img src="https://thumbnail4.coupangcdn.com/t/g3.jpg"></html>')
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (direct, u))
    calls = []
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=50.0: (calls.append(u) or dumped))
    out = pp.collect_product("https://www.coupang.com/vp/products/1")
    assert calls, "1장인데 브라우저 재시도를 안 함"
    assert len(out["images"]) == 4                   # 합집합 (브라우저 3 + 직접 1)
    assert "https://thumbnail1.coupangcdn.com/t/main.jpg" in out["images"]
    assert out["via"] == "브라우저"


def test_browser_not_retried_when_enough_images(monkeypatch):
    """직접 요청으로 3장 이상이면 브라우저를 띄우지 않는다 (속도 유지)."""
    direct = ('<html><meta property="og:title" content="상품">'
              '<img src="https://thumbnail1.coupangcdn.com/t/1.jpg">'
              '<img src="https://thumbnail2.coupangcdn.com/t/2.jpg">'
              '<img src="https://thumbnail3.coupangcdn.com/t/3.jpg"></html>')
    monkeypatch.setattr(pp, "_fetch_html", lambda u, timeout=20.0: (direct, u))
    monkeypatch.setattr(pp, "_browser_dump",
                        lambda u, timeout=50.0: (_ for _ in ()).throw(AssertionError("불필요한 재시도")))
    out = pp.collect_product("https://www.coupang.com/vp/products/2")
    assert len(out["images"]) == 3 and out["via"] == "직접"


def test_shop_hook_always_visible_with_ai_suggest():
    """훅 입력이 대본 생성 전에도 보이고(미리보기 블록 밖) AI 추천이 달려 있다."""
    html = webui._HTML
    assert html.index('id="shopHook"') < html.index('id="shopPreview"')
    for tok in ("suggestShopHooks", 'id="shopHookCands"', "🪝 AI 추천",
                "후킹 문구 — 비우면 대본 만들 때 AI가 자동"):
        assert tok in html, tok
    # 직접 넣은 훅은 대본 생성이 덮어쓰지 않는다
    assert "if(!($('shopHook').value || '').trim())" in html
    # 시작 시 훅이 그대로 전달
    assert "hook: ($('shopHook')||{}).value || ''" in html
