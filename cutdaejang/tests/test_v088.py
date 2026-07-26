"""v0.88 — 📋 작업 큐(순차 실행·대기 취소) + 🛒 쿠팡 파트너스 API."""

import datetime
import io
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v088_ui_present_and_wired():
    html = webui._HTML
    for tok in ('id="jobsBar"', "function renderJobsBar", "function watchJob",
                "function cancelQueued", "/api/cancel_queued",
                'id="cpKeyword"', 'id="cpResults"', "function coupangSearch",
                "function coupangPick", "function saveCoupangKeys",
                "/api/coupang_search", "/api/coupang_pick"):
        assert tok in html, tok
    src = open(webui.__file__, encoding="utf-8").read()
    assert src.count("_queue_job(") >= 10       # 정의 1 + 호출 9곳 (무거운 작업 전부)
    assert "threading.Thread(target=_run_generate" not in src
    assert "threading.Thread(target=_run_sections" not in src


def test_cea_signature_deterministic():
    from cutdaejang.tools import coupang_api

    auth = coupang_api.cea_authorization(
        "GET", "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search",
        "keyword=%EC%84%A0%ED%92%8D%EA%B8%B0&limit=8", "AKEY", "SKEY",
        now=datetime.datetime(2026, 7, 26, 3, 4, 5))
    assert "CEA algorithm=HmacSHA256" in auth
    assert "access-key=AKEY" in auth
    assert "signed-date=260726T030405Z" in auth
    sig = auth.split("signature=")[1]
    assert len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)
    # 같은 입력 → 같은 서명 (결정적)
    assert auth == coupang_api.cea_authorization(
        "GET", "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search",
        "keyword=%EC%84%A0%ED%92%8D%EA%B8%B0&limit=8", "AKEY", "SKEY",
        now=datetime.datetime(2026, 7, 26, 3, 4, 5))


def test_coupang_search_parses_and_errors(monkeypatch):
    from cutdaejang.tools import coupang_api

    fake = {"rCode": "0", "data": {"productData": [
        {"productName": "무선 선풍기 A", "productPrice": 29900,
         "productImage": "https://cdn/img1.jpg",
         "productUrl": "https://link.coupang.com/re/AFF1", "isRocket": True,
         "categoryName": "가전"},
        {"productName": "선풍기 B", "productPrice": "15900",
         "productImage": "", "productUrl": "https://link.coupang.com/re/AFF2"},
    ]}}

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(coupang_api.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(json.dumps(fake).encode()))
    items = coupang_api.search_products("선풍기", "AK", "SK")
    assert len(items) == 2
    assert items[0]["name"] == "무선 선풍기 A" and items[0]["price"] == 29900
    assert items[0]["rocket"] and items[1]["price"] == 15900
    # 키 없으면 발급 안내
    with pytest.raises(coupang_api.CoupangError) as ei:
        coupang_api.search_products("선풍기", "", "")
    assert "Open API" in str(ei.value)
    # 응답 rCode 오류 → 한국어 오류
    bad = {"rCode": "401", "rMessage": "Invalid signature"}
    monkeypatch.setattr(coupang_api.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(json.dumps(bad).encode()))
    with pytest.raises(coupang_api.CoupangError):
        coupang_api.search_products("선풍기", "AK", "SK")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v088")
    iso = tmp_path_factory.mktemp("iso88")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"

    httpd = webui.create_server(str(workdir), port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", str(workdir)
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


def _job(base, job_id):
    with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    return next((j for j in st.get("jobs", []) if j.get("id") == job_id), {})


def _wait(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = _job(base, job_id)
        if j.get("status") in targets:
            return j
        time.sleep(0.5)
    raise AssertionError(f"{job_id} 이 {targets} 에 도달하지 못함: {_job(base, job_id)}")


def _mk_clip(tmp_path, name, color, sec=4):
    from cutdaejang.utils import ffmpeg as ff

    p = tmp_path / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={sec}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(p)])
    return str(p)


@requires_ffmpeg
def test_queue_sequential_and_cancel_e2e(server, tmp_path):
    """작업 2개 연달아 시작 → 둘째는 '대기 중'으로 큐에 → 순서대로 완성.
    셋째는 대기 중에 취소 → 실행되지 않음."""
    base, _ = server
    clip = _mk_clip(tmp_path, "q.mp4", "teal")

    def start(narr):
        d = _post(base, "/api/section_edit", {
            "sections": [{"video_path": clip, "narration": narr}],
            "layout": "wide", "quality": "draft"})
        assert d.get("job_id"), d
        return d["job_id"]

    j1 = start("첫 작업 문장입니다")
    j2 = start("둘째 작업 문장이에요")
    j3 = start("셋째 작업 문장인데요")
    # 워커는 1개 — 뒤 작업들은 대기열에
    s2 = _job(base, j2).get("status")
    s3 = _job(base, j3).get("status")
    assert "queued" in (s2, s3), (s2, s3)
    # 셋째는 대기 중 취소
    d = _post(base, "/api/cancel_queued", {"job_id": j3})
    assert d.get("ok"), d
    assert _job(base, j3).get("status") == "cancelled"
    # 앞 둘은 순서대로 완성
    assert _wait(base, j1, {"ok", "partial", "failed"})["status"] == "ok"
    assert _wait(base, j2, {"ok", "partial", "failed"})["status"] == "ok"
    time.sleep(1.0)
    assert _job(base, j3).get("status") == "cancelled"   # 취소된 건 끝까지 실행 안 됨
    # 진행 중(running) 취소는 거절
    d2 = _post(base, "/api/cancel_queued", {"job_id": j1})
    assert "error" in d2


def test_coupang_pick_endpoint(server, monkeypatch):
    """상품 선택 → 사진 저장 + 미리보기 라우트 + 붙여넣기 문구 (딥링크 실패 시 원 링크)."""
    base, workdir = server
    from cutdaejang.tools import fetch_web

    png = (b"\x89PNG\r\n\x1a\n" + b"0" * 500)
    monkeypatch.setattr(fetch_web, "fetch_bytes", lambda url, **kw: png)
    d = _post(base, "/api/coupang_pick", {
        "name": "무선 선풍기 A", "price": 29900,
        "image": "https://cdn.example/img1.png",
        "url": "https://www.coupang.com/vp/products/123",
        "category": "가전"})
    assert d.get("ok"), d
    assert "무선 선풍기 A" in d["paste_text"] and "29,900" in d["paste_text"]
    assert d["link"].startswith("https://www.coupang.com")   # 키 없음 → 딥링크 실패 → 원 링크
    assert len(d["images"]) == 1 and d["images"][0].endswith("img_01.png")
    from pathlib import Path
    assert Path(d["images"][0]).is_file()
    with urllib.request.urlopen(base + d["previews"][0], timeout=30) as r:
        assert r.read(8) == b"\x89PNG\r\n\x1a\n"
    # 이름 없으면 오류
    d2 = _post(base, "/api/coupang_pick", {"name": ""})
    assert "error" in d2
