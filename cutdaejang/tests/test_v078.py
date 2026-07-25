"""v0.78 — 🔗 /api/fetch_url 백그라운드 수집 + 🔊 script_tts(대본 읽어주기) E2E."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v078")
    iso = tmp_path_factory.mktemp("iso78")
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
    os.environ.pop("GEMINI_API_KEY", None)


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _state(base):
    with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
        return json.loads(r.read())


def _wait_status(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _state(base)
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
        time.sleep(1.0)
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


# ── /api/fetch_url — 수집은 monkeypatch, AI는 무키 → 원문 폴백 ────


def test_fetch_url_endpoint_fills_result(server, tmp_path, monkeypatch):
    import cutdaejang.tools.fetch_web as fw

    img1 = tmp_path / "img_01.jpg"
    img1.write_bytes(b"\xff\xd8\xff" + b"x" * 20_000)

    def fake_fetch(url, dest_dir, timeout=20.0, max_images=20, progress_cb=None):
        assert url == "https://m.blog.naver.com/abc/223344"  # normalize_url 적용 확인
        if progress_cb:
            progress_cb("사진 받는 중…")
        return {"title": "가짜 글", "text": "첫 문장입니다. 둘째 문장이에요. 셋째 갑니다.",
                "images": [str(img1)], "links": ["https://coupa.ng/x"],
                "source_url": url, "notes": []}

    monkeypatch.setattr(fw, "fetch_article", fake_fetch)
    d = _post(server, "/api/fetch_url", {"url": "https://blog.naver.com/abc/223344"})
    assert d.get("ok"), d
    for _ in range(40):
        t = _state(server).get("weblink_fetch") or {}
        if not t.get("running"):
            break
        time.sleep(0.25)
    assert not t.get("running") and not t.get("error"), t
    r = t.get("result") or {}
    assert r["title"] == "가짜 글" and r["images"] == [str(img1)]
    assert r["links"] == ["https://coupa.ng/x"]
    # 무키 → 원문 문장 폴백 대본 + 안내 노트
    assert r["script_lines"] and r["script_lines"][0].startswith("첫 문장")
    assert any("원문 문장" in n for n in r["notes"])


def test_fetch_url_rejects_bad_url(server):
    d = _post(server, "/api/fetch_url", {"url": "자바스크립트:alert(1)"})
    assert "error" in d


def test_weblink_error_reported(server, monkeypatch):
    import cutdaejang.tools.fetch_web as fw

    def boom(url, dest_dir, timeout=20.0, max_images=20, progress_cb=None):
        raise ValueError("쿠팡 상품 페이지는 프로그램 접근을 막고 있어요 — 테스트")

    monkeypatch.setattr(fw, "fetch_article", boom)
    d = _post(server, "/api/fetch_url", {"url": "https://www.coupang.com/vp/1"})
    assert d.get("ok")
    for _ in range(40):
        t = _state(server).get("weblink_fetch") or {}
        if not t.get("running"):
            break
        time.sleep(0.25)
    assert "쿠팡" in (t.get("error") or ""), t


# ── 폼 요소 존재 (평가된 JS 문법은 test_v0743의 node 검사로 커버) ──


def test_html_has_weblink_and_script_tts_ui():
    html = webui._HTML
    for tok in ('id="weblinkUrl"', 'id="weblinkBtn"', 'id="weblinkProdBtn"',
                'id="weblinkHint"', 'id="scriptTtsChk"', "loadWeblink", "saveWeblinkProduct"):
        assert tok in html, tok
    assert "script_tts" in html  # startEdit payload에 포함


# ── 🔊 script_tts — 사진+대본을 목소리로 (stub TTS 폴백 체인) ─────


@requires_ffmpeg
def test_script_tts_photo_narration_e2e(server, tmp_path):
    from cutdaejang.utils import ffmpeg as ff

    for i, color in enumerate(("navy", "gray"), 1):
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=360x640:d=0.1",
                "-frames:v", "1", str(tmp_path / f"p{i}.png")])
    photos = ";".join(str(tmp_path / f"p{i}.png") for i in (1, 2))

    data = _post(server, "/api/edit", {
        "photo_path": photos, "photo_sec": 4, "layout": "shorts",
        "script": "첫 번째 소개 문장입니다\n두 번째 핵심 문장이에요\n마지막 정리 문장입니다",
        "script_tts": True, "quality": "draft",
    })
    job = _wait_status(server, data["job_id"], {"review_subtitle", "failed"}, timeout=180)
    assert job["status"] == "review_subtitle", job.get("errors")
    assert len(job["subtitles"]) == 3
    # 게이트 확인: script_tts → 내레이션(TTS) 켜짐
    assert job.get("edit_params", {}).get("narration") is True, job.get("edit_params")

    _post(server, "/api/edit_render", {"job_id": data["job_id"],
                                       "subtitles": job["subtitles"], "hook": ""})
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"}, timeout=300)
    assert done["status"] == "ok", done.get("errors")
    # 목소리가 실렸는지 — 무음이 아니어야 함 (stub TTS 사인파)
    assert ff.has_audio_stream(done["mp4"])
    out = ff.run([ff.ffmpeg_bin(), "-i", done["mp4"], "-af", "volumedetect",
                  "-f", "null", "-"])
    import re as _re
    err = out.stderr.decode("utf-8", "replace")
    m = _re.search(r"mean_volume:\s*(-?[\d.]+) dB", err)
    assert m and float(m.group(1)) > -50, err[-400:]


@requires_ffmpeg
def test_script_without_tts_stays_silent_gate(server, tmp_path):
    """반례: script_tts 없이 대본만 → narration 게이트 꺼짐 (기존 동작 유지)."""
    from cutdaejang.utils import ffmpeg as ff

    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=teal:s=360x640:d=0.1",
            "-frames:v", "1", str(tmp_path / "q.png")])
    data = _post(server, "/api/edit", {
        "photo_path": str(tmp_path / "q.png"), "photo_sec": 3, "layout": "shorts",
        "script": "자막만 넣는 문장입니다",
    })
    job = _wait_status(server, data["job_id"], {"review_subtitle", "failed"}, timeout=180)
    assert job["status"] == "review_subtitle", job.get("errors")
    assert job.get("edit_params", {}).get("narration") is False, job.get("edit_params")
