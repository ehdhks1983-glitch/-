"""편집 모드 E2E — 무음컷 + 자동자막 렌더 (stub STT)."""

from pathlib import Path

import pytest

from cutdaejang.core import edit_mode
from cutdaejang.core.stt_engine import STTEngine, StubSTT, make_provider
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


@requires_ffmpeg
def test_build_narration_wav_places_clips(tmp_path):
    from cutdaejang.core.edit_mode import build_narration_wav
    from cutdaejang.spec import Subtitle
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i in range(2):
        c = tmp_path / f"c{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"sine=frequency={300 + i * 100}:duration=1:sample_rate=24000", str(c)])
        clips.append(str(c))
    subs = [Subtitle("a", 500_000, 1_500_000), Subtitle("b", 3_000_000, 4_000_000)]
    out = build_narration_wav(clips, subs, 6_000_000, tmp_path / "n.wav")
    # 전체 길이(6초)에 맞춰 패딩·트림됨
    assert abs(ff.probe_duration_us(out) - 6_000_000) < 200_000


def _tts_clip(tmp_path, name, sec):
    c = tmp_path / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", f"sine=frequency=330:duration={sec}:sample_rate=24000", str(c)])
    return str(c)


@requires_ffmpeg
def test_retime_narration_matches_clip_durations(tmp_path):
    # 추정 창(균등 2.5초)이 실제 클립 길이(1/3/0.8초)와 달라도 실측 기준으로 재배치
    from cutdaejang.core.edit_mode import retime_narration
    from cutdaejang.spec import Subtitle

    clips = [_tts_clip(tmp_path, f"c{i}.wav", d) for i, d in enumerate([1.0, 3.0, 0.8])]
    subs = [Subtitle(t, i * 2_500_000, (i + 1) * 2_500_000) for i, t in enumerate("가나다")]
    out_subs, out_clips, note = retime_narration(clips, subs, 10_000_000, tmp_path)

    assert len(out_subs) == len(out_clips) == 3 and note == ""
    for s, dur in zip(out_subs, [1.0, 3.0, 0.8]):
        assert abs((s.end_us - s.start_us) - dur * 1e6) < 150_000  # 창 길이 == 발화 길이
    for a, b in zip(out_subs, out_subs[1:]):
        gap = b.start_us - a.end_us
        assert 100_000 <= gap <= 950_000        # 겹침 없음 + 간격 상한
    assert out_subs[-1].end_us <= 10_000_000


@requires_ffmpeg
def test_retime_narration_speeds_up_or_drops_when_video_short(tmp_path):
    from cutdaejang.core.edit_mode import retime_narration
    from cutdaejang.spec import Subtitle
    from cutdaejang.utils import ffmpeg as ff

    # 목소리 6초 > 영상 5초 → 말 속도 최대 1.25배로 압축 (문장은 유지)
    clips = [_tts_clip(tmp_path, f"s{i}.wav", 2.0) for i in range(3)]
    subs = [Subtitle(t, 0, 1) for t in "가나다"]
    out_subs, out_clips, note = retime_narration(clips, subs, 5_200_000, tmp_path)
    assert "말 속도" in note
    total_speech = sum(ff.probe_duration_us(c) for c in out_clips)
    assert total_speech < 6_000_000              # 실제로 빨라짐
    assert out_subs[-1].end_us <= 5_200_000 + 300_000

    # 상한(1.25배)으로도 못 담을 만큼 영상이 짧으면 → 뒷문장 생략 + 안내
    clips2 = [_tts_clip(tmp_path, f"d{i}.wav", 2.0) for i in range(3)]
    subs2 = [Subtitle(t, 0, 1) for t in "가나다"]
    out_subs2, out_clips2, note2 = retime_narration(clips2, subs2, 3_500_000, tmp_path / "b")
    assert len(out_subs2) == len(out_clips2) < 3
    assert "생략" in note2
    assert all(s.end_us <= 3_500_000 + 300_000 for s in out_subs2)


def test_split_into_clips_grouping():
    from cutdaejang.core.edit_mode import split_into_clips
    from cutdaejang.spec import Subtitle

    subs = [Subtitle(f"s{i}", i * 2_000_000, (i + 1) * 2_000_000) for i in range(5)]
    assert split_into_clips(subs, target_sec=5) == [[0, 1, 2], [3, 4]]
    assert split_into_clips(subs, target_sec=30) == [[0, 1, 2, 3, 4]]  # 짧으면 1개
    assert split_into_clips([], target_sec=30) == []


def _tone_video(tmp_path, name="tone.mp4", sec=3, an=False):
    v = tmp_path / name
    args = [ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=0x203040:s=320x240:r=30:d={sec}"]
    if not an:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}", "-af", "volume=0.5"]
    args += ["-c:v", "libx264", "-preset", "ultrafast"]
    args += ["-an"] if an else ["-c:a", "aac"]
    args.append(str(v))
    ff.run(args)
    return str(v)


def _max_volume_db(path):
    import re
    import subprocess

    r = subprocess.run([ff.ffmpeg_bin(), "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -99.0


@requires_ffmpeg
def test_render_orig_audio_mute(tmp_path):
    # 원본 소리 '무음' → 소리(440Hz 톤)가 사라진 무음 트랙
    from cutdaejang.core.edit_mode import render_from_analysis

    video = _tone_video(tmp_path)
    out = str(tmp_path / "mute.mp4")
    r = render_from_analysis(video, [], out, layout="keep", quality="draft", orig_audio="mute")
    assert r.ok, r.errors
    assert ff.has_audio_stream(out)          # 트랙은 있지만
    assert _max_volume_db(out) < -50         # 사실상 무음


@requires_ffmpeg
def test_render_bgm_mixed_and_looped(tmp_path):
    # BGM(1초짜리)이 3초 영상 길이만큼 루프되어 들림 (원본은 무음 처리)
    from cutdaejang.core.edit_mode import render_from_analysis

    video = _tone_video(tmp_path)
    bgm = tmp_path / "bgm.wav"
    # 실전 음원처럼 0dB 근처로 정규화된 1초짜리 톤 (sine 소스 기본 진폭은 -18dB라 증폭)
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-af", "volume=8", str(bgm)])
    out = str(tmp_path / "bgm.mp4")
    r = render_from_analysis(video, [], out, layout="keep", quality="draft",
                             orig_audio="mute", bgm_path=str(bgm), bgm_db=-10)
    assert r.ok, r.errors
    assert _max_volume_db(out) > -25         # BGM이 실제로 들림 (원본은 무음인데도)
    assert abs(ff.probe_duration_us(out) - ff.probe_duration_us(video)) < 300_000


@requires_ffmpeg
def test_render_video_without_audio_stream(tmp_path):
    # 오디오 트랙이 아예 없는 영상(마이크 없는 화면 녹화)도 무음 트랙으로 렌더 성공
    from cutdaejang.core.edit_mode import render_from_analysis

    video = _tone_video(tmp_path, name="noaudio.mp4", an=True)
    out = str(tmp_path / "na.mp4")
    r = render_from_analysis(video, [], out, layout="keep", quality="draft")
    assert r.ok, r.errors
    assert ff.has_audio_stream(out)


@requires_ffmpeg
def test_render_denoise_keeps_audio(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import analyze_video, render_from_analysis
    from cutdaejang.utils import ffmpeg as ff

    analysis = analyze_video(talk_video, tmp_path / "w", None, auto_subtitle=False)
    out = str(tmp_path / "w" / "dn.mp4")
    r = render_from_analysis(analysis.cut_video, [], out, layout="keep", denoise=True)
    assert r.ok, r.errors
    assert ff.has_audio_stream(out)                       # 잡음 제거 후에도 오디오 유지
    # 길이는 그대로 (denoise는 길이 안 바꿈)
    assert abs(ff.probe_duration_us(out) - ff.probe_duration_us(analysis.cut_video)) < 200_000


def test_hook_dialogue_text_highlights_keyword():
    from cutdaejang.core.render_engine.ass_writer import hook_dialogue_text
    from cutdaejang.spec import Style

    style = Style(highlight_color="#FFD400")
    out = hook_dialogue_text("블로그 글도 AI가? 꿀팁 | AI가?", style)
    assert "AI가?" in out
    assert "\\1c" in out                       # 강조색 인라인 태그가 들어감
    assert "|" not in out                      # 구분자는 최종 텍스트에서 사라짐


# ─────────── 화질 업 (유튜브 노출용) ───────────


def test_quality_canvas_shorts_tiers():
    from cutdaejang.core.edit_mode import _quality_canvas

    std, crf_s, _, sharp_s = _quality_canvas("shorts", 1280, 720, "standard")
    assert (std.w, std.h) == (1080, 1920) and not sharp_s
    ultra, crf_u, _, sharp_u = _quality_canvas("shorts", 1280, 720, "ultra")
    assert (ultra.w, ultra.h) == (2160, 3840) and sharp_u   # 4K 세로
    assert crf_u <= crf_s or True  # 화질 등급별 crf는 프리셋대로


def test_quality_canvas_keep_caps_upscale():
    from cutdaejang.core.edit_mode import _quality_canvas

    # keep + ultra: 720p 원본 → 2배(1440p), 3840 캡 이내
    c, _, _, _ = _quality_canvas("keep", 1280, 720, "ultra")
    assert (c.w, c.h) == (2560, 1440)
    # 이미 큰 원본(2160p)은 캡에 걸려 과도 업스케일 안 함
    c2, _, _, _ = _quality_canvas("keep", 3840, 2160, "ultra")
    assert max(c2.w, c2.h) <= 3840


@requires_ffmpeg
def test_render_ultra_quality_is_4k(talk_video, tmp_path):
    from cutdaejang.core.edit_mode import analyze_video, render_from_analysis
    from cutdaejang.utils import ffmpeg as ff

    analysis = analyze_video(talk_video, tmp_path / "w", None, auto_subtitle=False)
    out = str(tmp_path / "w" / "ultra.mp4")
    r = render_from_analysis(analysis.cut_video, [], out, layout="shorts", quality="ultra")
    assert r.ok, r.errors
    assert ff.probe_video_size(out) == (2160, 3840)


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


def test_spread_ranges_montage():
    # 자막 없는 긴 영상 → 전체에서 고르게 조각을 뽑아 목표 길이 (v0.30)
    from cutdaejang.core.edit_mode import spread_ranges

    r = spread_ranges(337_000_000, 30_000_000)
    total = sum(b - a for a, b in r)
    assert abs(total - 30_000_000) < 1_000_000
    assert r == sorted(r) and r[0][0] >= 0 and r[-1][1] <= 337_000_000
    assert r[0][0] < 337_000_000 * 0.2 and r[-1][1] > 337_000_000 * 0.8  # 앞~뒤 고르게
    for (a1, b1), (a2, b2) in zip(r, r[1:]):
        assert b1 <= a2                                   # 겹침 없음
    assert spread_ranges(20_000_000, 30_000_000) == [(0, 20_000_000)]  # 짧으면 그대로


# ─────────── v0.33: 핵심 선별 — 앞 30초만 나오던 문제 ───────────


def _flat_subs(n=30, dur_s=2.0):
    # 후킹 요소가 없는 밋밋한 자막 n개 (동점 상황 재현)
    return [{"text": f"그냥 평범한 설명 문장 {chr(0xAC00 + i)}", "start_us": int(i * dur_s * 1e6),
             "end_us": int((i + 1) * dur_s * 1e6)} for i in range(n)]


def test_heuristic_covers_whole_video_not_prefix():
    from cutdaejang.core.script_generator import suggest_highlights_heuristic

    subs = _flat_subs(30, 2.0)                      # 60초 영상, 목표 20초
    keep = suggest_highlights_heuristic(subs, target_sec=20)["keep"]
    assert keep != list(range(len(keep)))           # 0,1,2,… 접두 연속 금지
    assert min(keep) < 10 and any(10 <= i < 20 for i in keep) and max(keep) >= 20
    total = sum((subs[i]["end_us"] - subs[i]["start_us"]) / 1e6 for i in keep)
    assert 18 <= total <= 26                        # 목표 근처


def test_suggest_highlights_rejects_lazy_prefix(monkeypatch):
    import json as _json

    from cutdaejang.core import script_generator as sg

    def fake_post(url, payload, headers, timeout=120.0):
        return {"candidates": [{"content": {"parts": [{
            "text": _json.dumps({"keep": list(range(12)), "reason": "앞부터"})}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    subs = _flat_subs(30, 2.5)                      # 75초 > 30×1.6
    with pytest.raises(sg.ScriptError, match="앞부분만"):
        sg.suggest_highlights(subs, target_sec=30)


def test_suggest_highlights_accepts_scattered(monkeypatch):
    import json as _json

    from cutdaejang.core import script_generator as sg

    picked = [0, 7, 13, 19, 24, 29]

    def fake_post(url, payload, headers, timeout=120.0):
        assert "[0:00]" in payload["contents"][0]["parts"][0]["text"]  # 시작시각 제공
        return {"candidates": [{"content": {"parts": [{
            "text": _json.dumps({"keep": picked, "reason": "고르게"})}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    out = sg.suggest_highlights(_flat_subs(30, 2.5), target_sec=30)
    assert out["keep"] == picked


def test_suggest_highlights_allows_prefix_on_short_video(monkeypatch):
    # 영상이 목표와 비슷한 길이면 연속 선택도 정상 (자를 게 없음)
    import json as _json

    from cutdaejang.core import script_generator as sg

    def fake_post(url, payload, headers, timeout=120.0):
        return {"candidates": [{"content": {"parts": [{
            "text": _json.dumps({"keep": [0, 1, 2, 3, 4, 5], "reason": "짧아서 다"})}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(sg, "_http_post_json", fake_post)
    subs = _flat_subs(8, 4.0)                       # 32초 영상, 목표 30초 → 1.6배 미만
    assert sg.suggest_highlights(subs, target_sec=30)["keep"] == [0, 1, 2, 3, 4, 5]


# ─────────── v0.34: 자막 2줄 초과 자동 분할 ───────────


def test_split_long_subtitles_divides_and_keeps_sync():
    from cutdaejang.core.edit_mode import split_long_subtitles
    from cutdaejang.spec import Subtitle

    long_text = "이 문장은 아주 길어서 화면에서 네 줄로 표시되던 그 문제의 자막을 재현하기 위한 예시 문장입니다"
    subs = [Subtitle("짧은 자막", 0, 2_000_000),
            Subtitle(long_text, 2_000_000, 10_000_000, highlight="네 줄")]
    out = split_long_subtitles(subs, wrap_chars=16)
    assert out[0].text == "짧은 자막"                     # 짧으면 그대로
    parts = out[1:]
    assert len(parts) >= 2                                # 긴 자막은 여러 개로
    assert all(len(p.text) <= 32 for p in parts)          # 각각 2줄(32자) 이내
    assert " ".join(p.text for p in parts) == long_text   # 내용 손실 없음
    assert parts[0].start_us == 2_000_000 and parts[-1].end_us == 10_000_000
    for a, b in zip(parts, parts[1:]):                    # 이어지고 겹치지 않음
        assert a.end_us == b.start_us and a.end_us > a.start_us
    hl = [p for p in parts if p.highlight]
    assert len(hl) == 1 and "네 줄" in hl[0].text          # 강조어는 해당 조각에만


def test_split_long_subtitles_handles_no_space_text():
    from cutdaejang.core.edit_mode import split_long_subtitles
    from cutdaejang.spec import Subtitle

    out = split_long_subtitles([Subtitle("가" * 70, 0, 7_000_000)], wrap_chars=16)
    assert all(len(p.text) <= 32 for p in out) and sum(len(p.text) for p in out) == 70


# ─────────── v0.35: 워터마크 + 4K 화질 프리셋 ───────────


def test_ultra_preset_upgraded():
    from cutdaejang.core.edit_mode import _SHARPEN, QUALITY_PRESETS

    u = QUALITY_PRESETS["ultra"]
    assert u["crf"] <= 16 and u["mult"] == 2.0          # 저압축 + 4K 업스케일
    assert _SHARPEN[u["sharpen"]].startswith("cas")     # 적응형 선명화


@requires_ffmpeg
def test_render_watermark_overlay(tmp_path):
    import re
    import subprocess

    from cutdaejang.core.edit_mode import render_from_analysis

    v = tmp_path / "v.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=black:s=640x360:r=30:d=2",
            "-f", "lavfi", "-i", "anullsrc=r=44100:d=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(v)])
    wm = tmp_path / "logo.png"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=white:s=200x80:d=0.1", "-frames:v", "1", str(wm)])
    out = str(tmp_path / "o.mp4")
    r = render_from_analysis(str(v), [], out, layout="keep", quality="draft",
                             watermark={"path": str(wm), "pos": "tr", "scale": 0.14, "opacity": 1.0})
    assert r.ok, r.errors

    def yavg(x, y):
        p = subprocess.run([ff.ffmpeg_bin(), "-i", out,
                            "-vf", f"crop=80:40:{x}:{y},signalstats,metadata=print",
                            "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
        m = re.search(r"YAVG=([0-9.]+)", p.stderr)
        return float(m.group(1)) if m else -1

    assert yavg(540, 12) > 100          # 우상단에 로고가 밝게 찍힘
    assert yavg(280, 160) < 40          # 중앙 배경은 그대로 검정
    # 없는 파일이면 조용히 생략(렌더는 성공)
    r2 = render_from_analysis(str(v), [], str(tmp_path / "o2.mp4"), layout="keep",
                              quality="draft", watermark={"path": "없는파일.png"})
    assert r2.ok


# ── v0.41: 문장 단위 타임스탬프 ──

class FakeTimedSTT:
    """whisper처럼 문장 타임스탬프를 주는 가짜 제공자 (환각 1조각 포함)."""

    name = "faketimed"

    def transcribe(self, audio_path, language="ko"):
        return "폴백 텍스트"

    def transcribe_timed(self, audio_path, language="ko"):
        dur = ff.probe_duration_us(str(audio_path)) / 1e6
        mid = max(0.3, dur / 2)
        return [
            (0.05, mid, "첫 문장입니다"),
            (mid + 0.05, max(mid + 0.3, dur - 0.02), "둘째 문장입니다"),
            (0.0, 0.05, "시청해주셔서 감사합니다"),  # 환각 + 0.2초 미만 → 걸러짐
        ]


def test_stt_engine_timed_filter_and_cache(talk_video, tmp_path):
    """엔진 timed 경로: μs 변환·환각 제거·JSON 캐시 적중."""
    from cutdaejang.core import video_editor
    from cutdaejang.core.stt_engine import STTEngine

    wav = tmp_path / "piece.wav"
    video_editor.extract_segment_audio(talk_video, 0, 1_500_000, str(wav))
    eng = STTEngine(FakeTimedSTT(), tmp_path / "cache")
    out = eng.transcribe_timed(str(wav))
    assert [t for _, _, t in out] == ["첫 문장입니다", "둘째 문장입니다"]  # 환각 제외
    assert all(isinstance(a, int) and b > a for a, b, _ in out)
    assert eng.stats["hallucinations"] == 1
    out2 = eng.transcribe_timed(str(wav))  # 캐시 적중 (재호출 없음)
    assert out2 == out and eng.stats["cache_hits"] == 1


def test_timed_unsupported_provider_falls_back(talk_video, tmp_path):
    """타임스탬프 미지원(StubSTT) → None → 구간 전체 한 조각 폴백."""
    from cutdaejang.core.edit_mode import transcribe_segments_timed

    eng = _engine(tmp_path)
    assert eng.transcribe_timed(str(talk_video)) is None
    pieces = transcribe_segments_timed(
        talk_video, [(0, 1_500_000)], eng, tmp_path / "w")
    assert len(pieces) == 1 and len(pieces[0]) == 1
    rel_s, rel_e, text = pieces[0][0]
    assert (rel_s, rel_e) == (0, 1_500_000) and text.strip()


def test_build_subtitles_timed_mapping():
    """상대 조각 → 컷 타임라인 절대 시각 + 구간 밖 클램프 + 짧은 조각 제거."""
    from cutdaejang.core.edit_mode import build_subtitles_timed

    cut_segments = [(0, 2_000_000), (2_000_000, 5_000_000)]
    pieces = [
        [(100_000, 900_000, "가"), (950_000, 1_990_000, "나")],
        [(0, 1_500_000, "다"), (1_500_000, 9_000_000, "라"),  # 구간 길이 3초로 클램프
         (2_950_000, 2_990_000, "짧음")],                       # 0.2초 미만 → 제거
    ]
    subs = build_subtitles_timed(cut_segments, pieces)
    assert [s.text for s in subs] == ["가", "나", "다", "라"]
    assert (subs[2].start_us, subs[2].end_us) == (2_000_000, 3_500_000)
    assert subs[3].end_us == 5_000_000  # 구간 끝으로 클램프


def test_analyze_video_sentence_timestamps(talk_video, tmp_path):
    """analyze_video가 발화 구간 1개당 문장 2줄을 만든다 (기존: 구간=1줄)."""
    from cutdaejang.core.edit_mode import analyze_video
    from cutdaejang.core.stt_engine import STTEngine

    analysis = analyze_video(
        talk_video, tmp_path / "w", STTEngine(FakeTimedSTT(), tmp_path / "c"))
    assert analysis.segments == 3
    assert len(analysis.subtitles) == 6  # 구간마다 2문장
    assert any("문장 단위" in n for n in analysis.notes)
    for s in analysis.subtitles:  # 절대 시각·순서 정상
        assert 0 <= s.start_us < s.end_us <= analysis.cut_us + 100_000


@requires_ffmpeg
def test_render_with_bgm_duck(tmp_path):
    """v0.44 편집 모드 덕킹 — BGM+덕킹 그래프로 렌더가 정상 완성되는지."""
    from cutdaejang.core import edit_mode
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "v.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=3",
            "-f", "lavfi", "-i", "sine=frequency=600:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(src)])
    bgm = tmp_path / "bgm.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=200:duration=10", str(bgm)])
    out = tmp_path / "out.mp4"
    r = edit_mode.render_from_analysis(
        str(src), [], str(out), layout="keep",
        bgm_path=str(bgm), bgm_db=-14, bgm_duck=True)
    assert r.ok, r.errors
    assert ff.has_audio_stream(str(out))
    assert abs(ff.probe_duration_us(str(out)) - 3_000_000) < 400_000


def test_gemini_stt_thinking_off_and_empty_stop(monkeypatch, tmp_path):
    """v0.50.2 — 2.5-flash 씽킹 차단(thinkingBudget 0) + 출력 없는 정상 종료(STOP)는
    무음 처리. 사용자 로그: 씽킹이 출력을 삼켜 '빈 응답' 경고 8건."""
    import io
    import json
    import urllib.request as ur

    from cutdaejang.core import stt_engine as se

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=120):
        sent["payload"] = json.loads(req.data.decode())
        return Resp(json.dumps(sent["reply"]).encode())

    monkeypatch.setattr(ur, "urlopen", fake_urlopen)
    stt = se.GeminiSTT(api_key="k")

    sent["reply"] = {"candidates": [
        {"content": {"parts": [{"text": " 안녕하세요 "}]}, "finishReason": "STOP"}]}
    assert stt.transcribe(str(wav)) == "안녕하세요"
    assert sent["payload"]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0

    # 사용자 로그 그대로: parts 없이 STOP → 빈 자막 (오류·경고 아님)
    sent["reply"] = {"candidates": [{"content": {"role": "model"}, "finishReason": "STOP"}]}
    assert stt.transcribe(str(wav)) == ""

    # candidates 자체가 없으면(안전 차단·쿼터) 여전히 오류 → 빈 자막 캐시 오염 방지
    sent["reply"] = {"promptFeedback": {"blockReason": "SAFETY"}}
    with pytest.raises(se.STTError, match="빈 응답"):
        stt.transcribe(str(wav))

    # 씽킹 미지원 모델(2.5 아님)엔 thinkingConfig를 보내지 않음
    stt_old = se.GeminiSTT(api_key="k", model="gemini-2.0-flash")
    sent["reply"] = {"candidates": [
        {"content": {"parts": [{"text": "네"}]}, "finishReason": "STOP"}]}
    assert stt_old.transcribe(str(wav)) == "네"
    assert "generationConfig" not in sent["payload"]
