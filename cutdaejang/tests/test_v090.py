"""v0.90 — 🔀 동시 작업 N개 + 🛒 쇼핑 검색 링크 가드·고화질 사진 + 📱 완성→쇼츠/편집."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui


def test_v090_ui_present_and_wired():
    html = webui._HTML
    for tok in (
        # 🔀 동시 작업 개수 조절
        'id="parallelSel"', "function setParallel", "function syncParallelSel",
        "/api/parallel", "동시 1개 (순서대로)", "동시 4개 (고사양)",
        # ⏱ 경과 시간 표시
        # v1.28.0: "N분 경과" → fmtDur로 "45초/3분/1시간 5분" + 남은 시간까지 같이 표시
        "t_start", "' 경과'", "남은 시간 약 ",
        # 🛒 검색창 링크 가드
        "function shopUrlGuard", "shopUrlGuard('cpKeyword')", "shopUrlGuard('nvKeyword')",
        # 📱 완성 → 쇼츠/편집 보내기
        "function sendDoneToEdit", "📱 쇼츠로 만들기", "✂ 이 영상 편집",
        "_lastDoneJob",
    ):
        assert tok in html, tok
    # 쇼츠 보내기는 세로 + 완전 자동(여러 개 나누기)을 추천 기본으로 세팅
    assert "autoMultiSel" in html and "autoTargetSec" in html


def test_parallel_limit_reads_settings(monkeypatch):
    from cutdaejang import config

    monkeypatch.setattr(config, "load_settings",
                        lambda *a, **k: {"ui": {"parallel_jobs": 3}})
    webui._PLIMIT_CACHE.update(t=0.0)          # 캐시 무효화
    assert webui._parallel_limit() == 3
    monkeypatch.setattr(config, "load_settings",
                        lambda *a, **k: {"ui": {"parallel_jobs": 99}})
    webui._PLIMIT_CACHE.update(t=0.0)
    assert webui._parallel_limit() == 4        # 상한 4
    monkeypatch.setattr(config, "load_settings",
                        lambda *a, **k: {"ui": {"parallel_jobs": 0}})
    webui._PLIMIT_CACHE.update(t=0.0)
    assert webui._parallel_limit() == 2        # 0·빈값 → 기본 2
    monkeypatch.setattr(config, "load_settings", lambda *a, **k: {})
    webui._PLIMIT_CACHE.update(t=0.0)
    assert webui._parallel_limit() == 2
    webui._PLIMIT_CACHE.update(t=0.0, n=2)     # 다른 테스트에 영향 없게 복원


def test_queue_runs_two_at_a_time(monkeypatch):
    """동시 한도 2 → 3개를 걸면 2개가 '겹쳐서' 돌고(병렬), 3개를 넘진 않는다."""
    monkeypatch.setattr(webui, "_parallel_limit", lambda: 2)
    webui._ensure_queue_worker()
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "done": 0}
    done_evt = threading.Event()

    def work(jid):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.7)
        with lock:
            state["active"] -= 1
            state["done"] += 1
            if state["done"] == 3:
                done_evt.set()
        webui._set_job(jid, status="ok")       # 가짜 작업 뒷정리

    for i in range(3):
        webui._queue_job(f"par90-{i}", work, f"par90-{i}")
    assert done_evt.wait(20), state
    assert state["peak"] == 2, state           # 1(직렬)도 3(초과)도 아닌 정확히 2


def test_hi_res_image_urls():
    from cutdaejang.tools import coupang_api, naver_shop_api

    u = ("https://thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/"
         "image/retail/images/123.jpg")
    assert coupang_api.hi_res_image(u) == (
        "https://thumbnail7.coupangcdn.com/thumbnails/remote/1024x1024ex/"
        "image/retail/images/123.jpg")
    # ex 없는 크기 세그먼트도 교체, 쿠팡 CDN이 아니면 그대로
    assert "/1024x1024ex/" in coupang_api.hi_res_image(
        "https://t2.coupangcdn.com/thumbnails/remote/230x230/image/a.jpg")
    plain = "https://example.com/a.jpg"
    assert coupang_api.hi_res_image(plain) == plain
    # 네이버: ?type=f300 축소 파라미터 제거, 그 외 URL은 그대로
    n = "https://shopping-phinf.pstatic.net/main_1/2.jpg?type=f300"
    assert naver_shop_api.hi_res_image(n) == "https://shopping-phinf.pstatic.net/main_1/2.jpg"
    keep = "https://shopping-phinf.pstatic.net/main_1/2.jpg"
    assert naver_shop_api.hi_res_image(keep) == keep
    assert naver_shop_api.hi_res_image("https://other.com/i.jpg?type=f300") == \
        "https://other.com/i.jpg?type=f300"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v090")
    iso = tmp_path_factory.mktemp("iso90")
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
    webui._PLIMIT_CACHE.update(t=0.0, n=2)     # 다음 테스트를 위해 기본값 복원


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_parallel_endpoint(server):
    d = _post(server, "/api/parallel", {"n": 3})
    assert d.get("ok") and d.get("n") == 3
    assert webui._PLIMIT_CACHE["n"] == 3       # 대기 중 작업에도 즉시 반영
    with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    assert (st["settings"].get("ui") or {}).get("parallel_jobs") == 3
    d2 = _post(server, "/api/parallel", {"n": 99})
    assert d2.get("ok") and d2.get("n") == 4   # 상한 4로 잘라 저장
    d3 = _post(server, "/api/parallel", {"n": "abc"})
    assert "error" in d3


def test_coupang_pick_prefers_hi_res(server, monkeypatch):
    """상품 선택 시 고화질 후보(1024px)를 먼저 시도하고, 실패하면 원본으로 폴백."""
    from cutdaejang.tools import fetch_web

    tried = []
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 500

    def fake_fetch(url, **kw):
        tried.append(url)
        if "1024x1024ex" in url:
            raise OSError("고화질 없음")       # 폴백 확인용
        return png

    monkeypatch.setattr(fetch_web, "fetch_bytes", fake_fetch)
    d = _post(server, "/api/coupang_pick", {
        "name": "무선 물걸레 청소기", "price": 257090, "rocket": True,
        "image": ("https://thumbnail7.coupangcdn.com/thumbnails/remote/"
                  "492x492ex/image/retail/images/wd01.png"),
        "url": "https://www.coupang.com/vp/products/9999",
        "category": "가전 > 청소기"})
    assert d.get("ok"), d
    assert "1024x1024ex" in tried[0]           # 고화질 먼저
    assert "492x492ex" in tried[-1]            # 실패 시 원본 폴백
    assert len(d["images"]) == 1
    assert "로켓배송" in d["paste_text"] and "257,090" in d["paste_text"]
