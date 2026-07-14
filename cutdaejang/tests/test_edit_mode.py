"""편집 모드 E2E — 무음컷 + 자동자막 렌더 (stub STT)."""

import pytest

from cutdaejang.core import edit_mode
from cutdaejang.core.stt_engine import STTEngine, StubSTT, make_provider
from cutdaejang.core.video_editor import SilenceOptions
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


@pytest.fixture(scope="module")
def talk_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("talk")
    audio = d / "a.wav"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=2:sample_rate=44100",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=420:duration=2:sample_rate=44100",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=520:duration=2:sample_rate=44100",
        "-filter_complex", "[0][1][2][3][4]concat=n=5:v=0:a=1[a]", "-map", "[a]", str(audio),
    ])
    video = d / "talk.mp4"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=1280x720:r=30:d=9",
        "-i", str(audio), "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(video),
    ])
    return str(video)


def _engine(tmp_path):
    return STTEngine(StubSTT(), tmp_path / "sttcache")


def test_edit_shorts_output(talk_video, tmp_path):
    result = edit_mode.edit_video(
        talk_video, tmp_path / "work", _engine(tmp_path), layout="shorts",
    )
    assert result.ok, result.errors
    assert result.segments == 3
    assert result.removed_ratio > 0.2
    assert len(result.subtitles) == 3
    # 쇼츠 = 1080x1920, 오디오 유지, 길이 = 컷 길이
    w, h = ff.probe_video_size(result.out_path)
    assert (w, h) == (1080, 1920)
    assert ff.has_audio_stream(result.out_path)
    assert result.cut_us < result.original_us


def test_edit_keep_layout_preserves_ratio(talk_video, tmp_path):
    result = edit_mode.edit_video(
        talk_video, tmp_path / "work2", _engine(tmp_path), layout="keep",
    )
    assert result.ok, result.errors
    w, h = ff.probe_video_size(result.out_path)
    assert (w, h) == (1280, 720)  # 원본 비율 유지


def test_edit_stt_cache_hit_on_rerun(talk_video, tmp_path):
    cache = tmp_path / "sttcache"
    e1 = STTEngine(StubSTT(), cache)
    edit_mode.edit_video(talk_video, tmp_path / "w1", e1, layout="keep")
    assert e1.stats["calls"] == 3 and e1.stats["cache_hits"] == 0
    e2 = STTEngine(StubSTT(), cache)  # 같은 캐시 → 재전사 0회
    edit_mode.edit_video(talk_video, tmp_path / "w2", e2, layout="keep")
    assert e2.stats["calls"] == 0 and e2.stats["cache_hits"] == 3


def test_build_subtitles_skips_empty():
    from cutdaejang.core.edit_mode import build_subtitles

    subs = build_subtitles(
        [(0, 1_000_000), (1_000_000, 2_000_000), (2_000_000, 3_000_000)],
        ["안녕하세요", "", "반갑습니다"],
    )
    assert [s.text for s in subs] == ["안녕하세요", "반갑습니다"]
    assert subs[1].start_us == 2_000_000  # 빈 구간 건너뜀


def test_make_provider_stub_default():
    assert make_provider("stub").name == "stub"
    assert make_provider("whisper", {"whisper_model": "tiny"}).model_size == "tiny"
