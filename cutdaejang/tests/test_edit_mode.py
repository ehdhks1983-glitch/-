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


# ─────────── 편집모드 강조 단어(골드) — 사용자 레퍼런스 스타일 ───────────


def test_dicts_to_subtitles_parses_highlight_pipe():
    from cutdaejang.core.edit_mode import dicts_to_subtitles

    subs = dicts_to_subtitles([
        {"text": "안녕하세요 곰대리 곰부장입니다 | 곰대리", "start_us": 0, "end_us": 2_000_000},
    ])
    assert len(subs) == 1
    assert subs[0].text == "안녕하세요 곰대리 곰부장입니다"  # | 뒤는 텍스트에서 제거
    assert subs[0].highlight == "곰대리"                      # 골드로 렌더될 단어


def test_dicts_to_subtitles_explicit_highlight_key():
    from cutdaejang.core.edit_mode import dicts_to_subtitles

    subs = dicts_to_subtitles([
        {"text": "가격은 육천구백원", "highlight": "육천구백원", "start_us": 0, "end_us": 1_000_000},
    ])
    assert subs[0].highlight == "육천구백원"


def test_subtitles_to_dicts_roundtrips_highlight():
    from cutdaejang.core.edit_mode import dicts_to_subtitles, subtitles_to_dicts

    subs = dicts_to_subtitles([{"text": "문장 | 강조", "start_us": 0, "end_us": 1_000_000}])
    d = subtitles_to_dicts(subs)[0]
    assert d["text"] == "문장" and d["highlight"] == "강조"


def test_dicts_to_subtitles_no_pipe_no_highlight():
    from cutdaejang.core.edit_mode import dicts_to_subtitles

    subs = dicts_to_subtitles([{"text": "그냥 자막", "start_us": 0, "end_us": 1_000_000}])
    assert subs[0].highlight == ""


# ─────────── 쇼츠 핵심 추출 (긴 영상 → 짧고 굵게) ───────────


def test_remap_subs_to_ranges_rebases_timeline():
    from cutdaejang.core.edit_mode import _remap_subs_to_ranges
    from cutdaejang.spec import Subtitle

    # 컷 타임라인의 자막 2개(2~3초, 8~9초) → 두 구간만 남기면 0부터 재배치
    kept = [Subtitle("가", 2_000_000, 3_000_000), Subtitle("나", 8_000_000, 9_000_000)]
    ranges = [(2_000_000, 3_000_000), (8_000_000, 9_000_000)]
    out = _remap_subs_to_ranges(kept, ranges)
    assert (out[0].start_us, out[0].end_us) == (0, 1_000_000)
    assert (out[1].start_us, out[1].end_us) == (1_000_000, 2_000_000)


@requires_ffmpeg
def test_rebuild_from_keep_makes_shorter_video(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import analyze_video, rebuild_from_keep
    from cutdaejang.utils import ffmpeg as ff

    analysis = analyze_video(talk_video, tmp_path / "w", _engine(tmp_path))
    assert len(analysis.subtitles) == 3
    full_us = ff.probe_duration_us(analysis.cut_video)
    # 가운데 한 구간만 남김 → 확실히 짧아진다
    new_video, new_subs = rebuild_from_keep(
        analysis.cut_video, analysis.subtitles, [1], str(tmp_path / "w" / "short.mp4"),
    )
    short_us = ff.probe_duration_us(new_video)
    assert short_us < full_us
    assert len(new_subs) == 1
    assert new_subs[0].start_us < 400_000  # 새 타임라인 0 근처에서 시작
    assert ff.has_audio_stream(new_video)


def test_suggest_highlights_heuristic_picks_densest_within_target():
    from cutdaejang.core.script_generator import suggest_highlights_heuristic

    subs = [
        {"text": "짧게", "start_us": 0, "end_us": 5_000_000},               # 5초, 정보 적음
        {"text": "이건 정보가 아주 많은 핵심 문장입니다", "start_us": 5_000_000, "end_us": 8_000_000},
        {"text": "이것도 알찬 핵심 내용이에요 정말로", "start_us": 8_000_000, "end_us": 11_000_000},
        {"text": "음", "start_us": 11_000_000, "end_us": 20_000_000},        # 9초, 정보 거의 없음
    ]
    res = suggest_highlights_heuristic(subs, target_sec=8)
    assert res["keep"]  # 뭔가는 고름
    # 정보 촘촘한 1,2번을 골라야지 물타기 구간(0,3)만 고르면 안 됨
    assert 1 in res["keep"] or 2 in res["keep"]


def test_suggest_highlights_no_key_raises():
    import os

    from cutdaejang.core.script_generator import ScriptError, suggest_highlights

    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(ScriptError):
            suggest_highlights([{"text": "x", "start_us": 0, "end_us": 1_000_000}], api_key="")
    finally:
        if old:
            os.environ["GEMINI_API_KEY"] = old


# ─────────── 저장(렌더) 속도 + AI 대본 다듬기 + 훅 강조 ───────────


def test_atempo_chain_single_and_multi():
    from cutdaejang.core.edit_mode import _atempo_chain

    assert _atempo_chain(1.5) == "atempo=1.500000"
    # 2배 초과는 여러 개로 쪼갬 (atempo는 0.5~2.0만 지원)
    assert _atempo_chain(3.0).startswith("atempo=2.0,atempo=")


@requires_ffmpeg
def test_render_speed_shortens_output(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import analyze_video, render_from_analysis
    from cutdaejang.utils import ffmpeg as ff

    analysis = analyze_video(talk_video, tmp_path / "w", None, auto_subtitle=False)
    base = ff.probe_duration_us(analysis.cut_video)
    out = str(tmp_path / "w" / "fast.mp4")
    r = render_from_analysis(analysis.cut_video, [], out, layout="keep", speed=2.0)
    assert r.ok, r.errors
    sped = ff.probe_duration_us(out)
    assert sped < base * 0.62  # 2배속이면 대략 절반
    assert ff.has_audio_stream(out)


def test_refine_subtitles_no_key_raises():
    import os

    from cutdaejang.core.script_generator import ScriptError, refine_subtitles

    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(ScriptError):
            refine_subtitles(["원본"], api_key="")
    finally:
        if old:
            os.environ["GEMINI_API_KEY"] = old


def test_refine_subtitles_preserves_count(monkeypatch):
    from cutdaejang.core import script_generator as sg

    def fake_post(url, payload, headers):
        return {"candidates": [{"content": {"parts": [
            {"text": '{"lines":["고친 하나","고친 둘"]}'}]}}]}

    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    out = sg.refine_subtitles(["원본1", "원본2", "원본3"], api_key="x")
    assert len(out) == 3                       # 줄 수 보존
    assert out[0] == "고친 하나" and out[1] == "고친 둘"
    assert out[2] == "원본3"                    # 응답에 없는 줄은 원문 유지


def test_hook_dialogue_text_highlights_keyword():
    from cutdaejang.core.render_engine.ass_writer import hook_dialogue_text
    from cutdaejang.spec import Style

    style = Style(highlight_color="#FFD400")
    out = hook_dialogue_text("블로그 글도 AI가? 꿀팁 | AI가?", style)
    assert "AI가?" in out
    assert "\\1c" in out                       # 강조색 인라인 태그가 들어감
    assert "|" not in out                      # 구분자는 최종 텍스트에서 사라짐


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
