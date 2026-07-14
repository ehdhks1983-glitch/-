"""무음 감지·컷·타임라인 remap 검증 (편집 모드 코어)."""

import pytest

from cutdaejang.core import video_editor as ve
from cutdaejang.core.video_editor import SilenceOptions
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_parse_silences():
    text = (
        "[silencedetect] silence_start: 2.1\n"
        "[silencedetect] silence_end: 3.4 | silence_duration: 1.3\n"
        "[silencedetect] silence_start: 5.6\n"
        "[silencedetect] silence_end: 6.9 | silence_duration: 1.3\n"
    )
    assert ve._parse_silences(text) == [(2.1, 3.4), (5.6, 6.9)]


def test_speech_from_silences_inverts_and_pads():
    # 9초 영상, 무음 2.1~3.4, 5.6~6.9 → 발화 3구간
    opts = SilenceOptions(pad_s=0.0, min_segment_s=0.3, max_segment_s=60)
    speech = ve.speech_from_silences(9_000_000, [(2.1, 3.4), (5.6, 6.9)], opts)
    assert speech == [(0, 2_100_000), (3_400_000, 5_600_000), (6_900_000, 9_000_000)]


def test_speech_drops_tiny_segments():
    opts = SilenceOptions(pad_s=0.0, min_segment_s=0.5, max_segment_s=60)
    # 0~0.2(짧음, 버림), 1.0~3.0(유지)
    speech = ve.speech_from_silences(3_000_000, [(0.2, 1.0)], opts)
    assert speech == [(1_000_000, 3_000_000)]


def test_speech_splits_long_segment():
    opts = SilenceOptions(pad_s=0.0, min_segment_s=0.3, max_segment_s=4.0)
    # 0~10초 한 덩어리 → 4초 단위로 3분할
    speech = ve.speech_from_silences(10_000_000, [], opts)
    assert len(speech) == 3
    assert speech[0][0] == 0 and speech[-1][1] == 10_000_000
    assert all(e - s <= 4_000_000 + 1 for s, e in speech)


def test_speech_merges_on_padding_overlap():
    opts = SilenceOptions(pad_s=0.5, min_segment_s=0.3, max_segment_s=60)
    # 무음 2.0~2.3 (짧은 간격) → 패딩으로 두 발화가 병합됨
    speech = ve.speech_from_silences(5_000_000, [(2.0, 2.3)], opts)
    assert speech == [(0, 5_000_000)]


def test_remap_to_cut_timeline():
    segs = [(0, 2_100_000), (3_400_000, 5_600_000), (6_900_000, 9_000_000)]
    assert ve.remap_to_cut_timeline(segs) == [
        (0, 2_100_000), (2_100_000, 4_300_000), (4_300_000, 6_400_000)
    ]


def test_silence_ratio():
    segs = [(0, 2_000_000), (4_000_000, 6_000_000)]  # 6초 중 4초 유지
    assert ve.silence_ratio(segs, 6_000_000) == pytest.approx(1 / 3, abs=0.01)


@requires_ffmpeg
def test_detect_and_cut_roundtrip(tmp_path):
    # 말(톤)-무음-말 구조 합성 영상
    audio = tmp_path / "a.wav"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=2:sample_rate=44100",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=2:sample_rate=44100",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[a]", "-map", "[a]", str(audio),
    ])
    video = tmp_path / "v.mp4"
    ff.run([
        ff.ffmpeg_bin(), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=640x480:r=30:d=5.5",
        "-i", str(audio), "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(video),
    ])
    segments, dur = ve.detect_speech_segments(str(video))
    assert len(segments) == 2  # 무음 가운데 하나 → 발화 2구간
    assert ve.silence_ratio(segments, dur) > 0.2

    cut = ve.cut_and_concat(str(video), segments, str(tmp_path / "cut.mp4"))
    cut_us = ff.probe_duration_us(cut)
    # 컷 영상 = 발화 구간 합
    expected = sum(e - s for s, e in segments)
    assert abs(cut_us - expected) <= 200_000
    assert ff.has_audio_stream(cut)
