"""v1.51 — 목록 104·105: 즐겨찾기 목소리 따로 보기 + 꾸미기 미리보기 전항목 반영.

회원님 51차:
> "내가 선호하는 목소리를 따로 저장시켜 놓고 볼 수 있는 게 있음 좋겠어" (104)
> "꾸미기에서 기능들을 넣으면 제대로 보였음 해. 어떤 기능인지,
>  어떤 건 되고 어떤 건 안 됨" (105)

104의 발견: ☆ 즐겨찾기는 v0.67부터 있었는데 ★ 접두 정렬뿐이라 안 보였다
→ 「⭐ 내 즐겨찾기」 optgroup으로 분리 + 한 글자 ☆ 버튼에 라벨.
105의 발견: 제목/자막 배경 띠 체크·화면 톤·자막 글씨 버튼이 미리보기에
반영되지 않았다 → 체크가 프리셋을 이기게 + 톤 CSS 필터 + 안내 줄.
"""

import re

from cutdaejang import __version__
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.51.0"


# ── 104. 즐겨찾기 성우 따로 보기 ───────────────────────────────
def test_favorites_render_as_separate_group():
    """★ 접두 정렬이 아니라 「⭐ 내 즐겨찾기」 그룹으로 분리돼야 «따로 보인다»."""
    assert "⭐ 내 즐겨찾기" in JS
    assert "createElement('optgroup')" in JS
    assert "'⭐ 내 즐겨찾기 (일레븐랩스)'" in JS, "내레이션 셀렉트에도 같은 그룹"


def test_favorites_group_pinned_to_top_of_narr_list():
    """내레이션 목록은 비-일레븐 옵션이 앞에 있어, 그룹을 맨 앞에 꽂아야 보인다."""
    assert "nv.insertBefore(" in JS and "nv.firstChild" in JS


def test_empty_favorites_hint_in_group_label():
    """즐겨찾기가 없을 때도 «☆를 누르면 모인다»를 그룹 라벨로 알려준다."""
    assert "☆ 즐겨찾기를 누르면 맨 위에 모여요" in JS


def test_narr_fav_button_has_text_label():
    """한 글자 ☆라 아무도 못 알아봤다 — 라벨을 붙인다."""
    assert '>☆ 즐겨찾기</button>' in HTML
    assert "'★ 즐겨찾기됨' : '☆ 즐겨찾기'" in JS


def test_stale_optgroups_removed_on_rerender():
    """다시 렌더할 때 이전 el: 옵션과 빈 그룹을 청소해야 중복이 안 쌓인다."""
    assert "g.tagName === 'OPTGROUP'" in JS


# ── 105. 꾸미기 미리보기 전항목 반영 ───────────────────────────
def test_band_checkboxes_drive_preview():
    """제목/자막 배경 띠 체크박스가 미리보기 프리셋 기본값을 이긴다."""
    assert "querySelector('.qd-band')" in JS
    assert "querySelector('.qd-hookband')" in JS
    assert "bandC ? bandC.checked : !!ss.band" in JS
    assert "hbC ? hbC.checked : (('band' in hs) ? hs.band : true)" in JS


def test_tone_applies_css_filter_to_preview():
    """화면 톤 5종이 미리보기 틀에 CSS 필터로 근사 반영."""
    assert "PV_TONE" in JS and "fr.style.filter" in JS
    for tone in ("'기본'", "'시네마틱'", "'화사'", "'선명'", "'흑백'"):
        assert tone in JS, tone
    assert "grayscale(1)" in JS


def test_tone_selects_wired_into_pv_ids():
    for tid in ("genToneSel", "editToneSel", "wlToneSel", "secToneSel", "shopToneSel"):
        assert f"tone:'{tid}'" in JS, tid


def test_video_only_legend_under_preview():
    """미리보기에 «안» 나오는 것 안내 줄 — 어떤 건 되고 안 되는지 답."""
    assert 'class="pvonly hint"' in JS
    assert "영상에서만 나오는 것" in JS
    assert "나머지는 전부 위 미리보기에 보여요" in JS


def test_size_and_cards_clicks_refresh_preview():
    """자막 글씨(작게~특대)·텍스트 카드 클릭도 미리보기 즉시 반영."""
    assert ".qd-size,.qd-cards" in JS
    assert "refreshDecoSummaries(); _pvSchedule();" in JS
