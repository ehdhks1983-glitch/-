"""v1.01 — 🎙→📃 목소리 → 대본 따오기 (사용자 요청 "목소리를 대본으로 따와야지").

받아적기(영상 제작의 부산물)가 아니라 대본 추출이 목적인 전용 기능:
영상·녹음 파일 → 발화 구간 전사 → (키 있으면) 오인식 교정 → 한 줄 = 한 문장
대본. 구간 대본·AI 영상 카드로 바로 보내 옛 완성본 재제작·대본 재활용에 쓴다.
"""

import json
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

    workdir = tmp_path_factory.mktemp("ui-v101")
    iso = tmp_path_factory.mktemp("iso101")
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


def _wait(base, job_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            st = json.loads(r.read())
        j = next((x for x in st.get("jobs", []) if x.get("id") == job_id), {})
        if j.get("status") in {"ok", "partial", "failed"}:
            return j
        time.sleep(0.4)
    raise AssertionError(f"{job_id} 미완료")


@requires_ffmpeg
def test_rip_script_from_video(server, tmp_path):
    """말소리 든 영상 → 대본 텍스트 (stub STT) + 대본.txt 저장."""
    from cutdaejang.utils import ffmpeg as ff

    base, workdir = server
    clip = tmp_path / "talk.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=navy:s=320x180:r=30:d=2",
            "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(clip)])
    d = _post(base, "/api/rip_script", {"path": str(clip), "stt_provider": "stub"})
    assert d.get("job_id"), d
    job = _wait(base, d["job_id"])
    assert job["status"] == "ok", job.get("errors")
    assert "샘플자막" in (job.get("script") or "")
    assert job.get("script_raw")                     # 원문도 함께 보관
    txt = Path(workdir) / d["job_id"] / "대본.txt"
    assert txt.is_file() and "샘플자막" in txt.read_text(encoding="utf-8")


@requires_ffmpeg
def test_rip_script_from_audio_only_file(server, tmp_path):
    """녹음 파일(wav)만 넣어도 대본이 나온다 — 영상 없이 오디오 단독 지원."""
    from cutdaejang.utils import ffmpeg as ff

    base, _ = server
    wav = tmp_path / "memo.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-ar", "24000", str(wav)])
    d = _post(base, "/api/rip_script", {"path": str(wav), "stt_provider": "stub"})
    assert d.get("job_id"), d
    job = _wait(base, d["job_id"])
    assert job["status"] == "ok", job.get("errors")
    assert "샘플자막" in (job.get("script") or "")


def test_rip_script_rejects_bad_input(server):
    base, _ = server
    assert "error" in _post(base, "/api/rip_script", {"path": ""})
    assert "error" in _post(base, "/api/rip_script", {"path": "C:/없는파일.mp4"})


def test_rip_ui_wiring():
    """전용 화면·보내기 버튼·카드 전환 숨김 배선."""
    html = webui._HTML
    for tok in ('id="ripCard"', 'id="ripPath"', 'id="ripOut"', 'id="ripRefine"',
                "function openRip", "function closeRip", "function startRip",
                "function watchRip", "function sendRip", "function downloadRip",
                "/api/rip_script", "대본 따오기",
                "pickInto(event,'ripPath','video')", "pickInto(event,'ripPath','audio')",
                "sendRip(event,'sections')", "sendRip(event,'gen')"):
        assert tok in html, tok
    src = open(webui.__file__, encoding="utf-8").read()
    assert "_queue_job(job_id, _run_rip_script" in src   # 📋 작업 큐 경유 (병렬 한도)
    body = src.split("def _run_rip_script")[1].split("\ndef ")[0]
    assert "transcribe_segments_timed" in body           # STT 신호등(락) 걸린 경로
    assert "is_hallucination" in body                    # '음악'류 환각 제외
    assert "refine_subtitles" in body and "lines = raw" in body  # 다듬기 실패 폴백
