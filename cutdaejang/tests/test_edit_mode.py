"""편집 모드 E2E — 무음컷 + 자동자막 렌더 (stub STT)."""

from pathlib import Path

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


# ─────────── 대본 직접 입력 (STT 대신) — 사용자 요청 ───────────


def test_align_script_1to1_when_counts_match():
    from cutdaejang.core.edit_mode import align_script_to_segments

    segs = [(0, 1_000_000), (1_000_000, 2_500_000), (2_500_000, 4_000_000)]
    subs = align_script_to_segments(["첫 줄", "둘째 줄", "셋째 줄"], segs)
    # 줄 수 == 구간 수 → 실제 발화 타이밍에 1:1로 얹힌다
    assert [s.text for s in subs] == ["첫 줄", "둘째 줄", "셋째 줄"]
    assert [(s.start_us, s.end_us) for s in subs] == segs


def test_align_script_proportional_when_mismatch():
    from cutdaejang.core.edit_mode import align_script_to_segments

    # 무내레이션 b-roll: 구간 1개(전체) 인데 대본 3줄 → 길이 비례 분배
    subs = align_script_to_segments(
        ["짧다", "이건 조금 더 긴 문장이다", "끝"], [(0, 6_000_000)]
    )
    assert [s.text for s in subs] == ["짧다", "이건 조금 더 긴 문장이다", "끝"]
    assert subs[0].start_us == 0
    assert subs[-1].end_us == 6_000_000            # 마지막은 끝에 딱 맞춤
    for a, b in zip(subs, subs[1:]):               # 겹치지 않고 이어짐
        assert a.end_us == b.start_us
        assert b.start_us > a.start_us
    # 긴 문장이 더 오래 표시된다 (글자 수 비례)
    assert (subs[1].end_us - subs[1].start_us) > (subs[0].end_us - subs[0].start_us)


def test_align_script_ignores_blank_lines():
    from cutdaejang.core.edit_mode import align_script_to_segments

    subs = align_script_to_segments(["A", "", "  ", "B"], [(0, 1_000_000), (1_000_000, 2_000_000)])
    assert [s.text for s in subs] == ["A", "B"]


@requires_ffmpeg
def test_analyze_with_script_skips_stt(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import analyze_video

    eng = _engine(tmp_path)  # STT 엔진을 넘겨도 대본이 있으면 호출되면 안 됨
    analysis = analyze_video(
        talk_video, tmp_path / "w", eng,
        script_lines=["직접 넣은 첫 자막", "직접 넣은 둘째 자막", "직접 넣은 셋째 자막"],
    )
    assert [s.text for s in analysis.subtitles] == [
        "직접 넣은 첫 자막", "직접 넣은 둘째 자막", "직접 넣은 셋째 자막",
    ]
    assert analysis.stt_calls == 0
    assert eng.stats["calls"] == 0          # 음성 인식은 실제로 건너뜀
    # 자막이 컷 길이 안에 배치됐는지
    assert analysis.subtitles[-1].end_us <= analysis.cut_us + 200_000


# ─────────── Phase 1: 분석→수정→렌더 2단계 ───────────


@requires_ffmpeg
def test_analyze_then_render_two_phase(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import (
        analyze_video, dicts_to_subtitles, render_from_analysis, subtitles_to_dicts,
    )

    analysis = analyze_video(talk_video, tmp_path / "w", _engine(tmp_path))
    assert len(analysis.subtitles) == 3
    assert Path(analysis.cut_video).exists()
    # 자막 저장(json+srt) 확인
    assert (tmp_path / "w" / "subtitles.json").exists()
    assert (tmp_path / "w" / "subtitles.srt").exists()

    # 사용자가 자막 수정 (dict로 오감) → 렌더
    dicts = subtitles_to_dicts(analysis.subtitles)
    dicts[0]["text"] = "고친 자막"
    dicts[1]["text"] = ""  # 빈 자막은 제외돼야
    subs = dicts_to_subtitles(dicts)
    assert [s.text for s in subs] == ["고친 자막", subs[1].text]  # 2개(빈 것 제외)
    assert len(subs) == 2

    result = render_from_analysis(
        analysis.cut_video, subs, str(tmp_path / "w" / "out.mp4"), layout="shorts",
    )
    assert result.ok, result.errors
    # srt가 수정본으로 갱신됐는지
    srt = (tmp_path / "w" / "subtitles.srt").read_text(encoding="utf-8")
    assert "고친 자막" in srt


def test_save_srt_format(tmp_path):
    from cutdaejang.core.edit_mode import save_srt
    from cutdaejang.spec import Subtitle

    save_srt([Subtitle("첫 줄", 500_000, 2_100_000)], tmp_path / "s.srt")
    text = (tmp_path / "s.srt").read_text(encoding="utf-8")
    assert "1\n00:00:00,500 --> 00:00:02,100\n첫 줄" in text


def test_suggest_hooks_stub():
    from cutdaejang.core.script_generator import suggest_hooks_stub

    hooks = suggest_hooks_stub("블로그 자동화", n=5)
    assert len(hooks) == 5
    assert all("블로그 자동화" in h for h in hooks)
    assert all(len(h) <= 40 for h in hooks)


def test_suggest_hooks_no_key_raises():
    import os

    from cutdaejang.core.script_generator import ScriptError, suggest_hooks

    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(ScriptError):
            suggest_hooks("주제", api_key="")
    finally:
        if old:
            os.environ["GEMINI_API_KEY"] = old


def test_make_provider_stub_default():
    assert make_provider("stub").name == "stub"
    assert make_provider("whisper", {"whisper_model": "tiny"}).model_size == "tiny"


# ─────────── STT 환각 방지 (사용자 리포트: 내레이션 없는데 자막 생성됨) ───────────


def test_is_hallucination_detects_common_phrases():
    from cutdaejang.core.stt_engine import is_hallucination

    assert is_hallucination("시청해주셔서 감사합니다")
    assert is_hallucination("시청해주셔서 감사합니다.")
    assert is_hallucination("구독과 좋아요 부탁드립니다")
    assert is_hallucination("")  # 빈 텍스트
    assert is_hallucination("   ")
    # 진짜 발화는 통과
    assert not is_hallucination("오늘은 라멘 맛집에 왔습니다")
    assert not is_hallucination("이 가게는 6900원입니다")


def test_engine_filters_hallucination(tmp_path):
    from cutdaejang.core.stt_engine import STTEngine

    class HallucinateSTT:
        name = "fake"

        def transcribe(self, audio_path, language="ko"):
            return "시청해주셔서 감사합니다"

    e = STTEngine(HallucinateSTT(), tmp_path / "c")
    # 오디오 파일 필요 (캐시 키 계산) — 더미
    dummy = tmp_path / "a.wav"
    dummy.write_bytes(b"RIFFxxxx")
    assert e.transcribe(str(dummy)) == ""  # 환각 → 빈 자막
    assert e.stats["hallucinations"] == 1


@requires_ffmpeg
def test_edit_no_subtitle_mode(talk_video, tmp_path):
    # 자막 끄기 → STT 없이 컷+포맷만
    result = edit_mode.edit_video(
        talk_video, tmp_path / "w", None, layout="shorts", auto_subtitle=False,
    )
    assert result.ok, result.errors
    assert result.subtitles == []
    assert result.stt_calls == 0
    from cutdaejang.utils import ffmpeg as ff

    assert ff.probe_video_size(result.out_path) == (1080, 1920)


@requires_ffmpeg
def test_edit_with_hook_renders(talk_video, tmp_path):
    result = edit_mode.edit_video(
        talk_video, tmp_path / "w", None, layout="shorts",
        hook="테스트 제목\n둘째 줄", auto_subtitle=False,
    )
    assert result.ok, result.errors
    # 훅 .ass에 Title 이벤트가 들어갔는지
    ass = (tmp_path / "w" / "subs.ass").read_text(encoding="utf-8")
    assert "Title,," in ass and "테스트 제목" in ass


@requires_ffmpeg
def test_edit_no_cut_keeps_full_length(talk_video, tmp_path):
    from cutdaejang.utils import ffmpeg as ff

    orig = ff.probe_duration_us(talk_video)
    result = edit_mode.edit_video(
        talk_video, tmp_path / "w2", None, layout="keep",
        auto_subtitle=False, cut_silence=False,
    )
    assert result.ok, result.errors
    assert result.removed_ratio == 0.0
    assert abs(result.cut_us - orig) < 200_000  # 원본 길이 유지
