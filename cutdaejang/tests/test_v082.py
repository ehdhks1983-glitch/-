"""v0.82 — 🎞 구간 편집기: 예상 시간 표시 + 구간별 배속 + 완성 후 타임라인."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v082_ui_present_and_wired():
    html = webui._HTML
    for tok in (
        # ⏱ 예상 시간 (구간 행) + 전체 예상
        "sec-time", 'id="secTotal"', "function updateSectionTimes", "function fmtMMSS",
        # ⏩ 구간별 배속 셀렉트 + payload
        "sec-speed", "핵심 몽타주", "배속으로 통째로 맞춤",
        "sec-speed')||{}).value",
        # ⏱ 완성 후 유튜브 설명란용 타임라인
        'id="chaptersBox"', 'id="chaptersText"', "function copyChapters",
        "job.chapters",
    ):
        assert tok in html, tok
    # 내레이션 입력마다 실시간 갱신(+v1.13 칸 자동 늘어남) + 행 추가/삭제 시 갱신
    assert "na.oninput = function(){ updateSectionTimes(); autoGrow(na); }" in html
    assert html.count("updateSectionTimes()") >= 1


@requires_ffmpeg
def test_speed_video_2x(tmp_path):
    """8초 클립 2배속 → 4초 근처·무음·해상도 유지."""
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "src.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=teal:s=320x240:r=30:d=8",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(src)])
    out = video_editor.speed_video(str(src), 2.0, str(tmp_path / "x2.mp4"))
    dur = ff.probe_duration_us(out) / 1e6
    assert 3.6 <= dur <= 4.5, dur
    assert ff.probe_video_size(out) == (320, 240)
    assert not ff.has_audio_stream(out)      # 소리는 내레이션이 대체 — 무음이어야 함


@requires_ffmpeg
def test_speed_video_clamps_extreme_factor(tmp_path):
    """비정상 배속값은 0.25~8배로 클램프 (100배 요청 → 8배)."""
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "src.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=30:d=8",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(src)])
    out = video_editor.speed_video(str(src), 100.0, str(tmp_path / "x8.mp4"))
    dur = ff.probe_duration_us(out) / 1e6
    assert 0.8 <= dur <= 1.4, dur            # 8초/8배 = 1초 근처


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v082")
    iso = tmp_path_factory.mktemp("iso82")
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


def _wait_status(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


@requires_ffmpeg
def test_sections_speed_and_chapters_e2e(server, tmp_path):
    """구간 2개(첫째 2배속) → 완성 + 유튜브 설명란용 타임라인 생성."""
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i, (color, sec) in enumerate([("navy", 8), ("olive", 4)]):
        c = tmp_path / f"c{i}.mp4"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={sec}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                str(c)])
        clips.append(str(c))
    data = _post(server, "/api/section_edit", {
        "sections": [
            {"title": "인트로", "video_path": clips[0], "speed": "2",
             "narration": "첫 구간을 소개하는 문장입니다"},
            {"title": "핵심 정리", "video_path": clips[1],
             "narration": "둘째 구간 마무리 문장이에요"},
        ],
        "layout": "wide", "quality": "draft",
    })
    assert data.get("job_id"), data
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done.get("mp4")
    # ⏱ 타임라인: 구간 수만큼, 00:00 시작, 제목 포함
    chapters = (done.get("chapters") or "").splitlines()
    assert len(chapters) == 2, done.get("chapters")
    assert chapters[0].startswith("00:00") and "인트로" in chapters[0]
    assert "핵심 정리" in chapters[1]
    # 둘째 구간 시작(=첫 구간 길이)은 첫 내레이션 길이 근처 (몇 초 내)
    m, s = chapters[1].split()[0].split(":")
    assert 1 <= int(m) * 60 + int(s) <= 20
    # ⏩ 배속 클립이 실제로 만들어져 파이프라인에 쓰임
    from pathlib import Path
    job_dir = Path(done["mp4"]).parent
    assert (job_dir / "sec_1_spd.mp4").exists()
    from cutdaejang.utils import ffmpeg as ff2
    spd_dur = ff2.probe_duration_us(str(job_dir / "sec_1_spd.mp4")) / 1e6
    assert 3.6 <= spd_dur <= 4.5, spd_dur    # 8초 원본 ÷ 2배속
