"""v1.20.1 — 🖼 쿠팡 사진 수집을 **메인 썸네일 갤러리만**으로 (1·2번 7차).

> 회원님 스크린샷(2026-08-01): v1.20으로 연결은 성공해 사진 7장이 들어왔는데,
> 섬유유연제를 수집했더니 광고 배너·단백질·베개·폰(추천 상품)이 섞여 있었다.
> "이건 밑으로 내려가서 그런 거 같은데 — 썸네일만 크롤링하게."

원인: 페이지 **전체**에서 쿠팡 CDN 주소를 다 긁었다 — 아래쪽 "함께 본 상품"
추천 위젯과 광고 배너도 같은 CDN을 쓴다. 구분 기준은 크기 세그먼트:
갤러리는 레일 48x48ex·본이미지 492x492ex, 추천은 230x230ex 등, 광고는
/image/ads/ 경로. 갤러리 패턴이 확실히 잡히면(2장 이상) 그것만 쓴다.
"""

from cutdaejang import __version__
from cutdaejang.tools import coupang_api
from cutdaejang.tools import product_page as pp

COUPANG = "https://www.coupang.com/vp/products/123"

RAIL = [f"//thumbnail{9 - i}.coupangcdn.com/thumbnails/remote/48x48ex/image/retail"
        f"/images/prod_{i}.jpg" for i in range(7)]
MAIN = ["//thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/image/retail"
        f"/images/prod_{i}.jpg" for i in range(3)]          # 레일과 같은 사진(중복)
RECO = [f"//thumbnail3.coupangcdn.com/thumbnails/remote/230x230ex/image/retail"
        f"/images/other_{i}.jpg" for i in range(4)]         # "함께 본 상품" (다른 상품!)
ADS = ["//image8.coupangcdn.com/image/ads/banner/mega_week.jpg",
       "//thumbnail2.coupangcdn.com/thumbnails/remote/492x492ex/image/ads/promo.jpg"]


def _page() -> str:
    tags = "".join(f"<img src='{u}'>" for u in RAIL + MAIN + RECO + ADS)
    return ("<html><head><title>스너글 섬유유연제 4L</title>"
            "<meta property='og:title' content='스너글 섬유유연제 4L'>"
            "<meta property='og:image' content='https://thumbnail7.coupangcdn.com"
            "/thumbnails/remote/492x492ex/image/retail/images/prod_0.jpg'>"
            "<meta property='og:description' content='아기 옷에도 쓰는 부드러운 섬유유연제입니다'>"
            "</head><body>" + tags + "</body></html>")


def test_version():
    assert __version__ == "1.22.0"


def test_coupang_gallery_only_no_ads_no_recommendations():
    imgs = pp.extract_image_urls(_page(), base_url=COUPANG)
    assert len(imgs) == 7                                   # 갤러리 7장 그대로
    assert all("/492x492ex/" in u for u in imgs)            # 레일(48px)은 큰 사이즈로
    assert [u.rsplit("/", 1)[1] for u in imgs] == [
        f"prod_{i}.jpg" for i in range(7)]                  # 갤러리 순서 유지
    assert not any("other_" in u or "/ads/" in u for u in imgs)


def test_parse_product_og_image_dedup():
    """og:image(대표 사진)가 갤러리 1번과 같은 사진이면 두 번 넣지 않는다."""
    p = pp.parse_product(_page(), base_url=COUPANG)
    assert p["title"] == "스너글 섬유유연제 4L"
    assert len(p["images"]) == 7
    assert p["images"][0].endswith("prod_0.jpg")


def test_gallery_scoping_is_coupang_only():
    """다른 몰 주소면 예전 방식 그대로 — 없던 것보다 나빠지지 않게."""
    imgs = pp.extract_image_urls(_page(), base_url="https://www.gmarket.co.kr/item/1")
    assert any("other_" in u for u in imgs)                 # 일반 수집은 전체를 훑는다


def test_gallery_fallback_when_not_found():
    """갤러리 패턴이 없으면(모바일 등) 기존 수집이 그대로 돈다."""
    html = ("<html><body>" + "".join(
        f"<img src='//thumbnail1.coupangcdn.com/thumbnails/remote/700x700ex"
        f"/image/retail/images/m_{i}.jpg'>" for i in range(4)) + "</body></html>")
    imgs = pp.extract_image_urls(html, base_url=COUPANG)
    assert len(imgs) == 4                                   # 폴백이 살아 있다


def test_canon_urls_still_upgrade_to_hires():
    u = pp._coupang_canon(
        "https://thumbnail9.coupangcdn.com/thumbnails/remote/48x48ex"
        "/image/retail/images/prod_1.jpg")
    assert "/492x492ex/" in u
    assert "/1024x1024ex/" in coupang_api.hi_res_image(u)   # 내려받을 땐 고화질로
