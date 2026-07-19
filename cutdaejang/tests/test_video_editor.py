"""무음 감지·컷·타임라인 remap 검증 (편집 모드 코어)."""

import pytest

from cutdaejang.core import video_editor as ve
from cutdaejang.core.video_editor import SilenceOptions
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_resolve_input_video(tmp_path):
    # 파일 직접 지정
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    assert ve.resolve_input_video(str(f)) == str(f)
    # 따옴표 감싼 경로 ("경로로 복사" 형식)
    assert ve.resolve_input_video(f'"{f}"') == str(f)


def test_resolve_input_video_folder_picks_latest(tmp_path):
    import os
    import time

    (tmp_path / "old.mp4").write_bytes(b"x")
    time.sleep(0.02)
    (tmp_path / "new.mov").write_bytes(b"x")
    # mtime 명시적으로 조정
    os.utime(tmp_path / "old.mp4", (1, 1))
    picked = ve.resolve_input_video(str(tmp_path))
    assert picked.endswith("new.mov")  # 가장 최근 영상


def test_resolve_input_video_folder_no_video(tmp_path):
    (tmp_path / "readme.txt").write_bytes(b"x")
    with pytest.raises(ValueError, match="영상 파일이 없습니다"):
        ve.resolve_input_video(str(tmp_path))


def test_resolve_input_video_missing():
    with pytest.raises(ValueError, match="영상을 찾을 수 없습니다"):
        ve.resolve_input_video("/nonexistent/path/x.mp4")


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


# ─────────── v0.31: 사진 → 슬라이드쇼 영상 ───────────


def test_resolve_photo_inputs_folder_sorted(tmp_path):
    from pathlib import Path

    from cutdaejang.core.video_editor import resolve_photo_inputs

    for name in ["b.png", "a.jpg", "c.webp", "note.txt"]:
        (tmp_path / name).write_bytes(b"x")
    out = resolve_photo_inputs(str(tmp_path))
    assert [Path(p).name for p in out] == ["a.jpg", "b.png", "c.webp"]  # 이름순, 사진만
    with pytest.raises(ValueError, match="찾을 수 없"):
        resolve_photo_inputs(str(tmp_path / "없는폴더"))


@requires_ffmpeg
def test_photos_to_video_divides_duration(tmp_path):
    from cutdaejang.core.video_editor import photos_to_video
    from cutdaejang.utils import ffmpeg as ff

    imgs = []
    for i, c in enumerate(["red", "green", "blue"]):
        p = tmp_path / f"p{i}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=800x600:d=0.1", "-frames:v", "1", str(p)])
        imgs.append(str(p))
    out = str(tmp_path / "slide.mp4")
    photos_to_video(imgs, 9_000_000, out)  # 3장·9초 → 장당 3초
    assert abs(ff.probe_duration_us(out) - 9_000_000) < 400_000
    assert ff.probe_video_size(out) == (1080, 1920)
    assert ff.has_audio_stream(out)  # 무음 트랙 (내레이션·BGM 얹기용)


# ─────────── v0.43: 전환 효과(fade) + 인트로/아웃트로 ───────────


def _lum_at(video: str, t: float) -> int:
    """t초 프레임의 평균 밝기 (0~255) — 페이드 dip 검증용."""
    import subprocess

    out = subprocess.run(
        [ff.ffmpeg_bin(), "-v", "error", "-ss", str(t), "-i", str(video),
         "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True).stdout
    return out[0] if out else -1


@requires_ffmpeg
def test_cut_and_concat_fade_keeps_duration_and_dips(tmp_path):
    src = tmp_path / "white.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=white:s=320x180:d=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src)])
    segs = [(0, 2_000_000), (2_000_000, 4_000_000), (4_000_000, 6_000_000)]
    plain = ve.cut_and_concat(str(src), segs, str(tmp_path / "p.mp4"))
    faded = ve.cut_and_concat(str(src), segs, str(tmp_path / "f.mp4"), transition="fade")
    # 길이 불변 (자막 싱크 유지의 핵심)
    assert abs(ff.probe_duration_us(plain) - ff.probe_duration_us(faded)) < 80_000
    # 구간 경계(2s)는 어두워지고, 중간(1s)·시작(0s)은 밝음
    assert _lum_at(faded, 1.0) > 200
    assert _lum_at(faded, 2.0) < _lum_at(faded, 1.0) - 60
    assert _lum_at(faded, 0.02) > 200  # 영상 처음에는 페이드 없음


@requires_ffmpeg
def test_photos_to_video_fade_transition(tmp_path):
    from cutdaejang.core.video_editor import photos_to_video

    imgs = []
    for i, c in enumerate(["white", "white"]):
        p = tmp_path / f"w{i}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=320x568:d=0.1", "-frames:v", "1", str(p)])
        imgs.append(str(p))
    out = str(tmp_path / "slide.mp4")
    photos_to_video(imgs, 4_000_000, out, size=(320, 568), transition="fade")
    assert abs(ff.probe_duration_us(out) - 4_000_000) < 400_000
    # 사진 경계(2s)에서 dip, 사진 중간(1s)은 밝음
    assert _lum_at(out, 2.0) < _lum_at(out, 1.0) - 40


@requires_ffmpeg
def test_attach_branding_intro_outro(tmp_path):
    main = tmp_path / "main.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(main)])
    intro = tmp_path / "intro.png"  # 사진 인트로 → 2.5초 정지 클립
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=red:s=800x600:d=0.1", "-frames:v", "1", str(intro)])
    outro = tmp_path / "outro.mp4"  # 무음·다른 해상도 아웃트로
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1.5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(outro)])
    out = ve.attach_branding(str(main), str(intro), str(outro), str(tmp_path / "b.mp4"))
    assert out != str(main)
    dur_s = ff.probe_duration_us(out) / 1e6
    assert 6.6 <= dur_s <= 7.4  # 2.5 + 3 + 1.5
    assert ff.probe_video_size(out) == (320, 180)  # 본편 해상도 기준
    assert ff.has_audio_stream(out)


def test_attach_branding_skips_when_missing(tmp_path):
    main = tmp_path / "m.mp4"
    main.write_bytes(b"x")
    # 둘 다 비었으면 원본 그대로 (ffmpeg 호출 없음 — 가짜 파일이어도 통과해야 함)
    assert ve.attach_branding(str(main), "", "  ", str(tmp_path / "o.mp4")) == str(main)
    # 경로가 있어도 파일이 없으면 건너뜀
    assert ve.attach_branding(str(main), str(tmp_path / "없음.mp4"), "",
                              str(tmp_path / "o2.mp4")) == str(main)


# ─────────── v0.44: 장면 전환 감지 + 경계 스냅 ───────────


@requires_ffmpeg
def test_detect_scene_changes_on_color_cuts(tmp_path):
    # 어두움 2초 → 흰색 2초 → 회색 2초: 장면 전환은 2s·4s 두 곳
    # (빨강→초록 같은 순색 조합은 ffmpeg 장면 메트릭에서 점수가 낮게 나오는
    #  합성 소재 특이 케이스라 휘도 차가 있는 색으로 만든다 — 실제 영상은 무관)
    src = tmp_path / "scenes.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "color=c=white:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "color=c=0x606060:s=320x180:d=2:r=30",
            "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0[v]", "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src)])
    scenes = ve.detect_scene_changes(str(src))
    assert len(scenes) == 2, scenes
    assert abs(scenes[0] - 2_000_000) < 200_000
    assert abs(scenes[1] - 4_000_000) < 200_000


def test_shift_ranges_to_scenes_snaps_and_keeps_length():
    scenes = [2_000_000, 10_000_000]
    ranges = [(1_200_000, 4_200_000), (9_300_000, 12_300_000)]  # 각 3초
    out = ve.shift_ranges_to_scenes(ranges, scenes, duration_us=20_000_000)
    assert out == [(2_000_000, 5_000_000), (10_000_000, 13_000_000)]  # 길이 3초 유지
    # 스냅 범위(±1.5s) 밖이면 그대로
    far = ve.shift_ranges_to_scenes([(6_000_000, 9_000_000)], scenes, 20_000_000)
    assert far == [(6_000_000, 9_000_000)]
    # 밀었을 때 영상 밖으로 나가면 포기
    tail = ve.shift_ranges_to_scenes([(9_000_000, 11_500_000)], [10_000_000], 11_600_000)
    assert tail == [(9_000_000, 11_500_000)]


def test_snap_boundaries_to_scenes_moves_interior_only():
    scenes = [29_000_000]
    ranges = [(0, 30_000_000), (30_000_000, 60_000_000)]
    out = ve.snap_boundaries_to_scenes(ranges, scenes)
    # 경계 30s → 장면 전환 29s로, 양 끝(0·60s)은 고정, 빈틈 없음
    assert out == [(0, 29_000_000), (29_000_000, 60_000_000)]
    # 스냅하면 한 쪽이 3초 미만이 되는 경우엔 경계 유지
    short = ve.snap_boundaries_to_scenes([(0, 4_000_000), (4_000_000, 8_000_000)],
                                         [2_500_000])
    assert short == [(0, 4_000_000), (4_000_000, 8_000_000)]
