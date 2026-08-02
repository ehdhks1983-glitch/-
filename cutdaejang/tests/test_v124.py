"""v1.24 — 쇼핑 링크 영상 지적 7건 (목록 40~46).

회원님 19차(2026-08-02, 쇼핑 카드·완성 영상 스샷 4장):
40. "1번에 쿠팡 창 열기가 있는데 굳이 2번 밑에 상품 검색으로 고르기 칸이 필요해?"
    → 역할이 다른 기능이라 지우지 않고 **라벨로 역할을 드러내기**(회원님 ② 선택).
41. "감성 테마 랜덤도 하나 있음 좋겠어" → "체크하면 다르게 들어가야겠지"
    → 고를 때마다·배치는 영상마다 다시 뽑는다.
43. "금액이나 숫자를 자막에서도 숫자로 보여줘야 하는데 한글로 반영"
    → 대본 프롬프트가 "숫자를 한글로 쓰라"고 시켰던 게 원인. 낭독은 이미
    pronounce_ko가 자동 변환하므로 대본은 숫자 그대로 쓰게 한다.
44. "나레이션이 또 부드럽게 안 이어짐" (이전엔 잘 됐는데 재발)
    → 한 문장이 자막 두 줄로 쪼개진 대본에서 줄마다 따로 합성하면 문장 한가운데에
    종결 억양+0.35초 무음이 들어간다. 문장 단위로 묶어 합성 후 줄별로 나눈다.
45. "자막 잘 보이게, 설명 초보자도 알기 쉽게, 문단도 칸에 잘 맞게" (둘 다)
46. "히스토리에 폴더 열기 추가"
"""

import re

from cutdaejang import __version__
from cutdaejang.core import edit_mode
from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui
from cutdaejang.utils.pronounce import pronounce_ko


def test_version():
    assert __version__ == "1.27.0"


# ── 43. 자막은 숫자, 소리는 한글 발음 ──────────────────────────────
def test_script_prompt_keeps_digits():
    """대본 프롬프트가 더는 '숫자를 한글로'라고 시키지 않는다."""
    src = open("cutdaejang/core/script_generator.py", encoding="utf-8").read()
    assert "숫자·영어 약어는 한글 발음으로 표기" not in src
    assert src.count("숫자·단위·영어는 쓰인 그대로") == 2   # 대본 2곳(생성·쇼핑)


def test_pronounce_still_reads_digits_aloud():
    """자막을 숫자로 둬도 낭독은 한글로 — 이게 있어서 프롬프트를 뺄 수 있다."""
    assert pronounce_ko("약 23,800원인데요") == "약 이만삼천팔백원인데요"
    assert pronounce_ko("별점은 4.8점이에요") == "별점은 사점팔점이에요"
    assert "오십퍼센트" in pronounce_ko("50% 할인")


# ── 44. 문장 단위 묶기 (내레이션 이어짐) ───────────────────────────
def test_group_sentence_units_merges_split_lines():
    """종결부호 없는 줄은 다음 줄과 한 문장 — 회원님 쇼핑 대본 실제 사례.

    v1.27 갱신: "…제품인데요." "…나왔고요."도 **마침표가 있어도 뒷말로 이어지는
    말**이라 이제 함께 묶인다(예전 기대값 [[0,1],[2],[3]]). 실제로 이 두 줄은 한
    호흡으로 읽는 게 맞고, 사이에 침묵이 들어가던 것이 목록 44번의 증상이었다.
    """
    texts = ["리뷰 십오만 개 넘는", "섬유유연제가 있어요.",
             "바로 스너글 제품인데요.", "초고농축으로 나왔고요."]
    assert edit_mode.group_sentence_units(texts) == [[0, 1], [2, 3]]


def test_group_sentence_units_skips_when_no_punctuation():
    """음성 인식 자막처럼 구두점이 원래 없는 대본은 묶지 않는다(안전장치)."""
    texts = ["안녕하세요 오늘은", "라멘 맛집을", "소개합니다"]
    assert edit_mode.group_sentence_units(texts) == [[0], [1], [2]]


def test_group_sentence_units_caps_long_runs():
    """종결부호가 계속 없어도 3줄·90자를 넘기지 않는다(무한 병합 방지)."""
    texts = ["가", "나", "다", "라.", "마."]
    units = edit_mode.group_sentence_units(texts)
    assert all(len(u) <= 3 for u in units)
    assert [i for u in units for i in u] == [0, 1, 2, 3, 4]   # 빠지는 줄 없음


def test_retime_joins_close_gap_inside_sentence(tmp_path, monkeypatch):
    """같은 문장을 쪼갠 줄 사이는 간격 0 — 이어 붙이면 원래 소리 그대로."""
    from cutdaejang.spec import Subtitle

    monkeypatch.setattr(edit_mode.ff, "probe_duration_us", lambda *_a, **_k: 1_000_000)
    subs = [Subtitle(text=f"줄{i}", start_us=0, end_us=1) for i in range(3)]
    clips = [str(tmp_path / f"c{i}.wav") for i in range(3)]
    out, _c, _n = edit_mode.retime_narration(
        clips, subs, 10_000_000, tmp_path, fit="freeze", joins=[True, False])
    assert out[1].start_us == out[0].end_us              # 문장 안 → 붙임
    assert out[2].start_us > out[1].end_us               # 문장 사이 → 간격 유지


# ── 41. 감성 테마 랜덤 ────────────────────────────────────────────
def test_random_theme_option_everywhere():
    html = webui._HTML
    assert html.count('<option value="rand">') == 5      # 테마 셀렉트 5곳 전부
    assert html.count("rollRandomTheme('") == 5          # 시작 함수 5곳에서 호출
    assert "if(sel.value === 'rand') return;" in html    # 랜덤은 시작 때 뽑는다


def test_server_batch_themes_match_screen():
    """배치(여러 줄)는 서버가 영상마다 뽑는다 — 조합이 화면 THEMES와 같아야 함."""
    html = webui._HTML
    js = set(re.findall(r"sub_style: '([^']+)', tone: '([^']+)'", html))
    assert len(webui.THEMES_SRV) == 10        # 화면 10종과 개수 일치
    assert set(webui.THEMES_SRV.values()) == js   # 조합도 동일 (중복 조합은 한 번만)


# ── 45. 가독성 (화면 + 영상 자막) ─────────────────────────────────
def test_shop_guide_is_stepwise_not_wall():
    html = webui._HTML
    assert "전체 페이지를 보여줘요. <b>[창 열기] → 그 창에서" not in html   # 6줄 벽글 제거
    assert "① <b>[창 열기]</b>를 누르고" in html
    assert '<span class="stepnum">4</span>대본 확인' in html            # 3 중복 해소


def test_success_banner_is_not_red():
    html = webui._HTML
    assert ".banner.ok" in html
    assert "b.classList.toggle('ok', okMark);" in html


def test_extra_large_subtitle_choice():
    html = webui._HTML
    assert '<button class="ghost ezchip" data-v="124">특대</button>' in html
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert 'max(40, min(128, sub["font_size"]))' in src        # 상한도 함께 상향


# ── 40 / 46 ─────────────────────────────────────────────────────
def test_product_search_label_explains_role():
    html = webui._HTML
    assert "API 키를 넣으면 파트너스 사이트에 안 가도" in html
    assert "선택 기능 — 안 쓰셔도 됩니다" in html


def test_history_has_folder_button():
    html = webui._HTML
    assert "histFolder(" in html and "결과 폴더 열기" in html


# ── 42. AI 추천·다듬기가 오래 멈춘 것처럼 보이지 않게 ────────────────
def test_ai_calls_have_shorter_timeout():
    """구글 503 때 2분 굳는 대신 45초 안에 대략 추천으로 넘어간다."""
    src = open("cutdaejang/core/script_generator.py", encoding="utf-8").read()
    for fn in ("def suggest_highlights(", "def refine_subtitles("):
        seg = src[src.index(fn):src.index(fn) + 2500]
        assert "timeout=45.0" in seg, fn


def test_highlight_fallback_still_works():
    """키가 없으면 후킹 점수 방식으로 — 폴백은 그대로 살아 있다."""
    subs = [{"text": f"문장 {i}", "start_us": i * 1_000_000,
             "end_us": (i + 1) * 1_000_000} for i in range(10)]
    res = sg.suggest_highlights_heuristic(subs, target_sec=4)
    assert res["keep"] and all(0 <= i < 10 for i in res["keep"])
