"""v0.80 — 🎞 구간 대본 영상: 대본 구간 나누기·N클립 합본·구간 조립 E2E."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.core.script_generator import split_script_sections
from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg

_SCRIPT = """# 가이드 대본

## 📋 촬영 전 준비
- [ ] 체크리스트 (내레이션 아님)

## 🎬 0. 훅 (0:00 ~ 0:20) — 제일 중요

**[화면]** 스케줄러 시작 장면

**[말]**
> "카페에 글 올리고, 댓글 달고… 몇 시간씩 쓰시죠?
> 이 프로그램은 켜두기만 하면 알아서 합니다."

**[자막]** `자동화`

## 🎬 1. 설치 (0:20 ~ 1:10)

**[말]**
> "설치는 간단합니다. Setup 파일을 실행하세요."

### 3-1. 라이선스 (1분)

**[말]**
> "첫째, 인증입니다."

**[말]** *(마무리)*
> "여기까지 하면 준비 끝입니다."
"""


# ── 대본 → 구간 나누기 (휴리스틱) ─────────────────────────────────


def test_split_sections_from_shooting_script():
    secs = split_script_sections(_SCRIPT)
    assert len(secs) == 3
    assert secs[0]["title"].startswith("0. 훅")
    assert "알아서 합니다" in secs[0]["narration"]
    # 화면 지시·자막·체크리스트는 안 들어감
    assert "스케줄러" not in secs[0]["narration"] and "체크리스트" not in secs[0]["narration"]
    # 같은 구간의 [말] 여러 블록은 합쳐짐
    assert "인증입니다" in secs[2]["narration"] and "준비 끝" in secs[2]["narration"]


def test_split_sections_plain_text_fallback():
    secs = split_script_sections("첫 문단 내용입니다 충분히 길게.\n\n둘째 문단도 있습니다 역시 길게.")
    assert len(secs) == 2
    assert secs[0]["title"] == "구간 1"


# ── concat_videos — 해상도·오디오 제각각 N개 합본 ─────────────────


@requires_ffmpeg
def test_concat_videos_mixed_sources(tmp_path):
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    a = tmp_path / "a.mp4"   # 320x240 + 오디오
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(a)])
    b = tmp_path / "b.mp4"   # 640x360 무음
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=1.5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(b)])
    c = tmp_path / "c.mp4"   # 360x640 세로 + 오디오
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=green:s=360x640:d=1",
            "-f", "lavfi", "-i", "sine=frequency=600:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(c)])
    out = tmp_path / "joined.mp4"
    video_editor.concat_videos([str(a), str(b), str(c)], str(out), size=(640, 360))
    assert ff.probe_video_size(str(out)) == (640, 360)
    assert ff.has_audio_stream(str(out))
    dur = ff.probe_duration_us(str(out)) / 1e6
    assert 4.0 <= dur <= 5.2, dur   # 2 + 1.5 + 1 = 4.5초 근처


def test_concat_videos_empty_raises(tmp_path):
    from cutdaejang.core import video_editor

    with pytest.raises(ValueError):
        video_editor.concat_videos([], str(tmp_path / "x.mp4"))


# ── 서버 픽스처 ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v080")
    iso = tmp_path_factory.mktemp("iso80")
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


def _wait_status(base, job_id, targets, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
        time.sleep(1.0)
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


# ── /api/section_split — 무키 휴리스틱 (무네트워크) ──────────────


def test_section_split_endpoint(server):
    d = _post(server, "/api/section_split", {"script_text": _SCRIPT})
    assert d.get("ok"), d
    assert len(d["sections"]) == 3
    assert "알아서 합니다" in d["sections"][0]["narration"]


def test_section_split_empty_text(server):
    d = _post(server, "/api/section_split", {"script_text": " "})
    assert "error" in d


def test_section_edit_validation(server):
    d = _post(server, "/api/section_edit", {"sections": []})
    assert "error" in d
    d2 = _post(server, "/api/section_edit",
               {"sections": [{"narration": "안녕", "video_path": ""}]})
    assert "클립" in d2.get("error", "")


# ── 🎞 구간 조립 E2E — 압축 + 내레이션 길이 + 합본 ────────────────


@requires_ffmpeg
def test_sections_e2e(server, tmp_path):
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i, color in enumerate(("red", "navy"), 1):   # 각 8초 — 내레이션(약 5초)보다 김 → 압축 경로
        p = tmp_path / f"clip{i}.mp4"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d=8",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p)])
        clips.append(str(p))

    data = _post(server, "/api/section_edit", {
        "sections": [
            {"title": "훅", "video_path": clips[0],
             "narration": "첫 구간 소개 문장입니다\n조금 더 이어지는 말이에요"},
            {"title": "본론", "video_path": clips[1],
             "narration": "둘째 구간 핵심 문장입니다\n마무리 정리 문장이에요"},
        ],
        "layout": "wide", "quality": "draft",
    })
    assert data.get("job_id"), data
    done = _wait_status(server, data["job_id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    assert done.get("mp4")
    # 합본 = 구간 2개: 각 구간이 원본 8초가 아니라 내레이션 길이(~5초 내외)로 압축됨
    dur = ff.probe_duration_us(done["mp4"]) / 1e6
    assert 6 <= dur <= 15, dur          # 8+8=16초 원본이 그대로면 실패
    assert ff.has_audio_stream(done["mp4"])
    out = ff.run([ff.ffmpeg_bin(), "-i", done["mp4"], "-af", "volumedetect",
                  "-f", "null", "-"])
    import re as _re
    err = out.stderr.decode("utf-8", "replace")
    m = _re.search(r"mean_volume:\s*(-?[\d.]+) dB", err)
    assert m and float(m.group(1)) > -50, err[-300:]   # 내레이션 소리 존재
    # 구간별 중간 산출물 + 안내 문구
    from pathlib import Path
    job_dir = Path(done["mp4"]).parent
    assert (job_dir / "sec_1.mp4").exists() and (job_dir / "sec_2.mp4").exists()
    assert "구간 2개" in (done.get("tts_warn") or "")


def test_section_card_ui_present():
    html = webui._HTML
    for tok in ('id="sectionCard"', 'id="secRows"', 'id="secScriptText"',
                "openMode('sections')", "startSectionsSafe", "addSectionRow",
                "구간 대본 영상"):
        assert tok in html, tok
    assert html.count('class="modecard"') == 5
