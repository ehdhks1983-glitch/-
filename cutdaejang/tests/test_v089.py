"""v0.89 — 🛒 쇼핑 상품 영상 전용 카드 (쿠팡 파트너스 + 네이버 쇼핑커넥트)."""

import io
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v089_ui_present_and_wired():
    html = webui._HTML
    for tok in (
        # 6번째 홈 카드 + 전용 카드
        "openMode('shop')", 'id="shopCard"', "쇼핑 상품 영상",
        # 쿠팡 블록(이전됨) + 네이버 블록
        'id="cpKeyword"', 'id="nvKeyword"', 'id="nvResults"',
        "function naverSearch", "function saveNaverKeys",
        "/api/naver_search", "/api/naver_keys",
        # 공통 흐름
        'id="shopPasteText"', "function makeShopScript", "function startShop",
        "function pickShopPhotos", 'id="shopLinkInput"', 'id="shopThemeSel"',
        "function initShopCard",
    ):
        assert tok in html, tok
    assert html.count('class="modecard"') == 6
    # 블로그 카드에는 쇼핑 검색 UI가 더 이상 없음 (전용 카드로 이전)
    wl = html.split('id="weblinkCard"')[1].split('id="sectionCard"')[0]
    assert "cpKeyword" not in wl
    assert "쇼핑 상품 영상" in wl        # 대신 안내 문구


def test_naver_shop_search_parses_and_errors(monkeypatch):
    from cutdaejang.tools import naver_shop_api as na

    fake = {"items": [
        {"title": "<b>무선</b> 선풍기 A", "lprice": "29900",
         "image": "https://shopping-phinf.pstatic.net/img1.jpg",
         "link": "https://search.shopping.naver.com/gate?id=1",
         "mallName": "쿨링몰", "category1": "디지털/가전", "category2": "계절가전",
         "category3": "선풍기"},
        {"title": "선풍기 B", "lprice": "abc", "image": "", "link": "", "mallName": ""},
    ]}

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(na.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(json.dumps(fake).encode()))
    items = na.search_shop("선풍기", "CID", "CSEC")
    assert len(items) == 2
    assert items[0]["name"] == "무선 선풍기 A"          # <b> 태그 제거
    assert items[0]["price"] == 29900
    assert items[0]["category"] == "디지털/가전 > 계절가전 > 선풍기"
    assert items[0]["mall"] == "쿨링몰"
    assert items[1]["price"] == 0                       # 이상한 가격은 0
    # 키 없으면 발급 안내
    with pytest.raises(na.NaverShopError) as ei:
        na.search_shop("선풍기", "", "")
    assert "developers.naver.com" in str(ei.value)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v089")
    iso = tmp_path_factory.mktemp("iso89")
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
    for env in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        os.environ.pop(env, None)


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_naver_keys_endpoint(server):
    d0 = _post(server, "/api/naver_search", {"keyword": "선풍기"})
    assert "error" in d0 and "developers.naver.com" in d0["error"]   # 키 없음 안내
    d = _post(server, "/api/naver_keys", {"client_id": "CID", "client_secret": "CSEC"})
    assert d.get("ok") and d.get("has")
    with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    assert st["keys"]["naver"] is True


@requires_ffmpeg
def test_shop_flow_e2e(server, tmp_path):
    """붙여넣기 → AI 대본(스텁) → 사진 1장으로 /api/edit 완주 (쇼핑 카드 흐름)."""
    from cutdaejang.utils import ffmpeg as ff

    photo = tmp_path / "p.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=coral:s=640x360:d=1",
            "-frames:v", "1", str(photo)])
    pasted = ("무선 선풍기 A. 바람 세기 4단계로 책상에서 쓰기 좋아요. "
              "한 번 충전으로 12시간 사용. 접이식이라 캠핑에도 좋습니다.")
    d = _post(server, "/api/fetch_url", {"pasted_text": pasted})
    assert d.get("ok"), d
    t0, t = time.time(), {}
    while time.time() - t0 < 60:
        with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
            t = json.loads(r.read()).get("weblink_fetch") or {}
        if not t.get("running"):
            break
        time.sleep(0.5)
    lines = (t.get("result") or {}).get("script_lines") or []
    assert lines, t
    d2 = _post(server, "/api/edit", {
        "photo_path": str(photo), "photo_sec": 12, "layout": "shorts",
        "quality": "draft", "script": "\n".join(lines[:4]), "script_tts": True,
        "auto_subtitle": False, "cut_silence": False})
    assert d2.get("job_id"), d2
    t0 = time.time()
    while time.time() - t0 < 300:
        with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        j = next((x for x in st.get("jobs", []) if x.get("id") == d2["job_id"]), {})
        if j.get("status") in ("ok", "partial", "failed"):
            assert j["status"] == "ok", j.get("errors")
            assert j.get("mp4")
            return
        time.sleep(1)
    raise AssertionError("쇼핑 흐름 작업이 끝나지 않음")
