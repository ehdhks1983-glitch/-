"""v1.05 — 🛒 파트너스로 고른 상품도 링크 사진 수집 (사용자 리포트 "블로그는 5장인데").

진짜 원인: 파트너스 검색으로 상품을 고르면 상품 정보칸이 자동으로 채워지는데,
그 상태로 [🤖 대본 만들기]를 누르면 '붙여넣기 분기'가 링크 수집을 통째로
건너뛰어 v1.04의 수집 개선이 실행조차 안 됐다 → 붙여넣은 글 + 상품 링크가
같이 있으면 글은 그대로 쓰되 사진은 링크에서 수집해 합친다.
"""

from pathlib import Path

from cutdaejang.gui import webui
from cutdaejang.tools import product_page


def _run_bg(monkeypatch, tmp_path, url, pasted, collect=None, dl=None):
    if collect:
        monkeypatch.setattr(product_page, "collect_product", collect)
    if dl:
        monkeypatch.setattr(product_page, "download_images", dl)
    webui._WEBLINK_TASK.update(running=True, msg="", result=None, error="")
    webui._fetch_weblink_bg(url, str(tmp_path), 45, pasted_text=pasted)
    t = dict(webui._WEBLINK_TASK)
    assert not t["running"]
    return t


def test_pasted_plus_shop_link_collects_photos(monkeypatch, tmp_path):
    """붙여넣은 글 + 상품 링크 → 글은 그대로, 사진은 링크에서 수집·합류."""
    def fake_collect(url, progress_cb=None):
        return {"title": "무선 청소기", "text": "설명",
                "images": [f"https://thumbnail1.coupangcdn.com/t/{i}.jpg" for i in range(5)],
                "final_url": url, "via": "브라우저"}

    def fake_dl(urls, dest_dir, limit=12, min_bytes=12_000, **_kwargs):
        d = Path(dest_dir); d.mkdir(parents=True, exist_ok=True)
        out = []
        for i, _u in enumerate(urls[:limit], 1):
            p = d / f"img_{i:02d}.jpg"
            p.write_bytes(b"x" * 20)
            out.append(str(p))
        return out, 0

    t = _run_bg(monkeypatch, tmp_path,
                "https://link.coupang.com/re/AFFSDP?lptag=AF123&pageKey=1",
                "프리티케어 무선 청소기\n가격: 약 108,640원\n채워진 상품 정보입니다",
                collect=fake_collect, dl=fake_dl)
    assert t["error"] == "", t
    r = t["result"]
    assert len(r["images"]) == 5                       # 링크에서 수집된 사진
    assert "자동 수집" in " ".join(r["notes"])
    assert "프리티케어" in r["text"]                    # 붙여넣은 글은 그대로 대본 근거
    assert len(r["previews"]) == 5 and all(
        p.startswith("/weblink/") for p in r["previews"])


def test_pasted_plus_blocked_link_still_makes_script(monkeypatch, tmp_path):
    """링크 수집이 막혀도(차단) 붙여넣은 글로 대본은 만들어진다 + Ctrl+V 안내."""
    def blocked(url, progress_cb=None):
        raise product_page.ShopBlockedError("차단")

    t = _run_bg(monkeypatch, tmp_path,
                "https://www.coupang.com/vp/products/9",
                "상품 설명을 붙여넣은 글입니다. 특징이 많아요.",
                collect=blocked)
    assert t["error"] == "", t
    r = t["result"]
    assert r["images"] == []
    assert "Ctrl+V" in " ".join(r["notes"])            # 폴백 안내
    assert r["script_lines"], "글로는 대본이 나와야 함"


def test_pasted_without_link_unchanged(monkeypatch, tmp_path):
    """링크 없이 붙여넣기만 — 기존 동작 그대로 (수집 시도 안 함)."""
    def boom(url, progress_cb=None):
        raise AssertionError("링크가 없는데 수집을 시도함")

    t = _run_bg(monkeypatch, tmp_path, "", "그냥 붙여넣은 상품 설명입니다",
                collect=boom)
    assert t["error"] == "" and t["result"]["images"] == []


def test_front_merges_photos_not_replace():
    """수집 사진이 기존(파트너스 대표컷) 사진을 덮어쓰지 않고 합쳐진다."""
    html = webui._HTML
    for tok in ("window._shopPhotos.push(p)", "덮어쓰기 금지",
                "링크에서 ' + added + '장 추가됨"):
        assert tok in html, tok
    assert "window._shopPhotos = r.images.slice()" not in html
    # 백엔드: 붙여넣기 분기 안에 링크 수집 합류가 배선됨
    src = open(webui.__file__, encoding="utf-8").read()
    body = src.split("def _fetch_weblink_bg")[1].split("\ndef ")[0]
    assert body.count("collect_product") == 2          # 붙여넣기+링크 분기, 링크 단독 분기
    assert "수집기가 아예 안 돌았음" in body
