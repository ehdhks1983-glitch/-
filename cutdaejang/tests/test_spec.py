import pytest

from cutdaejang.spec import (
    AudioClip,
    Background,
    MainVideo,
    SpecError,
    Subtitle,
    TimelineSpec,
)


def make_valid_spec() -> TimelineSpec:
    return TimelineSpec(
        duration_us=5_000_000,
        background=Background(type="image", path="bg.png"),
        audio=[
            AudioClip("s01.m4a", 300_000, 2_000_000),
            AudioClip("s02.m4a", 2_250_000, 4_400_000),
        ],
        subtitles=[
            Subtitle("첫 문장", 300_000, 2_000_000),
            Subtitle("둘째 문장", 2_250_000, 4_400_000),
        ],
    )


def test_valid_spec_passes():
    make_valid_spec().validate()


def test_json_roundtrip_preserves_everything():
    spec = make_valid_spec()
    spec.main_video = MainVideo(path="main.mp4", layout="top", scale=0.9)
    restored = TimelineSpec.from_json(spec.to_json())
    assert restored.to_dict() == spec.to_dict()


def test_main_video_omitted_in_json_when_absent():
    assert "main_video" not in make_valid_spec().to_dict()


def test_overlapping_audio_rejected():
    spec = make_valid_spec()
    spec.audio[1].start_us = 1_500_000  # 이전 클립(~2s)과 겹침
    with pytest.raises(SpecError, match="겹칩"):
        spec.validate()


def test_clip_beyond_duration_rejected():
    spec = make_valid_spec()
    spec.audio[1].end_us = 6_000_000
    with pytest.raises(SpecError, match="초과"):
        spec.validate()


def test_float_time_rejected():
    spec = make_valid_spec()
    spec.audio[0].start_us = 0.3  # μs 정수 규칙 위반
    with pytest.raises(SpecError, match="정수"):
        spec.validate()


def test_image_background_requires_path():
    spec = make_valid_spec()
    spec.background = Background(type="image", path=None)
    with pytest.raises(SpecError, match="path"):
        spec.validate()


def test_unknown_keys_ignored_for_forward_compat():
    d = make_valid_spec().to_dict()
    d["style"]["future_field"] = 123
    d["future_top_level"] = True
    TimelineSpec.from_dict(d).validate()


def test_resolve_paths(tmp_path):
    spec = make_valid_spec()
    resolved = spec.resolve_paths(str(tmp_path))
    assert resolved.background.path == str(tmp_path / "bg.png")
    assert resolved.audio[0].path == str(tmp_path / "s01.m4a")
    # 원본은 불변
    assert spec.background.path == "bg.png"
