"""v1.11 — 의미 기반 장면 8종·글꼴 조합·속도 대상 분리."""

from pathlib import Path

import pytest

from cutdaejang import config
from cutdaejang.core import edit_mode, orchestrator, text_cards
from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.spec import Style, Subtitle
from cutdaejang.utils import ffmpeg as ff
from tests.test_spec import make_valid_spec


def test_semantic_card_plan_has_eight_scene_roles():
    texts = [
        "매출이 95% 늘었습니다",
        "설명을 이어갑니다",
        "왜 이런 차이가 생길까요?",
        "다음 설명입니다",
        "기존 제품과 새 제품의 차이",
        "계속 이어지는 평범한 문장입니다",
        "직접 써보니 정말 만족했어요",
        "조금 더 설명합니다",
        "꼭 기억할 핵심 3가지",
        "내용을 이어갑니다",
        "먼저 첫째 단계부터 시작합니다",
        "다시 내용을 설명합니다",
        "지금 프로필 링크에서 확인하세요",
        "마지막 설명을 이어갑니다",
        "단 하나의 핵심",
    ]
    plan = text_cards.pick_card_plan(
        texts, duration_us=120_000_000, density="rich", content_pack="auto")
    kinds = {c.kind for c in plan}
    assert len(kinds) >= 6
    examples = {
        "95%가 선택": "number", "왜 그럴까요?": "search",
        "A와 B 비교": "compare", "직접 써본 솔직 후기": "review",
        "꼭 기억할 핵심 3가지": "checklist", "먼저 첫째 단계": "steps",
        "지금 링크를 확인하세요": "cta", "단 하나": "punch",
    }
    assert {text_cards.classify_card(t) for t in examples} == set(examples.values())
    assert all(abs(a.index - b.index) > 1 for a, b in zip(plan, plan[1:]))


def test_manual_card_kind_and_duration_density():
    assert text_cards.marked_kind("[카드:후기] 솔직 후기") == "review"
    assert text_cards.strip_mark("[카드:CTA] 지금 확인") == "지금 확인"
    assert text_cards.card_limit(30_000_000, 30, "auto") == 3
    assert text_cards.card_limit(60_000_000, 30, "rich") > 5
    plan = text_cards.pick_card_plan(
        ["[카드:비교] A와 B", "바로 다음 문장"], duration_us=10_000_000)
    assert plan[0].kind == "compare" and plan[0].manual


def test_ass_contains_distinct_manual_scene_templates(tmp_path):
    spec = make_valid_spec()
    base = list(spec.subtitles)
    # 수동 지정은 자동 상한보다 우선한다. 타이밍은 검증이 필요 없는 ASS 단위 테스트.
    labels = ["숫자", "펀치", "목록", "비교", "후기", "검색", "단계", "CTA"]
    spec.subtitles = [
        Subtitle(text=f"[카드:{name}] 장면 {i + 1}의 핵심 95%",
                 start_us=i * 1_000_000, end_us=(i + 1) * 1_000_000)
        for i, name in enumerate(labels)
    ]
    spec.duration_us = 8_000_000
    # v1.22부터 기본은 영상마다 룩이 변하는 시드 — 이 테스트는 "8종 템플릿이
    # 서로 다른 구조로 나온다"는 클래식 기준을 검사하므로 클래식(-1)으로 고정.
    from dataclasses import replace as _rp
    spec.style = _rp(spec.style, card_seed=-1)
    out = tmp_path / "v111.ass"
    write_ass(spec, out)
    ass = out.read_text(encoding="utf-8")
    for token in ("KEY NUMBER", "CHECK", "REVIEW", "SEARCH", "STEP", "지금 확인"):
        assert token in ass
    assert "A" in ass and "B" in ass
    assert "[카드:" not in ass
    spec.subtitles = base


def test_font_pack_applies_bundled_pair():
    settings = config.deep_merge(config.DEFAULTS, {
        "subtitle": {"font_pack": "impact", "font": "Jua-Regular",
                     "hook_font": "NanumPenScript-Regular"}})
    style = orchestrator.build_style(settings)
    assert style.font == "DoHyeon-Regular"
    assert style.hook_font == "BlackHanSans-Regular"
    assert style.font_pack == "impact"


@pytest.fixture()
def four_second_video(tmp_path):
    try:
        exe = ff.ffmpeg_bin()
    except Exception as exc:  # pragma: no cover - 환경별 선택
        pytest.skip(str(exc))
    src = tmp_path / "speed_src.mp4"
    ff.run([
        exe, "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(src),
    ])
    return src


@pytest.mark.parametrize("mode,expected", [
    ("all", 2.0),
    ("voice", 4.0),
    ("video", 4.0),
])
def test_speed_modes_have_expected_output_length(four_second_video, tmp_path,
                                                 mode, expected):
    work = tmp_path / mode
    work.mkdir()
    out = work / "out.mp4"
    subs = [Subtitle(text="속도 대상 분리", start_us=1_000_000, end_us=3_000_000)]
    style = Style(text_cards=False)
    result = edit_mode.render_from_analysis(
        str(four_second_video), subs, str(out), style=style,
        layout="keep", speed=2.0, speed_mode=mode, quality="draft")
    assert result.ok, result.errors
    duration = ff.probe_duration_us(str(out)) / 1_000_000
    assert abs(duration - expected) < 0.35
    assert ff.has_audio_stream(str(out))
    ass = (work / "subs.ass").read_text(encoding="utf-8")
    if mode == "voice":
        assert "0:00:00.50,0:00:01.50" in ass
    else:
        assert "0:00:01.00,0:00:03.00" in ass


def test_webui_has_speed_target_and_scene_controls():
    from cutdaejang.gui import webui

    html = webui._HTML
    for token in (
        'id="editSpeedModeSel"', 'id="outSpeedMode"',
        'value="voice"', 'value="video"',
        'id="setCardPack"', 'id="setCardDensity"', 'id="setFontPack"',
        "speed_mode:", "card_density:",
    ):
        assert token in html
