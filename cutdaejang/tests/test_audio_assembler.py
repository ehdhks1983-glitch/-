"""audio_assembler 실행 테스트 — 실측 길이·배치 검증 (ffmpeg 필요)."""

import pytest

from cutdaejang.core.render_engine import audio_assembler
from cutdaejang.spec import AudioClip, Background, TimelineSpec
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def test_assemble_three_clips_with_gaps(tmp_path, make_sine_clip):
    clips = [
        make_sine_clip("s01.m4a", 0.9, freq=330),
        make_sine_clip("s02.m4a", 1.4, freq=440),
        make_sine_clip("s03.m4a", 1.1, freq=550),
    ]
    # 실측 길이로 스펙 구성 (lead-in 0.3s, 갭 0.25s, 테일 0.6s)
    t = 300_000
    audio = []
    for c in clips:
        dur = ff.probe_duration_us(str(c))
        audio.append(AudioClip(str(c), t, t + dur))
        t += dur + 250_000
    duration = (t - 250_000) + 600_000

    spec = TimelineSpec(
        duration_us=duration,
        background=Background(type="image", path="unused.png"),
        audio=audio,
    )
    out = tmp_path / "voice_full.m4a"
    measured = audio_assembler.assemble(spec, out)

    assert abs(measured - duration) <= 50_000
    assert ff.has_audio_stream(str(out))


def test_assemble_empty_audio_produces_silence(tmp_path):
    spec = TimelineSpec(
        duration_us=2_000_000,
        background=Background(type="image", path="unused.png"),
    )
    out = tmp_path / "voice_full.m4a"
    measured = audio_assembler.assemble(spec, out)
    assert abs(measured - 2_000_000) <= 50_000


def test_short_clip_padded_to_full_spec_length(tmp_path, make_sine_clip):
    clip = make_sine_clip("s01.m4a", 1.0)
    spec = TimelineSpec(
        duration_us=10_000_000,
        background=Background(type="image", path="unused.png"),
        audio=[AudioClip(str(clip), 0, 1_000_000)],
    )
    measured = audio_assembler.assemble(spec, tmp_path / "voice_full.m4a")
    assert abs(measured - 10_000_000) <= 50_000


def test_assemble_rejects_length_mismatch(tmp_path, make_sine_clip, monkeypatch):
    clip = make_sine_clip("s01.m4a", 1.0)
    spec = TimelineSpec(
        duration_us=2_000_000,
        background=Background(type="image", path="unused.png"),
        audio=[AudioClip(str(clip), 0, 1_000_000)],
    )
    # 실측이 스펙과 어긋난 상황을 주입해 검증 게이트가 실제로 작동하는지 확인
    monkeypatch.setattr(audio_assembler.ff, "probe_duration_us", lambda p: 1_500_000)
    with pytest.raises(audio_assembler.AssembleError, match="길이 불일치"):
        audio_assembler.assemble(spec, tmp_path / "voice_full.m4a")
