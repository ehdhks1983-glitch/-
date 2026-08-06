"""v1.35 — 화면 구조 개편 (목록 64·66·67·68·69·70).

회원님 28~30차:
> "설정 부분이랑 일반적으로 영상 만들면서 설정하는 거랑 너무 헷갈리지 않아?
>  자막 같은 것도 영상 만들면서 그때그때 골라야 하는데 설정에 들어가 있고"
> "세부 설정에서 소리 체크하는 거 빼줘"
> "카드 자막 뭐 이런 거 빼니 화면이 위로 올라가지는데 …
>  내가 작업하고 있는 화면에 안내가 떴다 사라지는 게 나을 것 같아"
> "AI 영상 제작을 넣어달라고 했는데 어디 포지션에 도대체 들어가 있는 거야?"
> "그림을 내가 만든 뒤 폴더에서 넣을려고 할 때 폴더를 찾기도 보기도 너무 불편"
> "설정은 누르면 맨 아래에서 설정을 해야 하니 너무 불편해"
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def test_version():
    assert __version__ == "1.47.2"


# ── 66: 「🔊 소리 점검용 목소리(삐-)」 라디오 ──────────────────
def test_the_beep_test_voice_is_gone_from_the_form():
    """개발용 «삐-» 신호음이 성우들과 나란히 있었다 — 고르면 영상이 삐- 소리."""
    assert 'name="prov" value="stub"' not in HTML
    # 왜 뺐는지는 주석으로 남겼으므로, 주석을 지운 «보이는 화면»만 본다
    visible = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
    assert "소리 점검용 목소리" not in visible


def test_something_is_still_checked_when_elevenlabs_key_is_missing():
    """🔴 이 라디오를 되돌릴 자리로 stub을 쓰고 있었다 — 빼면 아무것도 안 켜진다.

    pick('prov')는 `querySelector(':checked').value`라 null이면 그 자리에서 터진다.
    """
    body = JS.split("function checkElevenProv(")[1].split("\nasync function ")[0]
    assert "value='stub'" not in body
    assert "value='gemini'" in body and "value='windows'" in body


# ── 67: 안내가 화면을 맨 위로 끌고 가던 것 ─────────────────────
def test_notices_no_longer_yank_the_page_to_the_top():
    assert "b.scrollIntoView({behavior:'smooth', block:'center'})" not in JS
    assert 'id="toastBox"' in HTML
    assert ".toast {" in HTML and "@keyframes toastOut" in HTML


def test_warnings_still_stay_but_notices_fade():
    """«저장했어요»는 사라져도 되지만 «⚠ 못 찾았어요»는 남아야 한다."""
    body = JS.split("function uiBanner(")[1].split("\nfunction ")[0]
    assert "_WARN_MARKS" in body, "경고와 알림을 가르지 않고 있다"
    assert "toast(s, okMark); return;" in body
    assert "b.classList.remove('hidden')" in body, "경고 띠가 사라지면 안 된다"
    marks = JS.split("const _WARN_MARKS = [")[1].split("]")[0]
    for m in ("⚠", "❌"):
        assert m in marks


def test_the_warning_banner_is_visible_without_scrolling():
    """스크롤을 안 옮기기로 했으니 띠가 화면에 붙어 있어야 읽힌다."""
    assert ".banner { position:sticky" in HTML


# ── 70: 설정이 맨 아래라 끌려 내려가던 것 ──────────────────────
@pytest.mark.parametrize("cid", ["settingsCard", "productCard", "apiCard"])
def test_settings_product_api_are_drawers(cid):
    assert f'<div class="card drawer hidden" id="{cid}">' in HTML
    seg = HTML.split(f'id="{cid}"')[1][:400]
    assert "drawer-head" in seg and "closeDrawer(event)" in seg


def test_opening_a_drawer_never_moves_the_page():
    """🔴 예전 toggleSettings는 페이지 맨 아래로 scrollIntoView 했다 (22번의 덮개)."""
    assert "c.scrollIntoView({behavior:'smooth', block:'start'})" not in JS
    body = JS.split("function openDrawer(")[1].split("\nfunction ")[0]
    assert "c.scrollTop = 0;" in body, "서랍 «안»만 위로 가야 한다"
    assert "scrollIntoView" not in body


def test_the_top_bar_is_pinned_and_carries_the_settings_button():
    """아무리 내려가도 설정을 열 수 있어야 한다 — 예전엔 위로 올라가야 했다."""
    assert ".navbar { position:sticky" in HTML
    assert 'id="navSet"' in HTML and 'onclick="toggleSettings(event)"' in HTML


def test_moving_screens_closes_the_drawer():
    for fn in ("function openMode(kind){", "function showHome(ev){"):
        body = JS.split(fn)[1][:400]
        assert "closeDrawer()" in body, fn


def test_the_drawer_says_which_video_you_are_making():
    body = JS.split("function _drawerNowLine(")[1].split("\nfunction ")[0]
    assert "다음 영상부터 기본값" in body
    # v1.36에서 'aiclip'은 뺐다 (목록 72 — 같은 방으로 가는 두 번째 문이었다)
    for key in ("gen", "edit", "photo", "weblink", "sections", "shop"):
        assert f"{key}:" in body


# ── 64: 흩어져 있던 꾸미기 ────────────────────────────────────
DECO = {
    "gen":      ["genThemeSel", "genSubStyleSel", "genSubFontSel", "genHookStyleSel", "genToneSel"],
    "edit":     ["editThemeSel", "editSubStyleSel", "editSubFontSel", "hookStyleSel", "editToneSel"],
    "weblink":  ["wlThemeSel", "wlSubStyleSel", "wlSubFontSel", "wlHookStyleSel", "wlToneSel"],
    "sections": ["secThemeSel", "secSubStyleSel", "secSubFontSel", "secHookStyleSel", "secToneSel"],
    "shop":     ["shopThemeSel", "shopSubStyleSel", "shopSubFontSel", "shopHookStyleSel", "shopToneSel"],
}


@pytest.mark.parametrize("key,ids", DECO.items())
def test_every_making_screen_has_the_same_five_choices(key, ids):
    """경로마다 이름·자리가 다르면 초보자는 못 찾는다 — 다섯을 한 상자로."""
    body = JS.split("const DECO_SETS = {")[1].split("};")[0]
    line = [x for x in body.splitlines() if x.strip().startswith(key + ":")]
    assert line, f"{key} 가 DECO_SETS에 없다"
    for i in ids:
        assert f"'{i}'" in line[0], f"{key} 에 {i} 가 빠졌다"
        assert f'id="{i}"' in HTML, f"{i} 가 화면에 없다"


def test_the_deco_box_is_built_from_the_elements_that_already_exist():
    """id가 바뀌면 저장·복원·페이로드가 전부 깨진다 — «옮기기»여야 한다."""
    body = JS.split("function mountDeco(")[1].split("\nfunction ")[0]
    # v1.39 (목록 79): «옮긴다»는 그대로. 다만 «부모 줄째» 옮기던 것이 상단 제목의
    #   색·크기·글씨체까지 통째로 데려가 버려서, 이제 조작이 하나뿐인 줄만 통째로
    #   옮기고 아니면 «칸과 바로 앞 이름표»만 옮긴다. 어느 쪽이든 새로 만들진 않는다.
    assert "$(id)" in body, "id로 «있던 것»을 찾아야 한다"
    assert "inner.appendChild(p);" in body, "한 줄짜리는 그 줄을 옮긴다"
    assert "wrap.appendChild(el);" in body, "여러 조작 든 줄에서는 칸만 옮긴다"
    assert "createElement('select'" not in body, "새로 만들면 id·값·이벤트가 다 끊긴다"
    assert "_commonDetails(set.ids)" in body, "이미 한 상자면 그걸 재사용해야 한다"


def test_the_two_most_changed_knobs_are_on_the_making_screen():
    """회원님이 «자주 바꾸는 것»이라 이름 붙인 둘 — 자막 크기와 배경음악 소리."""
    body = JS.split("function _decoQuickRow(")[1].split("\nfunction ")[0]
    assert "qd-size" in body and "qd-bgm" in body
    assert "subtitle: {font_size:" in body
    assert "audio: {bgm_db:" in body, "배경음악 소리는 설정에만 있었다"


def test_the_folded_title_shows_what_is_chosen_now():
    """펼치지 않아도 알 수 있어야 초보자가 안 헤맨다."""
    body = JS.split("function decoSummary(")[1].split("\nfunction ")[0]
    assert "'글씨 ' + (size <= 70" in body
    assert "function refreshDecoSummaries()" in JS


def test_the_old_chip_only_injector_is_gone():
    assert "function injectQuickDeco(" not in JS
    assert "mountAllDeco();" in JS


# ── 64 ②: 사진 모드가 화면 비율을 못 고르던 것 ────────────────
def test_the_shape_picker_left_the_hidden_drawer():
    """🔴 editLayout 라디오가 optAdv 안에 있었고, 사진 모드는 그걸 통째로 숨긴다.

    그래서 사진 영상의 비율은 «직전 편집에서 고른 값»이 조용히 되살아나 정해졌다.
    """
    assert 'id="editShapeTop"' in HTML and 'id="editShapeRow"' in HTML
    opt = HTML.split('id="optAdv"')[1].split("</details>")[0]
    assert 'name="editLayout"' not in opt, "아직 숨겨지는 서랍 안에 있다"
    body = JS.split("function mountShapeTop(")[1].split("\nfunction ")[0]
    assert "top.appendChild(row)" in body


def test_photo_mode_still_hides_the_things_it_should():
    """비율은 꺼냈지만 음성 인식·무음 컷은 사진에 없는 게 맞다."""
    opt = HTML.split('id="optAdv"')[1].split("</details>")[0]
    for i in ("sttSel", "cutSilenceChk"):
        assert f'id="{i}"' in opt


# ── 68: [✨ AI 클립]을 찾을 수 없던 것 ────────────────────────
# ⚠ v1.36에서 «되돌렸다» (목록 72). v1.35의 답(첫 화면에 바로가기 카드)은
#   같은 방(sectionCard)으로 가는 «두 번째 문»이라 오히려 헷갈렸다 —
#   회원님 지적: "각 템플릿 카테고리에 적용을 시키라고 한 거였지."
#   그래서 문은 없애고, AI 영상을 만들기 경로 «안»에 넣었다.
#   여기 있던 세 시험은 그 반대를 못 박고 있어 tests/test_v136.py로 옮겼다
#   (test_the_duplicate_front_door_is_gone / test_each_scene_can_become_an_ai_video).


def test_the_hints_no_longer_point_at_a_screen_that_does_not_exist():
    """안내는 「🎞 구간 대본 영상」을 가리켰는데 첫 화면에 그 이름이 없었다."""
    assert "[🎞 구간 대본 영상]" not in HTML
    assert "구간 만들기의 [✨ AI 클립]" not in HTML
    # v1.36: 「AI로 영상 만들기」 카드는 뺐다 (목록 72) — 이름 일치 검사만 남긴다
    nav = JS.split("const NAV_INFO = {")[1].split("};")[0]
    assert "🖥 긴 영상 (가로 16:9)" in nav, "첫 화면 카드 이름과 위 바 제목이 달랐다"


# ── 69: 내가 만든 그림 넣기 ──────────────────────────────────
@pytest.mark.parametrize("names,want,why", [
    (["1.png", "2.png", "3.png"], [0, 1, 2], "단순 번호"),
    (["03_s.png", "01_s.png", "02_s.png"], [2, 0, 1], "0채움 + 뒤섞임"),
    (["장면2.png", "장면1.png"], [1, 0], "한글 + 번호"),
    (["scene_1.png", "scene_2.png", "scene_10.png"], [0, 1, 9], "10번 이상"),
    (["ChatGPT Image 2026-08-03 14-22-07.png",
      "ChatGPT Image 2026-08-03 14-25-31.png"], [0, 1], "시각 이름 → 이름순"),
    (["a.png", "b.png"], [0, 1], "숫자 없음 → 이름순"),
    (["5.png", "5b.png"], [0, 1], "번호가 겹침 → 이름순"),
])
def test_scene_order_reads_the_number_in_the_filename(names, want, why):
    """🔴 예전엔 이름순 zip이라 챗지피티가 시각으로 지은 이름과 어긋났다."""
    assert webui._scene_order(names) == want, why


def test_the_picker_remembers_the_last_folder():
    """🔴 시작 폴더를 안 줘서 장면 12개면 그림 폴더를 12번 찾아 들어가야 했다."""
    assert "InitialDirectory" in SRC and "@INITDIR@" in SRC
    assert "initialdir" in SRC, "그 외 OS(tkinter)도 같이"
    body = SRC.split("def pick_path(")[1].split("\ndef ")[0]
    assert "_pick_remember(kind, got)" in body


def test_the_picker_escapes_quotes_in_the_remembered_path():
    """시작 폴더는 작은따옴표로 감싼 PowerShell 문자열에 들어간다."""
    body = SRC.split("def _pick_windows(")[1].split("\ndef ")[0]
    assert 'replace("\'", "\'\'")' in body


def test_image_and_images_share_one_remembered_folder():
    assert webui._PICK_GROUP["images"] == webui._PICK_GROUP["image"]


def test_folder_import_reports_what_it_could_not_do():
    """모자라거나 남는 것을 조용히 넘어가면 «넣은 줄 알고» 그냥 완성한다."""
    api = SRC.split('elif path == "/api/scene_folder":')[1].split("elif path ==")[0]
    for k in ('"by_name"', '"empty"', '"skipped"'):
        assert k in api
    body = JS.split("async function importSceneFolder(")[1].split("\n// 📁")[0]
    assert "data.by_name" in body and "아직 빈 장면" in body


def test_the_scene_grid_leads_with_the_picture():
    """🔴 한 칸에 그림+대사+96px 글상자+버튼을 다 넣어 그림이 작았다."""
    body = JS.split("function renderScenes(")[1].split("\nasync function ")[0]
    assert "aspect-ratio:' + (window._jobOrient === 'wide'" in body, "가로 영상은 가로 칸"
    assert "✍ 그림 묘사 고치기" in body, "프롬프트는 접어 둔다"
    assert "cell.append(cap, lab, row);" in body, "글상자가 칸 밖으로 나와야 한다"
    assert "minmax(300px,1fr)" in HTML


def test_bulk_import_button_is_not_a_faint_ghost_anymore():
    tag = "<button" + HTML.split("<button")[0][:0] + \
        [b for b in HTML.split("<button") if "importSceneFolder(event)" in b[:120]][0]
    assert 'class="ghost"' not in tag[:140], "작은 회색 버튼이라 못 찾으셨다"
    assert "내가 만든 그림 폴더에서" in tag


# ── 화면이 여전히 성한가 ──────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
