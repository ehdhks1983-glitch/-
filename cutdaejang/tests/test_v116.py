"""v1.16 — 🎞 구간 순서 이동(⬆⬇) + 무나레이션 구간 통과 (회원님 리포트 21번).

> "구간이 4개로 나눠졌어. 앞에 영상을 넣고 싶어서 아래에서 구간 넣고 옮기고
>  해서 만들었는데 이상하게 만들어져."

원인 2개: ① 순서 이동 버튼이 없어 칸(6개)을 손으로 하나씩 옮기다 꼬였고,
② 내레이션이 빈 구간(인트로 클립)은 **조용히 버려져** 최종 영상에서 사라졌다.
→ ⬆⬇ 버튼은 행(칸 전부)을 통째로 옮기고, 무나레이션 구간은 클립 길이 그대로
   화면만 들어간다(소리 없음 · BGM/화면 자막은 적용 · 완료 안내에 표시).
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang import __version__
from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_version():
    assert __version__ == "1.27.0"


# ── ⬆⬇ 순서 이동 — 행을 통째로 옮긴다 ───────────────────────────
def test_move_buttons_present_and_move_whole_row():
    html = webui._HTML
    for tok in ("sec-up", "sec-down", "이 구간을 위로 (내용 전부 함께 이동)",
                "이 구간을 아래로 (내용 전부 함께 이동)",
                "rows.insertBefore(div, prev)", "rows.insertBefore(nx, div)"):
        assert tok in html, tok
    # 옮긴 순서가 임시 저장에도 바로 반영된다
    assert html.count("JSON.stringify({draft: collectSecDraft()})") >= 2


# ── 🔇 무나레이션 구간 — 버리지 않고 클립 그대로 ─────────────────
def test_collect_keeps_clip_only_sections():
    html = webui._HTML
    assert "s.narration.trim() || s.video_path" in html      # JS 수집 필터
    assert "내레이션(또는 클립)을 넣어주세요" in html
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    # 라우트·실행부 둘 다 클립/범위만 있는 구간을 인정
    assert src.count('or str((s or {}).get("video_path") or "").strip()') >= 1
    assert src.count('or str(s.get("video_path") or "").strip()') >= 1
    # 무나레이션이면 클립 길이 그대로 (예전 1초 폴백 금지)
    assert "if not narr_end:" in src and "narr_end = dur" in src
    assert "silent_secs" in src
    assert "내레이션 없이 클립 화면만 그대로 들어갔어요" in src


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("v116-jobs")
    iso = tmp_path_factory.mktemp("iso116")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
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
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _wait(base, job_id, targets, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        for j in st.get("jobs", []):
            if j.get("id") == job_id and j.get("status") in targets:
                return j
    raise AssertionError(f"작업 {job_id} 이 {targets} 에 도달하지 못함")


@requires_ffmpeg
def test_intro_clip_without_narration_e2e(server, tmp_path):
    """앞 구간 = 클립만(무나레이션), 뒤 구간 = 내레이션 — 인트로가 사라지지 않는다."""
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i, (color, sec) in enumerate([("navy", 4), ("olive", 5)]):
        c = tmp_path / f"c{i}.mp4"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={sec}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                str(c)])
        clips.append(str(c))
    data = _post(server, "/api/section_edit", {
        "sections": [
            {"title": "인트로", "video_path": clips[0], "narration": "",
             "caption": "구독과 좋아요"},                    # 💬 무낭독 카드는 그대로
            {"title": "본편", "video_path": clips[1],
             "narration": "본편을 소개하는 문장입니다"},
        ],
        "layout": "wide", "quality": "draft",
    })
    assert data.get("job_id"), data                    # 무나레이션 구간이 있어도 접수
    done = _wait(server, data["job_id"], {"ok", "partial", "failed"})
    assert done["status"] == "ok", done.get("errors")
    # 인트로(4초)가 통째로 살아 있어야 한다 — 예전엔 조용히 사라지거나 1초로 압축
    total = ff.probe_duration_us(done["mp4"]) / 1e6
    assert total >= 4 + 2, total
    chapters = (done.get("chapters") or "").splitlines()
    assert len(chapters) == 2 and "인트로" in chapters[0]
    m, s = chapters[1].split()[0].split(":")
    assert 3 <= int(m) * 60 + int(s) <= 6              # 본편 시작 ≈ 인트로 길이(4초)
    assert "내레이션 없이 클립 화면만" in (done.get("tts_warn") or "")
