"""v0.75 「훅 팩」 — 콜드오픈(클라이맥스 티저) + AI 후킹 보이스 + 14~15초 재훅.

알파컷式 리텐션 엔지니어링 대응: ① 핵심추출 시 가장 궁금한 순간을 맨 앞 티저로,
② 훅 제목을 성우가 읽는 인트로 프리펜드, ③ 대본 1/4 지점 재훅 문장에 펀치인+효과음.
"""
import json

import pytest

from cutdaejang.core import script_generator as sg
from cutdaejang.core.orchestrator import (JobOptions, _hook_voice_text,
                                          pick_rehook_index)
from cutdaejang.core.script_generator import Script
from cutdaejang.utils import ffmpeg as ff


# ── ① 대본: rehook 플래그 ──────────────────────────────────────────────


def test_script_parses_rehook_flag():
    s = Script.from_json_text(json.dumps({
        "title": "t",
        "sentences": [
            {"text": "훅 문장", "highlight": "", "scene": ""},
            {"text": "재훅!", "highlight": "", "scene": "", "rehook": True},
            {"text": "마무리", "highlight": "", "scene": ""},
        ],
    }))
    assert s.rehook_idx == 1


def test_script_rehook_roundtrips_and_clamps():
    s = Script.from_json_text(
        '{"title":"t","sentences":[{"text":"a"},{"text":"b","rehook":true}]}')
    assert Script.from_json_text(s.to_json()).rehook_idx == s.rehook_idx == 1
    # 범위 밖 지정은 -1로 정규화
    assert Script(title="x", sentences=["a"], rehook_idx=7).rehook_idx == -1
    # 표시가 없으면 -1
    assert Script.from_json_text('{"title":"t","sentences":["a","b"]}').rehook_idx == -1


def test_prompts_mention_rehook_and_climax():
    assert "rehook" in sg.PROMPT_TEMPLATE          # 대본 프롬프트: 재훅 규칙
    assert "콜드오픈" in sg.PROMPT_TEMPLATE          # 콜드오픈 훅 강화 규칙
    assert "climax" in sg.HIGHLIGHT_PROMPT         # 핵심추출: 클라이맥스 번호


# ── ② 클라이맥스 선택 ─────────────────────────────────────────────────


def _subs():
    return [
        {"text": "그냥 인사말입니다", "start_us": 0, "end_us": 2_000_000},
        {"text": "충격! 90% 할인 비밀?", "start_us": 10_000_000, "end_us": 12_000_000},
        {"text": "평범한 설명 문장", "start_us": 20_000_000, "end_us": 22_000_000},
        {"text": "결론은 이렇습니다", "start_us": 30_000_000, "end_us": 32_000_000},
    ]


def test_pick_climax_prefers_hooky_nonfirst():
    assert sg.pick_climax(_subs(), [0, 1, 2, 3]) == 1  # 숫자+?+키워드 문장


def test_pick_climax_skips_first_kept_and_handles_small():
    # keep의 첫 문장은 제외 (어차피 맨 앞이라 티저 의미 없음)
    assert sg.pick_climax(_subs(), [1]) == -1
    assert sg.pick_climax([], []) == -1


def test_suggest_highlights_parses_climax(monkeypatch):
    resp = {"candidates": [{"content": {"parts": [{"text": json.dumps(
        {"keep": [0, 1, 3], "climax": 1, "reason": "r"})}]}}]}
    monkeypatch.setattr(sg, "_http_post_json", lambda *a, **k: resp)
    out = sg.suggest_highlights(_subs(), target_sec=30, api_key="k")
    assert out["keep"] == [0, 1, 3] and out["climax"] == 1


def test_suggest_highlights_invalid_climax_falls_back(monkeypatch):
    resp = {"candidates": [{"content": {"parts": [{"text": json.dumps(
        {"keep": [0, 1, 3], "climax": 2, "reason": "keep에 없는 번호"})}]}}]}
    monkeypatch.setattr(sg, "_http_post_json", lambda *a, **k: resp)
    out = sg.suggest_highlights(_subs(), target_sec=30, api_key="k")
    assert out["climax"] == 1  # keep 밖 → 후킹 점수로 대체


def test_heuristic_returns_climax_key():
    out = sg.suggest_highlights_heuristic(_subs(), target_sec=10)
    assert "climax" in out and (out["climax"] == -1 or out["climax"] in out["keep"])


# ── ③ 재훅 위치 선택 ──────────────────────────────────────────────────


def test_rehook_picks_nearest_to_14s():
    starts = [0, 5_000_000, 13_500_000, 25_000_000]
    assert pick_rehook_index(starts, 40_000_000) == 2


def test_rehook_respects_script_flag_and_guards():
    starts = [0, 9_000_000, 13_500_000, 25_000_000]
    assert pick_rehook_index(starts, 40_000_000, scripted_idx=1) == 1
    # 지정이 너무 이르면(8초 미만) 14초 근처로 대체
    starts2 = [0, 2_000_000, 13_500_000, 25_000_000]
    assert pick_rehook_index(starts2, 40_000_000, scripted_idx=1) == 2
    # 20초 미만 영상·문장 4개 미만이면 미적용
    assert pick_rehook_index(starts, 15_000_000) == -1
    assert pick_rehook_index([0, 10_000_000, 14_000_000], 40_000_000) == -1


def test_hook_voice_text_strips_markup():
    assert _hook_voice_text("[노랑]충격[/] 사실|충격") == "충격 사실"
    assert _hook_voice_text("") == ""
    assert _hook_voice_text("그냥 제목") == "그냥 제목"


def test_job_options_has_hook_voice_default_off():
    assert JobOptions().hook_voice is False


# ── ④ 콜드오픈 재컷 (실제 ffmpeg) ────────────────────────────────────


@pytest.fixture()
def sample_video(tmp_path):
    """12초 컬러 영상 + 무음 오디오 (컷·티저 검증용)."""
    p = tmp_path / "src.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=12",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=12",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-c:a", "aac", "-shortest", str(p)])
    return str(p)


def _mk_subs():
    from cutdaejang.spec import Subtitle
    return [
        Subtitle(text="첫 문장", start_us=500_000, end_us=2_000_000),
        Subtitle(text="충격! 90% 비밀?", start_us=5_000_000, end_us=7_000_000),
        Subtitle(text="마무리 결론", start_us=9_000_000, end_us=10_500_000),
    ]


def test_rebuild_cold_open_puts_teaser_first(sample_video, tmp_path):
    from cutdaejang.core import edit_mode

    subs = _mk_subs()
    video, out_subs, teaser_s = edit_mode.rebuild_cold_open(
        sample_video, subs, [0, 1, 2], str(tmp_path / "co.mp4"), climax_idx=1)
    assert teaser_s > 0.5
    # 첫 자막 = 클라이맥스 문장이 0초부터 (티저)
    assert out_subs[0].text == "충격! 90% 비밀?" and out_subs[0].start_us == 0
    # 본편 자막은 티저 길이만큼 뒤로 밀림 (원래 순서 유지)
    assert out_subs[1].text == "첫 문장" and out_subs[1].start_us >= teaser_s * 1e6 - 1
    # 결과 길이 ≈ 티저 + 본편(자막 구간 합 + 패드)
    got = ff.probe_duration_us(video) / 1e6
    assert got > teaser_s + 4.0  # 본편 3구간이 뒤에 실제로 존재


def test_rebuild_cold_open_falls_back_when_climax_is_opening(sample_video, tmp_path):
    from cutdaejang.core import edit_mode

    subs = _mk_subs()
    # 클라이맥스가 첫 구간이면 티저 의미 없음 → 일반 재컷과 동일 (teaser 0)
    video, out_subs, teaser_s = edit_mode.rebuild_cold_open(
        sample_video, subs, [0, 1], str(tmp_path / "co2.mp4"), climax_idx=0)
    assert teaser_s == 0.0
    assert out_subs[0].text == "첫 문장"


def test_rebuild_cold_open_auto_picks_climax(sample_video, tmp_path):
    from cutdaejang.core import edit_mode

    subs = _mk_subs()
    video, out_subs, teaser_s = edit_mode.rebuild_cold_open(
        sample_video, subs, None, str(tmp_path / "co3.mp4"), climax_idx=-1)
    # 후킹 점수로 '충격! 90% 비밀?'이 자동 선택돼 티저로
    assert teaser_s > 0.5 and out_subs[0].text == "충격! 90% 비밀?"


# ── ⑤ 후킹 보이스 인트로 (실제 ffmpeg) ───────────────────────────────


def test_hook_intro_clip_prepends_with_audio(sample_video, tmp_path):
    from cutdaejang.core import video_editor

    voice = tmp_path / "hook.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2:sample_rate=44100",
            str(voice)])
    intro = video_editor.hook_intro_clip(
        sample_video, str(voice), str(tmp_path / "intro.mp4"))
    d = ff.probe_duration_us(intro) / 1e6
    assert 1.2 <= d <= 2.2          # 음성 1.2초 + 꼬리 0.35초 부근
    assert ff.has_audio_stream(intro)
    merged = video_editor.attach_branding(
        sample_video, intro, "", str(tmp_path / "merged.mp4"))
    total = ff.probe_duration_us(merged) / 1e6
    assert total >= 12 + d - 1.0    # 본편 12초 + 인트로 (concat 오차 여유)


# ── ⑥ UI 배선 ────────────────────────────────────────────────────────


def test_webui_wiring():
    from cutdaejang.gui import webui

    assert "cold_open" in webui._EDIT_LAST_KEYS
    assert "hook_voice" in webui._EDIT_LAST_KEYS
    for i in ("editColdOpen", "editHookVoice", "genHookVoice"):
        assert f'id="{i}"' in webui._HTML, i


def test_job_options_plumbs_hook_voice():
    from cutdaejang.gui.webui import _job_options

    assert _job_options({"hook_voice": True, "tts_provider": "stub"}).hook_voice is True
    assert _job_options({"tts_provider": "stub"}).hook_voice is False
