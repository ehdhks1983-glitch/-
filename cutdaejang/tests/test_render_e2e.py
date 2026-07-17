"""E2E: 스텁 TTS → 타임라인 실측 → 배경 → 렌더 → 자가검증 (기획안 §3.1 출력 B 전체 경로)."""

import pytest

from cutdaejang import presets
from cutdaejang.core import render_engine, timeline_calculator
from cutdaejang.core.render_engine.ffmpeg_composer import RenderOptions
from cutdaejang.core.tts_engine import StubTTS, TTSEngine
from cutdaejang.spec import Background
from cutdaejang.utils.png import vertical_gradient_png
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg

SENTENCES = [
    "컷대장 엔드투엔드 테스트입니다.",
    "문장별 티티에스 길이를 실측해서 타임라인을 만듭니다.",
    "자막과 오디오는 항상 같은 구간을 씁니다.",
]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    work = tmp_path_factory.mktemp("e2e")
    tts = TTSEngine(StubTTS(), work / "cache")
    audio_paths = tts.synth_all(SENTENCES)

    bg = vertical_gradient_png(str(work / "bg.png"), 1080, 1920, (16, 24, 48), (94, 33, 82))
    spec = timeline_calculator.build_spec(
        sentences=SENTENCES,
        audio_paths=[str(p) for p in audio_paths],
        background=Background(type="image", path=bg),
        style=presets.SUBTITLE_STYLE_PRESETS["shorts_basic"],
    )

    progress = []
    result = render_engine.render(
        spec,
        work / "render",
        out_path=str(work / "out.mp4"),
        opts=RenderOptions(crf=23, preset="veryfast", use_gpu="off"),
        progress_cb=progress.append,
    )
    return spec, result, progress


def test_render_passes_self_verification(rendered):
    spec, result, _ = rendered
    assert result.ok, result.errors
    assert result.attempts == 1
    assert result.encoder == "libx264"


def test_duration_within_50ms(rendered):
    spec, result, _ = rendered
    assert abs(result.measured_duration_us - spec.duration_us) <= render_engine.SYNC_TOLERANCE_US


def test_canvas_and_audio(rendered):
    _, result, _ = rendered
    assert (result.width, result.height) == (1080, 1920)
    assert result.has_audio


def test_progress_reported_monotonic(rendered):
    _, _, progress = rendered
    assert progress and progress[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(progress, progress[1:]))


def test_spec_roundtrip_rerender_possible(rendered, tmp_path):
    """히스토리 '재생성' 시나리오: 저장된 spec.json만으로 재렌더 가능해야 한다."""
    spec, _, _ = rendered
    from cutdaejang.spec import TimelineSpec

    path = tmp_path / "spec.json"
    spec.save(path)
    restored = TimelineSpec.load(path)
    assert restored.to_dict() == spec.to_dict()
    assert restored.missing_files() == []
