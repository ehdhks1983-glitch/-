"""v0.83 — 구간 전환 크로스페이드 + 용량 줄이기 + 일레븐랩스 목소리 일관성."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cutdaejang.gui import webui
from tests.conftest import requires_ffmpeg


def test_v083_ui_present_and_wired():
    html = webui._HTML
    for tok in ('용량 줄이기', "function shrinkVideo", "/api/shrink",
                "shrink_status", "_업로드용"):
        assert tok in html, tok


def test_xfade_clamp_units():
    from cutdaejang.core.video_editor import xfade_clamp

    assert xfade_clamp(0.45, [8.0, 4.0]) == pytest.approx(0.45)
    assert xfade_clamp(0.45, [0.6, 8.0]) == pytest.approx(0.27)   # 짧은 클립의 45%
    assert xfade_clamp(0.0, [8.0, 8.0]) == 0.0
    assert xfade_clamp(0.45, [8.0]) == 0.0                        # 클립 1개 — 경계 없음
    assert xfade_clamp(0.45, [0.08, 8.0]) == 0.0                  # 너무 짧으면 하드컷
    assert xfade_clamp(5.0, [8.0, 8.0]) == pytest.approx(1.0)     # 최대 1초


def _make_clip(path, color, sec, size="320x240", freq=440):
    from cutdaejang.utils import ffmpeg as ff

    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=30:d={sec}",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={sec}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path)])
    return str(path)


@requires_ffmpeg
def test_concat_videos_crossfade_duration(tmp_path):
    """4초+4초를 0.5초 크로스페이드로 → 7.5초 근처 (하드컷이면 8초)."""
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    a = _make_clip(tmp_path / "a.mp4", "red", 4, freq=300)
    b = _make_clip(tmp_path / "b.mp4", "blue", 4, freq=800)
    out = video_editor.concat_videos([a, b], str(tmp_path / "x.mp4"),
                                     crossfade_s=0.5)
    dur = ff.probe_duration_us(out) / 1e6
    assert 7.2 <= dur <= 7.85, dur
    assert ff.has_audio_stream(out)
    assert ff.probe_video_size(out) == (320, 240)
    # crossfade_s=0 (기존 하드컷 경로)은 그대로 8초
    out2 = video_editor.concat_videos([a, b], str(tmp_path / "y.mp4"))
    assert 7.8 <= ff.probe_duration_us(out2) / 1e6 <= 8.4


@requires_ffmpeg
def test_mix_bgm_copies_video_stream(tmp_path):
    """BGM 입히기가 영상 스트림을 재인코딩하지 않고 그대로 복사하는지 검증."""
    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = _make_clip(tmp_path / "src.mp4", "green", 6, freq=500)
    bgm = tmp_path / "bgm.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=3",
            str(bgm)])                                # 3초 — 루프로 6초 채움
    out = video_editor.mix_bgm(src, str(bgm), str(tmp_path / "with.mp4"),
                               bgm_db=-16, duck=True)
    dur = ff.probe_duration_us(out) / 1e6
    assert 5.6 <= dur <= 6.4, dur
    assert ff.has_audio_stream(out)
    # 영상 비트스트림이 바이트 단위로 동일해야 함 (-c:v copy 증명)
    import hashlib
    def vhash(p):
        raw = tmp_path / (Path(p).stem + ".h264")
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(p),
                "-map", "0:v:0", "-c", "copy", str(raw)])
        return hashlib.md5(raw.read_bytes()).hexdigest()
    from pathlib import Path
    assert vhash(src) == vhash(out)


@requires_ffmpeg
def test_shrink_video_reduces_size(tmp_path):
    """업로드용 재인코딩 — 파일이 눈에 띄게 작아지고 길이·해상도 유지."""
    import os

    from cutdaejang.core import video_editor
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "big.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=6",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
            "-pix_fmt", "yuv420p", str(src)])
    out = video_editor.shrink_video(str(src), str(tmp_path / "small.mp4"))
    before, after = os.path.getsize(src), os.path.getsize(out)
    assert after < before * 0.75, (before, after)
    assert abs(ff.probe_duration_us(out) - ff.probe_duration_us(str(src))) < 300_000
    assert ff.probe_video_size(out) == (1280, 720)    # 1080 이하면 해상도 유지


def test_eleven_payload_context_and_settings(monkeypatch):
    """일레븐랩스 페이로드 — stability/similarity 반영 + 이어읽기 문맥 필드."""
    from cutdaejang.core import tts_engine as te

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    p = te.ElevenLabsTTS(stability=0.6, similarity=0.9)
    body = p._payload("안녕하세요")
    assert body["voice_settings"] == {"stability": 0.6, "similarity_boost": 0.9}
    assert "previous_text" not in body and "next_text" not in body
    p._prev_text, p._next_text = "앞 문장이에요", "뒤 문장이에요"
    body = p._payload("안녕하세요")
    assert body["previous_text"] == "앞 문장이에요"
    assert body["next_text"] == "뒤 문장이에요"
    # 범위 밖 값은 0~1로 클램프 + 캐시 키 구분용 cache_extra
    p2 = te.ElevenLabsTTS(stability=7, similarity=-1)
    assert p2.stability == 1.0 and p2.similarity == 0.0
    assert "stab" in p2.cache_extra and "ctx1" in p2.cache_extra
    assert p2.wants_context


@requires_ffmpeg
def test_engine_passes_context_and_keys_cache_by_context(tmp_path):
    """synth_all이 앞뒤 문장을 제공자에 전달 + 문맥이 다르면 캐시 키도 다름."""
    from cutdaejang.core import tts_engine as te

    class FakeCtxProvider:
        name = "fakectx"
        model = "m1"
        wants_context = True

        def __init__(self):
            self._prev_text = ""
            self._next_text = ""
            self.seen = []

        def synthesize(self, text, voice, out_path):
            self.seen.append((text, self._prev_text, self._next_text))
            te.StubTTS().synthesize(text, voice, out_path)
            return out_path

    prov = FakeCtxProvider()
    eng = te.TTSEngine(prov, tmp_path / "cache")
    eng.synth_all(["첫 문장입니다", "둘째 문장입니다", "셋째 문장입니다"])
    assert [s[1] for s in prov.seen] == ["", "첫 문장입니다", "둘째 문장입니다"]
    assert [s[2] for s in prov.seen] == ["둘째 문장입니다", "셋째 문장입니다", ""]
    # 같은 문장이라도 문맥이 다르면 다른 캐시 파일
    k_solo = eng.cache_path("같은 문장", "v")
    k_ctx = eng.cache_path("같은 문장", "v", ctx="앞\x1f뒤")
    assert k_solo != k_ctx
    # 문맥 미지원 제공자(윈도우 등)는 기존 키 그대로 → 캐시 보존
    assert eng._cache_key("같은 문장", "v", ctx="") == eng._cache_key("같은 문장", "v")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v083")
    iso = tmp_path_factory.mktemp("iso83")
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
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


@requires_ffmpeg
def test_shrink_api_e2e(server, tmp_path):
    """완성 작업의 mp4 → /api/shrink → _업로드용.mp4 생성 + 크기 리포트."""
    import os

    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "done.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=s=960x540:r=30:d=4",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
            "-pix_fmt", "yuv420p", str(src)])
    webui._set_job("shrinkjob83", status="ok", mp4=str(src))
    d = _post(server, "/api/shrink", {"job_id": "shrinkjob83"})
    assert d.get("ok"), d
    t0 = time.time()
    job = {}
    while time.time() - t0 < 120:
        job = webui._get_job("shrinkjob83") or {}
        if job.get("shrink_status") in ("done", "failed"):
            break
        time.sleep(0.5)
    assert job.get("shrink_status") == "done", job
    assert job["shrink_out"].endswith("_업로드용.mp4")
    assert os.path.getsize(job["shrink_out"]) < os.path.getsize(src)
    assert job["shrink_after_mb"] <= job["shrink_before_mb"]
    # 없는 작업은 친절한 오류
    d2 = _post(server, "/api/shrink", {"job_id": "없는작업"})
    assert "error" in d2
