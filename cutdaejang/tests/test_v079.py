"""v0.79 — 🔗 전용 탭·사진 미리보기·중복 제거·📸 사진-문장 싱크 재배치."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.core.video_editor import photo_sentence_spans
from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v079")
    iso = tmp_path_factory.mktemp("iso79")
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
    os.environ.pop("GEMINI_API_KEY", None)


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _wait_status(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
        time.sleep(1.0)
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


# ── 📸 사진 ↔ 문장 매핑 (순수 함수) ───────────────────────────────


def test_spans_one_to_one():
    starts = [0, 2_000_000, 4_000_000]
    assert photo_sentence_spans(3, starts, 6_000_000) == [
        (0, 2_000_000), (1, 2_000_000), (2, 2_000_000)]


def test_spans_first_block_covers_leadin():
    """첫 사진은 0초부터 (첫 문장이 0.5초에 시작해도 검은 화면 없이)."""
    spans = photo_sentence_spans(2, [500_000, 3_000_000], 6_000_000)
    assert spans == [(0, 3_000_000), (1, 3_000_000)]
    assert sum(d for _, d in spans) == 6_000_000


def test_spans_fewer_images_group_blocks():
    starts = [0, 1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000]
    spans = photo_sentence_spans(3, starts, 6_000_000)
    assert [i for i, _ in spans] == [0, 1, 2]
    assert [d for _, d in spans] == [2_000_000, 2_000_000, 2_000_000]


def test_spans_more_images_than_sentences():
    spans = photo_sentence_spans(8, [0, 1_000_000, 2_000_000], 3_000_000)
    assert [i for i, _ in spans] == list(range(8))  # 뒤 사진도 버리지 않고 전부 사용
    assert all(d >= 333_333 for _, d in spans)
    assert sum(d for _, d in spans) == 3_000_000


def test_spans_empty_inputs():
    assert photo_sentence_spans(0, [0], 1_000_000) == []
    assert photo_sentence_spans(3, [], 1_000_000) == []


# ── 🔗 전용 탭 UI + /weblink/ 미리보기 서빙 ───────────────────────


def test_weblink_card_ui_present():
    html = webui._HTML
    for tok in ('id="weblinkCard"', 'id="wlGrid"', 'id="wlScript"', 'id="wlHook"',
                'id="wlVoiceSel"', 'id="wlGoBtn"', "openMode('weblink')",
                "startWeblinkSafe", "initWeblinkCard", "블로그 글로 만들기"):
        assert tok in html, tok
    # 사진 폼의 옛 파란 상자는 제거 (전용 탭으로 이동)
    assert html.count('id="weblinkUrl"') == 1


def test_weblink_preview_route(server):
    base, workdir = server
    from pathlib import Path

    d = Path(workdir) / "weblink" / "ab12cd34"
    d.mkdir(parents=True, exist_ok=True)
    (d / "img_01.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 500)
    with urllib.request.urlopen(base + "/weblink/ab12cd34/img_01.jpg", timeout=10) as r:
        assert r.status == 200 and r.read()[:3] == b"\xff\xd8\xff"
    # 화이트리스트 밖(경로 주입·다른 파일명)은 404
    for bad in ("/weblink/ab12cd34/../../settings.json", "/weblink/ab12cd34/evil.py",
                "/weblink/zzzz/img_01.jpg"):
        try:
            code = urllib.request.urlopen(base + bad, timeout=10).status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 404, bad


# ── 📸 사진-문장 싱크 E2E — 재배치 영상으로 전 사진 반영·길이 일치 ──


@requires_ffmpeg
def test_photo_sentence_sync_e2e(server, tmp_path):
    from pathlib import Path

    from cutdaejang.utils import ffmpeg as ff

    base, workdir = server
    for i, color in enumerate(("red", "blue", "green"), 1):
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=360x640:d=0.1",
                "-frames:v", "1", str(tmp_path / f"s{i}.png")])
    photos = ";".join(str(tmp_path / f"s{i}.png") for i in (1, 2, 3))

    data = _post(base, "/api/edit", {
        "photo_path": photos, "photo_sec": 60,   # 일부러 크게 어긋난 예상 길이
        "layout": "shorts", "quality": "draft",
        "script": "빨강 사진 문장입니다\n파랑 사진 문장이에요\n초록 사진 문장입니다",
        "script_tts": True,
    })
    job = _wait_status(base, data["job_id"], {"review_subtitle", "failed"}, timeout=180)
    assert job["status"] == "review_subtitle", job.get("errors")

    _post(base, "/api/edit_render", {"job_id": data["job_id"],
                                     "subtitles": job["subtitles"], "hook": ""})
    done = _wait_status(base, data["job_id"], {"ok", "partial", "failed"}, timeout=300)
    assert done["status"] == "ok", done.get("errors")
    # 재배치 확인: 안내 문구 + photo_sync.mp4 생성 + 60초 예상치가 아닌 내레이션 길이
    assert "타이밍에 맞춰 배치" in (done.get("tts_warn") or ""), done.get("tts_warn")
    assert (Path(workdir) / data["job_id"] / "photo_sync.mp4").exists()
    dur_s = ff.probe_duration_us(done["mp4"]) / 1e6
    assert dur_s < 40, dur_s  # 예상 60초로 만들었어도 내레이션 길이로 재구성됨
