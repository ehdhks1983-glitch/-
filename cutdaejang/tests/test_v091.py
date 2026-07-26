"""v0.91 — 📷 쇼핑 사진 대량 가져오기 (페이지 복사·붙여넣기 + 스크린샷 붙여넣기)."""

import base64
import json
import re
import threading
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui


def test_v091_ui_present_and_wired():
    html = webui._HTML
    for tok in (
        # 📋 페이지 조각 붙여넣기 → 사진 URL 추출 → 서버 다운로드
        "function shopPasteHandler", "function extractImgUrls", "function fetchShopImages",
        "/api/shop_images",
        # 📸 스크린샷 클립보드 붙여넣기
        "function uploadPastedImage", "/api/shop_upload",
        # 미리보기·관리
        'id="shopPhotoPrev"', "function renderShopPhotoPrev", "function addShopPhotos",
        "function clearShopPhotos", "사진 비우기", "사진 한꺼번에 넣기",
    ):
        assert tok in html, tok
    # 붙여넣기 리스너는 쇼핑 카드가 보일 때만 동작
    assert "addEventListener('paste'" in html


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v091")
    iso = tmp_path_factory.mktemp("iso91")
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


def test_shop_images_downloads_hi_res_and_skips_icons(server, monkeypatch):
    from cutdaejang.tools import fetch_web

    big_png = b"\x89PNG\r\n\x1a\n" + b"0" * 20000
    icon = b"\x89PNG\r\n\x1a\n" + b"0" * 100          # 12KB 미만 → 아이콘 취급
    tried = []

    def fake_fetch(url, **kw):
        tried.append(url)
        if "icon" in url:
            return icon
        return big_png

    monkeypatch.setattr(fetch_web, "fetch_bytes", fake_fetch)
    urls = [
        "https://thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/image/retail/a.jpg",
        "https://thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/image/retail/a.jpg",  # 중복
        "https://shopping-phinf.pstatic.net/main_1/b.jpg?type=f300",
        "https://cdn.example.com/icon-cart.png",
    ]
    d = _post(server, "/api/shop_images", {"urls": urls})
    assert d.get("ok"), d
    assert len(d["images"]) == 2                        # 중복 1 제거, 아이콘 1 스킵
    assert d["skipped"] == 1
    assert d["images"][0].endswith("img_01.png") and d["images"][1].endswith("img_02.png")
    route = re.compile(r"^/weblink/[0-9a-f]{8}/img_\d{2}\.(?:jpg|jpeg|png|webp|bmp)$")
    assert all(route.match(p) for p in d["previews"]), d["previews"]
    assert "1024x1024ex" in tried[0]                    # 쿠팡 썸네일은 고화질 먼저
    assert any("b.jpg" in t and "type=f300" not in t for t in tried)   # 네이버 축소 파라미터 제거
    # 미리보기 GET도 실제로 열린다
    with urllib.request.urlopen(server + d["previews"][0], timeout=30) as r:
        assert r.read()[:8] == b"\x89PNG\r\n\x1a\n"
    # 사진 주소가 하나도 없으면 안내 오류
    d2 = _post(server, "/api/shop_images", {"urls": ["data:image/png;base64,xx", ""]})
    assert "error" in d2


def test_shop_upload_saves_pasted_screenshot(server):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 500
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    d = _post(server, "/api/shop_upload", {"data": data_url})
    assert d.get("ok"), d
    assert d["images"][0].endswith(".png") and d["previews"][0].startswith("/weblink/")
    with urllib.request.urlopen(server + d["previews"][0], timeout=30) as r:
        assert r.read() == png
    # 이미지가 아니면 한국어 안내 오류
    bad = _post(server, "/api/shop_upload",
                {"data": base64.b64encode(b"hello world").decode()})
    assert "error" in bad
    empty = _post(server, "/api/shop_upload", {"data": ""})
    assert "error" in empty
