"""v0.74 — 그림체 다양화 + 타이핑 자막 + 인스타·틱톡(reels) 특화 + 본문 자막 실물 미리보기.

사용자 요청: (1) 그림체 더 다양하게 (2) 자막 스타일 적용 효과를 눈으로 보기
(3) 인스타/틱톡은 화면 중앙 타이핑 자막 (4) 인스타·틱톡 특화 출력 옵션.
"""

import re

from cutdaejang.core import background_generator as bg
from cutdaejang.core.orchestrator import build_style
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.spec import Subtitle, Style


# ── 1) 그림체 다양화 (6종 → 12종) ─────────────────────────────────────────
def test_more_image_styles():
    for k in ("웹툰", "지브리풍", "유화", "동화", "흑백", "픽셀아트"):
        assert k in bg.IMAGE_STYLES, f"그림체 누락: {k}"
    assert len(bg.IMAGE_STYLES) >= 12
    # 서술형 프롬프트라 길이가 충분
    assert all(len(v) > 10 for v in bg.IMAGE_STYLES.values())


# ── 2) 타이핑 자막 (anim="type") ─────────────────────────────────────────
def _sub(t, hl=""):
    return Subtitle(text=t, start_us=0, end_us=2_000_000, highlight=hl)


def test_typing_body_reveals_each_char():
    body = aw._typing_body("가나다", "#FF3B30", cps=20)
    assert body.count("alpha&HFF&") == 3          # 글자 3개 각각 리빌
    assert body.count("\\t(") == 3                 # 글자마다 \t 타이밍
    assert aw._inline_color("#FF3B30") in body     # 줄 색 한 번


def test_typing_body_skips_newline_from_timing():
    body = aw._typing_body("가\n나", "#FFFFFF", cps=20)
    assert "\\N" in body
    assert body.count("alpha&HFF&") == 2           # 줄바꿈은 글자수에 안 셈


def test_dialogue_text_typing_no_fade_pop():
    style = Style(anim="type")
    body = aw.dialogue_text(_sub("이렇게 나와요"), style)
    assert "alpha&HFF&" in body                    # 타이핑 리빌
    assert "\\fad(" not in body                    # 타이핑이 등장연출 → 페이드 없음
    assert "\\fscx86" not in body                  # 팝도 없음


def test_typing_respects_manual_markup():
    style = Style(anim="type")
    body = aw.dialogue_text(_sub("[민트]직접[/] 색"), style)
    assert aw._inline_color("#31E1C4") in body      # 수동 색 존중
    assert "alpha&HFF&" not in body                 # 마크업 있으면 타이핑 미적용


def test_typing_uses_pop_color():
    style = Style(anim="type")
    body = aw.dialogue_text(_sub("문장"), style, pop_color="#FFD400")
    assert aw._inline_color("#FFD400") in body       # 다색 팝 회전색 + 타이핑


# ── 3) 인스타·틱톡(reels) 특화 프리셋 ─────────────────────────────────────
def _settings(sub_style="기본", anim="none"):
    return {"subtitle": {"font_size": 64, "outline": 4, "sub_style": sub_style, "anim": anim},
            "bg": {}}


def test_reels_forces_center_typing_pop():
    st = build_style(_settings(), "reels")
    assert st.position == "center"
    assert st.anim == "type"
    assert st.sub_style == "다색 팝"


def test_reels_respects_user_sub_style():
    st = build_style(_settings(sub_style="네온"), "reels")
    assert st.sub_style == "네온"          # 사용자가 고른 건 그대로
    assert st.position == "center" and st.anim == "type"


def test_shorts_unchanged_by_reels_logic():
    st = build_style(_settings(), "shorts")
    assert st.position == "bottom" and st.anim == "none" and st.sub_style == "기본"


def test_job_options_preserves_reels():
    from cutdaejang.gui import webui
    opt = webui._job_options({"orientation": "reels"})
    assert opt.orientation == "reels"
    opt2 = webui._job_options({"orientation": "wide"})
    assert opt2.orientation == "wide"
    opt3 = webui._job_options({"orientation": "shorts"})
    assert opt3.orientation == "shorts"


# ── 4) UI: 새 옵션·미리보기 배선 ─────────────────────────────────────────
def test_html_has_reels_and_typing_and_styles():
    from cutdaejang.gui import webui
    html = webui._HTML
    assert 'value="reels"' in html                          # 인스타·틱톡 라디오
    assert 'value="type"' in html and "타이핑" in html       # 타이핑 애니메이션 옵션
    for k in ("웹툰", "지브리풍", "픽셀아트"):                 # 새 그림체 옵션
        assert f'value="{k}"' in html
    # 본문 자막 실물 미리보기 배선
    assert "SUB_STYLE_CSS" in html and "subStylePreviewInto" in html
    # 훅 미리보기도 v0.73 프리셋 반영
    assert "'다색 팝'" in html and "'블랙 박스'" in html
