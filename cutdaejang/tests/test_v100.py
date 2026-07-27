"""v1.00 — 🎙 구간 영상을 다 합친 뒤 내레이션을 '한 트랙'으로 얹기 (사용자 제안 구조).

구간별로 목소리를 구우면 경계마다 톤 리셋·말 잘림이 생긴다는 사용자 진단:
"작업순서가 영상을 다합치고 그다음에 나래이션을 넣는방향으로해야할꺼같은데"
→ 구간 파일은 무음(화면·자막만)으로 렌더하고, 합본 전체 타임라인 위에
내레이션 트랙을 딱 한 번 얹는다. 경계에서 잘릴 소리 자체가 없다.
"""

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v100")
    iso = tmp_path_factory.mktemp("iso100")
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


def _wait(base, job_id, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        j = next((x for x in st.get("jobs", []) if x.get("id") == job_id), {})
        if j.get("status") in {"ok", "partial", "failed"}:
            return j
        time.sleep(0.5)
    raise AssertionError(f"{job_id} 미완료")


def _mk_clip(tmp_path, name, color, sec=3):
    from cutdaejang.utils import ffmpeg as ff

    p = tmp_path / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={sec}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(p)])
    return str(p)


def _mean_db(path, start=None, dur=None):
    """구간 평균 음량(dB). 완전 무음(-inf 등 숫자 없음)은 -120으로 취급."""
    from cutdaejang.utils import ffmpeg as ff

    af = "volumedetect" if start is None else f"atrim={start}:{start + dur},volumedetect"
    r = subprocess.run([ff.ffmpeg_bin(), "-i", str(path), "-af", af,
                        "-vn", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -120.0


@requires_ffmpeg
def test_sections_voice_is_one_track_over_joined_video(server, tmp_path):
    """구간 2개: 구간 파일은 무음, 최종 합본에만 목소리 — 이음새 양쪽 다 들린다."""
    base, _ = server
    a = _mk_clip(tmp_path, "a.mp4", "red")
    b = _mk_clip(tmp_path, "b.mp4", "blue")
    d = _post(base, "/api/section_edit", {
        "sections": [{"title": "도입", "video_path": a, "narration": "첫 구간 문장입니다"},
                     {"title": "정리", "video_path": b, "narration": "둘째 구간 문장이에요"}],
        "layout": "wide", "quality": "draft"})
    assert d.get("job_id"), d
    job = _wait(base, d["job_id"])
    assert job["status"] == "ok", job.get("errors")

    final = Path(job["mp4"])
    job_dir = final.parent
    # ① 최종 파일은 내레이션을 얹은 sections_voiced.mp4 — 다운로드 목록엔 이것 하나만
    assert final.name == "sections_voiced.mp4", final
    assert (job.get("mp4s") or []) == [str(final)]
    assert (job_dir / "narration_bed.wav").is_file()
    # ② 구간 파일엔 목소리가 없다 (무음 렌더 — 경계에서 잘릴 소리 자체가 없음)
    for k in (1, 2):
        sec = job_dir / f"sec_{k}.mp4"
        assert sec.is_file()
        assert _mean_db(sec) < -55, (k, _mean_db(sec))
    # ③ 합본에선 이음새 앞뒤 모두 목소리(스텁 톤)가 들린다 — 한 트랙이 관통
    #    (구간1 톤 ≈0.2~2.1초, 구간2 톤 ≈2.75~4.7초 — 스텁 길이 0.55+0.14×글자수)
    assert _mean_db(final, 0.4, 1.0) > -35, "구간1 내레이션이 합본에 없음"
    assert _mean_db(final, 3.0, 1.0) > -35, "구간2 내레이션이 합본에 없음"


@requires_ffmpeg
def test_single_section_also_gets_voiced_final(server, tmp_path):
    """구간이 1개여도(합치기 생략) 내레이션 얹기는 항상 수행된다."""
    base, _ = server
    clip = _mk_clip(tmp_path, "solo.mp4", "teal")
    d = _post(base, "/api/section_edit", {
        "sections": [{"video_path": clip, "narration": "혼자인 구간 문장입니다"}],
        "layout": "wide", "quality": "draft"})
    assert d.get("job_id"), d
    job = _wait(base, d["job_id"])
    assert job["status"] == "ok", job.get("errors")
    final = Path(job["mp4"])
    assert final.name == "sections_voiced.mp4", final
    assert _mean_db(final.parent / "sec_1.mp4") < -55
    assert _mean_db(final, 0.4, 1.0) > -35


def test_narration_last_wiring():
    """무음 구간 렌더 + 합본 1회 얹기 배선 — 구간 루프 안엔 내레이션이 없다."""
    src = open(webui.__file__, encoding="utf-8").read()
    body = src.split("def _run_sections")[1].split("\ndef ")[0]
    # 구간 렌더는 내레이션 없이(무음), 베드는 합본 뒤 딱 1회
    assert "narration_wav=None" in body
    assert body.count("build_narration_wav(") == 1
    assert body.index("concat_videos(") < body.index("build_narration_wav(")
    assert "sections_voiced" in body and "narration_bed" in body
    # 재사용 지문에 bed1 — 내레이션 구워진 옛(v0.99↓) 구간 재사용 차단
    assert "|bed1" in body
    # 얹기는 볼륨 무변경(normalize=0)·영상 재인코딩 없음(c:v copy)
    assert "amix=inputs=2:duration=first:normalize=0" in body
    assert '"copy"' in body
