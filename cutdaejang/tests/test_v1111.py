"""v1.11.1 — 확정 원인 4건 수정.

회원님 리포트에서 원인이 코드로 확정된 것만 모아 고쳤다:
  ③ 쇼핑커넥트 버튼이 존재하지 않는 도메인을 열었다 (DNS NXDOMAIN)
  ⑥ 연속 낭독 블록이 바뀔 때 ElevenLabs 음높이가 리셋됐다 (140→169→195Hz)
  ⑪ naver.me 단축링크가 쇼핑 링크로 인식되지 않아 사진 수집이 아예 안 돌았다
  ⑬ 구간 영상이 4K→1080p→4K를 왕복해 전체 인코딩이 3회였다 (3분 영상 45분)
  ⑭ 마지막 단계가 98%에 박혀 멈춘 것처럼 보였다 (⑬과 함께 나가야 체감된다)
"""

import inspect
import re

from cutdaejang import __version__
from cutdaejang.core import edit_mode, tts_engine, video_editor
from cutdaejang.gui import webui
from cutdaejang.tools import fetch_web, product_page


def test_version():
    assert __version__ == "1.22.1"


# ── ③ 외부 링크 ────────────────────────────────────────────────
def test_dead_shopping_connect_url_is_gone():
    """존재하지 않던 도메인으로 다시는 사용자를 보내지 않는다 (회귀 봉인)."""
    html = webui._apply_links(webui._HTML)
    assert "shoppingconnect.naver.com" not in html
    assert webui.EXT_LINKS["naver_shopping_connect"] == "https://brandconnect.naver.com"
    assert "shoppingconnect.naver.com" not in "".join(webui.EXT_LINKS.values())


def test_all_external_links_come_from_one_table():
    """화면의 모든 바깥 링크가 EXT_LINKS 안에 있어야 한다 — 하드코딩 재발 차단."""
    html = webui._apply_links(webui._HTML)
    assert "{{LINK:" not in html, "치환되지 않은 링크 토큰이 남았다"
    hosts = set(re.findall(r'href="https?://([^/"]+)', html))
    allowed = {re.sub(r"^https?://([^/]+).*", r"\1", u) for u in webui.EXT_LINKS.values()}
    assert hosts <= allowed, f"목록 밖 링크: {sorted(hosts - allowed)}"
    for url in webui.EXT_LINKS.values():
        assert url.startswith(("https://", "http://")) and " " not in url


# ── ⑪ 단축링크 ────────────────────────────────────────────────
def test_host_lists_have_one_source():
    """목록이 두 군데로 갈라져 생긴 사고 — 다시 갈라지면 여기서 깨진다."""
    assert product_page._SHOP_HOSTS is fetch_web.SHOP_HOSTS
    assert product_page._SHORT_HOSTS is fetch_web.SHORTENER_HOSTS
    # naver.me는 블로그 공유에도 쓰여 '상품'으로 단정하면 안 된다
    assert "naver.me" not in fetch_web.SHOP_HOSTS
    assert "naver.me" in fetch_web.SHORTENER_HOSTS
    assert not product_page.is_shop_url("https://mycoupang.com/x")   # 점 경계
    assert product_page.is_shop_url("https://smartstore.naver.com/a/products/1")


def test_resolve_shop_url_touches_network_only_for_shorteners(monkeypatch):
    """블로그·일반 링크는 네트워크를 한 번도 열지 않아야 한다."""
    def boom(*a, **k):
        raise AssertionError("단축 도메인이 아닌데 열어봤다")
    monkeypatch.setattr(product_page, "_landing_url", boom)
    assert product_page.resolve_shop_url("https://blog.naver.com/x/1") == ""
    assert product_page.resolve_shop_url("https://example.com/a") == ""
    assert product_page.resolve_shop_url("") == ""
    # 이미 쇼핑 호스트면 원본 그대로 (파트너스 추적 링크 보존)
    assert product_page.resolve_shop_url(
        "https://link.coupang.com/a/xyz") == "https://link.coupang.com/a/xyz"


def test_shortlink_repointed_to_real_product(monkeypatch):
    """naver.me가 상품으로 착지하면 그 주소를, 블로그면 빈 문자열을 돌려준다."""
    monkeypatch.setattr(product_page, "_landing_url",
                        lambda u, timeout=8.0: "https://smartstore.naver.com/s/products/9")
    assert product_page.resolve_shop_url("https://naver.me/FQu2awsL").startswith(
        "https://smartstore.naver.com")
    monkeypatch.setattr(product_page, "_landing_url",
                        lambda u, timeout=8.0: "https://m.blog.naver.com/x/1")
    assert product_page.resolve_shop_url("https://naver.me/FQu2awsL") == ""
    monkeypatch.setattr(product_page, "_landing_url", lambda u, timeout=8.0: "")
    assert product_page.resolve_shop_url("https://naver.me/FQu2awsL") == ""


def test_naver_images_without_extension_are_collected():
    """스마트스토어 사진은 확장자 없이 ?type=w860만 붙는 주소가 흔하다."""
    html = (
        '<img src="https://shop-phinf.pstatic.net/20260101_1/abcd_01?type=w860">'
        '<img src="https://shop-phinf.pstatic.net/20260101_2/efgh.jpg">'
        '<img src="https://storep-phinf.pstatic.net/sticker_01?type=w80">'
        '<img src="https://ssl.pstatic.net/static/icon.png">')
    urls = product_page.extract_image_urls(html, base_url="https://smartstore.naver.com/x")
    assert any("abcd_01" in u for u in urls), "확장자 없는 상품 사진을 놓쳤다"
    assert any("efgh.jpg" in u for u in urls)
    assert not any("storep-phinf" in u or "ssl.pstatic.net" in u for u in urls), \
        "스티커·아이콘 CDN이 상품 사진으로 섞였다"


def test_zero_photos_is_never_silent():
    """사진 0장이어도 대본은 만들되(폴백 유지), 화면에 이유를 반드시 남긴다."""
    assert product_page.photo_note({"images": ["x"]}) == ""
    note = product_page.photo_note({"images": [], "via_detail": "직접 0장 · 브라우저 차단"})
    assert "못 찾았" in note and "직접 0장" in note
    # _usable의 관대함(사진 0장도 통과)은 의도된 것 — 대본을 잃지 않기 위해 유지
    assert product_page._usable({"title": "상품", "text": "설" * 30, "images": []})


def test_webui_uses_resolved_shop_url():
    body = inspect.getsource(webui._fetch_weblink_bg)
    assert "shop_url = product_page.resolve_shop_url(url)" in body
    assert "if shop_url:" in body and "elif shop_url:" in body
    assert "product_page.is_shop_url(url)" not in body, "옛 판정이 남아 있다"
    assert "collect_product(shop_url" in body      # 단축 주소가 아니라 실제 상품 주소로
    assert body.count("사진 주소") >= 2             # (가)/(나) 구분 안내


# ── ⑥ 목소리 톤 ───────────────────────────────────────────────
def test_elevenlabs_pins_seed_and_context():
    """블록이 바뀌어도 같은 화자·음높이가 되도록 seed를 고정한다."""
    p = tts_engine.ElevenLabsTTS(api_key="k")
    assert p.wants_context is True
    assert isinstance(p.seed, int) and p.seed > 0, "시드가 고정돼 있지 않다"
    assert f"seed{p.seed}" in p.cache_extra, "시드가 캐시 키에 반영되지 않으면 옛 소리가 재생된다"
    src = inspect.getsource(tts_engine.ElevenLabsTTS)
    assert '"seed"' in src and "previous_request_ids" in src


def test_continuity_block_keeps_one_breath_for_short_videos():
    """1~2분 영상은 블록 1개로 — 경계 자체가 없으면 톤도 안 튄다."""
    assert tts_engine.CONTINUITY_MAX_SENTENCES >= 40
    blocks = tts_engine.continuity_blocks(["짧은 문장입니다."] * 40)
    assert len(blocks) == 1, f"40문장이 {len(blocks)}블록으로 쪼개졌다"


# ── ⑬ 4K 왕복 ────────────────────────────────────────────────
def test_section_render_is_1080p_and_final_is_4k():
    """구간은 1080p로 굽고 최종만 4K — 왕복 리샘플 제거의 수치 고정선."""
    assert edit_mode.BASE_QUALITY["ultra"] == "_ultra_base"
    q = edit_mode.QUALITY_PRESETS["_ultra_base"]
    assert q["mult"] == 1.0 and q["sharpen"] is False

    def canvas(layout, w, h, quality):
        c, *_ = edit_mode._quality_canvas(layout, w, h, quality)
        return (c.w, c.h)

    assert canvas("wide", 1920, 1080, "_ultra_base") == (1920, 1080)
    assert canvas("shorts", 1080, 1920, "_ultra_base") == (1080, 1920)
    # 최종 산출물은 지금과 똑같이 4K여야 한다 (회원님 유튜브 노출 요건)
    assert canvas("keep", 1920, 1080, "ultra") == (3840, 2160)
    assert canvas("keep", 1080, 1920, "ultra") == (2160, 3840)


def test_single_section_keeps_native_resolution():
    """구간이 1개면 합치기(다운스케일)가 없다 — 그 경로는 4K 그대로 둬야 한다."""
    body = inspect.getsource(webui._run_sections)
    assert "if len(secs) > 1 else quality" in body, \
        "구간 1개까지 1080p로 떨어뜨리면 원본 4K가 파괴된다"
    assert "quality=sec_quality" in body          # 구간 렌더
    assert "quality=quality" in body              # 최종 패스는 그대로 4K


def test_concat_crf_is_tied_to_the_same_decision():
    body = inspect.getsource(webui._run_sections)
    assert "crf=(17 if sec_quality != quality else 19)" in body
    sig = inspect.signature(video_editor.concat_videos)
    assert sig.parameters["crf"].default == 19    # 다른 호출부는 동작 불변


def test_reuse_fingerprint_invalidated_only_for_changed_quality():
    body = inspect.getsource(webui._run_sections)
    assert "secmult" in body and "if sec_quality != quality else \"\"" in body, \
        "4K로 구운 옛 구간이 섞여 들어오면 화질 단차가 생긴다"


# ── ⑭ 진행률 ─────────────────────────────────────────────────
def test_final_pass_owns_half_the_progress_bar():
    """가장 오래 걸리는 단계가 98%에 눌려 있으면 멈춘 걸로 보인다."""
    body = inspect.getsource(webui._run_sections)
    assert "frac=0.50" in body and "0.50 + f * 0.47" in body
    assert "멈춘 게 아닙니다" in body
    assert "frac=min(0.989, 0.975" not in body, "옛 98% 고정 구간이 남아 있다"
    assert "* 0.45" in body                       # 구간 렌더는 앞 45%
    assert "1080p 합본으로 저장했어요" in body      # 4K 실패 시 해상도 강등 고지
