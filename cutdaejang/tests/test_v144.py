"""v1.44 — 목록 87(📺 꾸미기 미리보기 틀) + 86(🖋 손글씨 팝).

회원님 44차 (참고 릴스 스샷 5장):
> "자막이나 설정 같은 걸 골랐을 때 화면 같은 곳에 예시 화면이 있음 좋겠어.
>  설정은 많은데 어떤 건지 모르겠어. 글씨체부터 효과 등등 모두 다"
> "이런 자막 스타일 같은 것도 넣고 싶고" (대형 손글씨+형광 줄마다)

조사에서 확인한 것: 스샷 스타일 절반(화이트 박스·다색 강조·예능 노랑)은
«이미 있는데 몰라서 못 쓰는» 상태였다 — 조각 미리보기(글씨체 실물 v0.68,
견본 칩 v0.60)만 있고 «합쳐 보는 틀»이 없어서다. 그래서 87이 본질이고
86(신규 프리셋 1종)이 그 위에 올라탄다.
"""

import json
import re
import tempfile
import threading
import urllib.request

import pytest

from cutdaejang import __version__, presets
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.gui import webui
from cutdaejang.spec import Canvas, Style, Subtitle, TimelineSpec

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def _render(sub_style, text, hl=""):
    subs = [Subtitle(text=text, start_us=0, end_us=10**6, highlight=hl)]
    spec = TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목",
                        subtitles=subs, style=Style(sub_style=sub_style),
                        duration_us=10**6)
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(spec, p)
    return open(p, encoding="utf-8").read()


def test_version():
    assert __version__ == "1.44.0"


# ── 🖋 손글씨 팝 (86) ───────────────────────────────────────────
def test_handpop_preset_shape():
    ss = aw.SUB_STYLES["손글씨 팝"]
    assert ss["line_rotate"] == ["#FFE94D", "#B8F268"], "형광 노랑/연두 두 색"
    assert ss["scale"] > 1.1, "참고 릴스의 «대형» — 확대 배율"
    assert ss.get("outline", 9) <= 3, "손글씨는 얇은 테두리"
    assert not ss.get("pop_rotate"), "다색 팝(문장마다)과 상호배타"
    assert ss["font"] == "NanumPenScript-Regular", "화면이 제안할 글씨체 힌트"


def test_two_lines_get_two_alternating_colors():
    """🔴 핵심 — 스샷1의 «윗줄 노랑 / 아랫줄 연두»가 실제 ASS에 나온다."""
    txt = _render("손글씨 팝", "형광 노랑 윗줄이고요 연두색 아랫줄입니다")
    assert "&H4DE9FF&" in txt, "노랑 (FFE94D → BGR)"
    assert "&H68F2B8&" in txt, "연두 (B8F268 → BGR)"
    body = [l for l in txt.splitlines() if l.startswith("Dialogue")][-1]
    assert body.index("4DE9FF") < body.index("68F2B8"), "윗줄이 노랑"


def test_scale_actually_enlarges_the_font():
    big = _render("손글씨 팝", "한 줄")
    base = _render("기본", "한 줄")
    fs = lambda t: int(re.search(r"Style: Default,[^,]+,(\d+)", t).group(1))
    assert abs(fs(big) / fs(base) - aw.SUB_STYLES["손글씨 팝"]["scale"]) < 0.03


def test_highlight_restores_to_that_lines_color():
    """강조 뒤 복원색이 «기본색»이면 아랫줄이 윗줄 색으로 바뀐다 — 그 줄 색으로."""
    txt = _render("손글씨 팝", "형광 노랑 윗줄이고요 연두색 아랫줄입니다", hl="아랫줄")
    body = [l for l in txt.splitlines() if l.startswith("Dialogue")][-1]
    after_hl = body.split("&H0032E1FF&")[-1] if "&H0032E1FF&" in body else body
    # 강조(골드) 뒤에 연두 복원이 다시 나온다
    assert body.count("&H68F2B8&") >= 1
    gold = aw._inline_color(Style().highlight_color)
    assert gold in body, "강조색 자체도 살아 있다"
    assert body.rindex("&H68F2B8&") > body.index(gold), "강조 뒤 «그 줄» 색 복원"


def test_word_anim_keeps_working_with_handpop():
    """단어별 등장은 자기 경로로 — 손글씨 팝이어도 죽지 않는다 (색은 등장이 우선)."""
    subs = [Subtitle(text="단어별 등장 확인", start_us=0, end_us=10**6)]
    spec = TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목", subtitles=subs,
                        style=Style(sub_style="손글씨 팝", anim="word"),
                        duration_us=10**6)
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(spec, p)
    assert "alpha" in open(p, encoding="utf-8").read(), "단어별 알파 공개가 그대로"


def test_existing_presets_unchanged():
    for st in ("기본", "예능 노랑", "말풍선 띠", "네온", "다색 팝", "블랙 박스"):
        assert "scale" not in aw.SUB_STYLES[st], "확대는 손글씨 팝만"
        _render(st, "회귀 확인 문장")                # 죽지 않고 렌더


def test_ui_offers_handpop_everywhere_subtitles_are_chosen():
    # 편집·AI생성 셀렉트 + 칩, 재렌더(꾸미기만 다시) — 훅 셀렉트에는 없다
    assert HTML.count('<option value="손글씨 팝">') == 3
    assert HTML.count('data-v="손글씨 팝"') == 2, "칩 (편집·AI생성)"
    hook_sel = HTML.split('id="hookStyleSel"')[1].split("</select>")[0]
    assert "손글씨 팝" not in hook_sel, "훅(제목)용 아님"
    # 블로그·긴영상·쇼핑은 편집 셀렉트 복제로 전파된다
    assert "cloneSelect('editSubStyleSel', 'wlSubStyleSel')" in JS
    assert "cloneSelect('editSubStyleSel', 'secSubStyleSel')" in JS
    assert "cloneSelect('editSubStyleSel', 'shopSubStyleSel')" in JS


def test_font_is_suggested_not_forced():
    """🔴 서버가 글씨체를 강제하면 미설치 때 libass가 «조용히» 기본체로 —
    v1.38에서 배운 함정. 화면(JS)이 제안만 하고, 직접 고른 글씨체는 존중."""
    assert "function autoFontForPreset(" in JS
    seg = JS.split("function autoFontForPreset(")[1].split("\nfunction ")[0]
    assert "if(f.value) return;" in seg, "«기본»일 때만 제안"
    assert "opt.disabled" in seg, "미설치면 받기 안내"
    # 렌더 쪽은 font 키를 쓰지 않는다
    aw_src = open(aw.__file__, encoding="utf-8").read()
    assert 'ss.get("font"' not in aw_src


# ── 📺 미리보기 틀 (87) ─────────────────────────────────────────
def test_every_deco_box_gets_a_preview_frame():
    assert "_mountPvFrame(box, key);" in JS, "mountDeco가 5경로 전부에 장착"
    for key in ("gen", "edit", "weblink", "sections", "shop"):
        assert f"{key}:" in JS.split("const PV_IDS = {")[1].split("};")[0]


def test_preview_replays_the_entrance_effect():
    assert "function _pvApplyAnim(" in JS
    seg = JS.split("function _pvApplyAnim(")[1].split("\nfunction ")[0]
    for anim in ("pvPop", "pvType", "pvFadeIn"):
        assert anim in seg
    assert "void el.offsetWidth;" in seg, "리플로 강제 없이는 재생이 안 된다"
    assert "▶ 효과 다시" in JS


def test_preview_updates_on_any_change_in_the_box():
    seg = JS.split("function _mountPvFrame(")[1].split("\nfunction ")[0]
    assert "addEventListener('change'" in seg, "위임 — 상자 안 어떤 조작이든"
    assert "addEventListener('click'" in seg, "칩·톤카드는 change를 안 쏜다"


def test_ass_band_color_converts_to_css():
    """&HAABBGGRR(BGR!) → CSS. 틀리면 띠 색이 화면과 렌더에서 딴판이 된다."""
    seg = JS.split("function assColorToCss(")[1].split("\nfunction ")[0]
    assert "h.slice(4,6)" in seg and "h.slice(0,2)" in seg, "BGR 뒤집기"
    assert "rgba(" in seg, "반투명 알파(&H90…) 지원"


def test_presets_come_from_the_server_not_a_js_copy():
    """색을 JS에 베끼면 언젠가 어긋난다 — ass_writer가 진실의 원천."""
    assert '"/api/deco_presets"' in SRC or "'/api/deco_presets'" in JS
    assert "window._DECO_PRESETS = d" in JS


def test_deco_presets_api_serves_everything(tmp_path):
    import os

    from cutdaejang import config

    iso = tmp_path / "iso"
    iso.mkdir()
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(tmp_path / "wd"), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/deco_presets"
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.loads(r.read())
        assert "손글씨 팝" in d["sub"]
        assert d["sub"].keys() == aw.SUB_STYLES.keys()
        assert d["hook"].keys() == aw.HOOK_STYLES.keys()
        assert d["palette"] == aw.POP_PALETTE
    finally:
        httpd.shutdown()
        config.api_keys_path = orig
        if old is None:
            os.environ.pop("CUTDAEJANG_SETTINGS", None)
        else:
            os.environ["CUTDAEJANG_SETTINGS"] = old


def test_js_font_map_matches_render_name_table():
    """🔴 v1.38 함정의 화면판 — JS 맵이 렌더 이름표(name1)와 다르거나 빠지면
    글씨체 미리보기가 «조용히» 프리텐다드로 나온다. 실제로 4종이 빠져 있었다."""
    m = re.search(r"const FONT_FAMILY_MAP = \{(.*?)\};", JS, re.S)
    pairs = dict(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", m.group(1)))
    for stem, fam in pairs.items():
        assert presets.FONT_FAMILY_ALIASES.get(stem) == fam, stem
    # 글씨체 셀렉트가 권하는 모든 글씨체가 맵에 있어야 한다 (누락 = 조용한 폴백)
    sel = HTML.split('id="editSubFontSel"')[1].split("</select>")[0]
    for stem in re.findall(r'<option value="([^"]+)"', sel):
        assert stem in pairs, f"{stem} — JS 맵 누락"


def test_font_size_setting_feeds_the_preview():
    assert "setFontSize" in JS.split("function renderDecoPreview(")[1].split("\nfunction ")[0]


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label", "span"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
