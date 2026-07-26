"""v0.84 — 🎥 풀영상 하나로: 구간 범위 선택 + 자동 나누기(비율·장면 스냅) + 미리보기."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v084_ui_present_and_wired():
    html = webui._HTML
    for tok in ('name="secSrcMode"', 'id="secFullBox"', 'id="secPlayer"',
                'id="secFullPath"', "function applySecMode", "function parseMMSS",
                "function suggestSecRanges", "function loadFullVideo",
                "/api/reg_video", "/api/suggest_ranges", "full_video",
                "sec-start", "sec-end", "여기부터", "여기까지"):
        assert tok in html, tok


def test_partition_by_weights_units():
    from cutdaejang.core.video_editor import partition_by_weights

    S = 1_000_000
    # 비율 분할 (100초를 1:1:2로)
    r = partition_by_weights(100 * S, [1, 1, 2])
    assert r == [(0, 25 * S), (25 * S, 50 * S), (50 * S, 100 * S)]
    # 경계가 장면 전환점 가까이면 스냅 (25초 → 26초, 관대한 30% 안)
    r = partition_by_weights(100 * S, [1, 1, 2], scenes_us=[26 * S])
    assert r[0][1] == 26 * S and r[1] == (26 * S, 50 * S)
    # 멀면 스냅 안 함
    r = partition_by_weights(10 * S, [1, 1], scenes_us=[100_000])
    assert r == [(0, 5 * S), (5 * S, 10 * S)]
    # 항상 연속·단조 (합이 전체를 덮음)
    r = partition_by_weights(30 * S, [3, 1, 1, 5])
    assert r[0][0] == 0 and r[-1][1] == 30 * S
    for (a, b), (c, d) in zip(r, r[1:]):
        assert b == c and a <= b <= c <= d


@requires_ffmpeg
def test_extract_segment(tmp_path):
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "full.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=orange:s=320x240:r=30:d=12",
            "-f", "lavfi", "-i", "sine=frequency=500:duration=12",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(src)])
    out = video_editor.extract_segment(str(src), 4_000_000, 8_000_000,
                                       str(tmp_path / "seg.mp4"))
    dur = ff.probe_duration_us(out) / 1e6
    assert 3.7 <= dur <= 4.3, dur
    assert not ff.has_audio_stream(out)      # 소리는 내레이션이 대체
    assert ff.probe_video_size(out) == (320, 240)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v084")
    iso = tmp_path_factory.mktemp("iso84")
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


def _wait_status(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


def _two_part_video(tmp_path):
    """앞 6초 빨강 + 뒤 6초 파랑 — 6초 지점에 또렷한 장면 전환."""
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    for p, c in ((a, "red"), (b, "blue")):
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={c}:s=640x360:r=30:d=6",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                str(p)])
    full = tmp_path / "full.mp4"
    video_editor.concat_videos([str(a), str(b)], str(full))
    return str(full)


@requires_ffmpeg
def test_reg_video_and_localvideo_route(server, tmp_path):
    full = _two_part_video(tmp_path)
    d = _post(server, "/api/reg_video", {"path": full})
    assert d.get("ok") and d.get("token"), d
    assert 11.0 <= d["duration_s"] <= 13.0
    # Range 요청 → 206 부분 응답 (플레이어 탐색바용)
    req = urllib.request.Request(server + "/localvideo/" + d["token"],
                                 headers={"Range": "bytes=0-99"})
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.status == 206
        assert len(r.read()) == 100
    # 등록 안 된 토큰은 404
    try:
        urllib.request.urlopen(server + "/localvideo/ffffffffffff", timeout=30)
        raise AssertionError("404이어야 함")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    # 없는 경로 등록은 친절한 오류
    d2 = _post(server, "/api/reg_video", {"path": str(tmp_path / "없음.mp4")})
    assert "error" in d2


@requires_ffmpeg
def test_suggest_ranges_snaps_to_scene(server, tmp_path):
    full = _two_part_video(tmp_path)
    d = _post(server, "/api/suggest_ranges", {"video_path": full,
                                              "weights": [45, 55]})
    assert d.get("ok"), d
    assert len(d["ranges"]) == 2
    (s1, e1), (s2, e2) = d["ranges"]
    assert s1 == 0 and abs(e2 - d["total_us"]) < 1_000
    # 비율 경계(5.4초)가 장면 전환(≈6초)으로 스냅됨
    if d.get("snapped"):
        assert 5_500_000 <= e1 <= 6_600_000, e1
    assert e1 == s2


@requires_ffmpeg
def test_sections_full_video_e2e(server, tmp_path):
    """풀영상 1개 + 구간 2개(시간 범위) → 잘라서 조립·타임라인까지."""
    from cutdaejang.utils import ffmpeg as ff

    full = _two_part_video(tmp_path)
    data = _post(server, "/api/section_edit", {
        "full_video": full,
        "sections": [
            {"title": "도입", "start_us": 0, "end_us": 6_000_000,
             "narration": "첫 구간 소개 문장입니다"},
            {"title": "마무리", "start_us": 6_000_000, "end_us": 12_000_000,
             "narration": "둘째 구간 정리 문장이에요"},
        ],
        "layout": "wide", "quality": "draft",
    })
    assert data.get("job_id"), data
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done.get("mp4")
    from pathlib import Path
    job_dir = Path(done["mp4"]).parent
    assert (job_dir / "sec_1_src.mp4").exists()   # 풀영상에서 잘라낸 조각
    assert (job_dir / "sec_2_src.mp4").exists()
    chapters = (done.get("chapters") or "").splitlines()
    assert len(chapters) == 2 and "도입" in chapters[0] and "마무리" in chapters[1]
    # 범위가 빠지면 친절한 오류
    d2 = _post(server, "/api/section_edit", {
        "full_video": full,
        "sections": [{"narration": "시간 없는 구간"}],
    })
    assert "시간 범위" in d2.get("error", "")
