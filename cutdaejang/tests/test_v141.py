"""v1.41 — 목록 83: 자막 «등장 효과·페이드·배경 띠»가 설정 서랍에만 있던 것.

회원님 41차 (스크린샷 2장 — 꾸미기 상자 / ⚙ 설정 안의 효과들):
> "1번 사진을 봤을 때 꾸미기 쪽에 2번 이(것)들[이] 가야 할 것 같은데"

맞는 말이었다. 이 넷은 «영상마다 바꾸는 겉모습»인데 ⚙ 설정 서랍에만 있어서,
만들다 말고 서랍을 열었다 닫아야 했다. 자막 글씨 크기·배경음악 소리는
이미 꾸미기에서 바꾸고 있으니(v1.35 _decoQuickRow) 결이 같다.

⚠ 여기서 만드는 건 «분신»이다 — 진짜 칸은 설정 서랍에 그대로 둔다.
  만드는 경로가 6개라 원본을 옮길 수 없고(한 곳에만 있을 수 있다),
  id를 복제하면 저장·복원이 통째로 깨진다 (v1.35 목록 64에서 배운 것).
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))
# 효과 줄은 «상수(_DECO_CHK) + 함수» 두 조각이라 둘 다 본다
DECO = (JS.split("const _DECO_CHK = ")[1].split("\nfunction mountDeco(")[0])


def test_version():
    assert __version__ == "1.51.0"


def test_the_four_things_are_in_the_deco_box():
    """🔴 회원님이 가리킨 넷 — 등장 효과·페이드·제목 띠·자막 띠."""
    assert "qd-anim" in DECO, "자막 등장 효과"
    for cls, label in (("qd-fade", "자막 페이드"), ("qd-hookband", "제목 배경 띠"),
                       ("qd-band", "자막 배경 띠")):
        assert cls in DECO, cls
        assert label in DECO, label


def test_it_is_mounted_on_every_making_screen():
    """만드는 경로가 6개다 — 한 곳만 붙이면 나머지는 그대로 서랍을 열어야 한다."""
    body = JS.split("function mountDeco(")[1].split("\nfunction ")[0]
    assert "box.appendChild(_decoEffectRow());" in body
    assert JS.count("_decoEffectRow()") == 2, "정의 1 + 붙이기 1"
    sets = JS.split("const DECO_SETS = ")[1].split("\n}")[0]
    for key in ("gen", "edit", "weblink", "sections", "shop"):
        assert key + ":" in sets, key


def test_the_effect_list_is_copied_not_retyped():
    """따로 적으면 언젠가 어긋난다 — v1.38에서 «단어별»을 더했듯 앞으로도 는다."""
    assert "[...src.options].forEach(o => sel.add(new Option(o.textContent, o.value)))" in DECO
    assert "$('setSubAnim')" in DECO
    assert "<option value=\"word\">" not in DECO, "여기 목록을 다시 적으면 안 된다"


@pytest.mark.parametrize("cls,key", [("qd-anim", "anim"), ("qd-fade", "fade"),
                                     ("qd-hookband", "hook_band"), ("qd-band", "band")])
def test_changing_it_actually_saves(cls, key):
    """바꿨는데 저장이 안 되면 다음 영상에서 되돌아간다."""
    assert "quickSet(" in DECO
    if cls == "qd-anim":
        assert "quickSet({subtitle: {anim: sel.value}})" in DECO
    else:
        assert "_DECO_CHK" in DECO and key in JS.split("const _DECO_CHK = ")[1][:300]


def test_the_real_box_in_the_drawer_stays_in_sync():
    """설정 서랍에서 바꿔도 꾸미기에 보여야 하고, 반대도 마찬가지다."""
    # 분신 → 원본
    assert "if(src) src.value = sel.value;" in DECO
    assert "const orig = $(x[2]); if(orig) orig.checked = cb.checked;" in DECO
    # 원본 → 분신
    mark = JS.split("function markQuickDeco(){")[1].split("\n}")[0]
    assert "document.querySelectorAll('.qd-anim')" in mark
    assert "$('setSubAnim')" in mark
    assert "_DECO_CHK" in mark


def test_the_original_controls_are_untouched():
    """서랍의 진짜 칸을 지우면 저장 코드가 통째로 깨진다 (id로 읽는다)."""
    for eid in ("setSubAnim", "setFade", "setHookBand", "setBand"):
        assert f'id="{eid}"' in HTML, eid
    save = JS.split("async function saveSettings(){")[1].split("\n}")[0]
    for eid in ("setFade", "setHookBand", "setBand", "setSubAnim"):
        assert f"$('{eid}')" in save, eid


def test_no_duplicate_ids_were_created():
    """🔴 v1.35에서 배운 것 — id를 복제하면 저장·복원이 통째로 깨진다."""
    assert 'id="qd-anim"' not in HTML
    assert "class=\"qd-anim\"" in HTML or "'qd-anim'" in JS
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids))


def test_it_says_what_changed():
    """조용히 바뀌면 «바뀐 줄» 모른다."""
    assert "uiBanner('✅ 자막 등장 효과: '" in DECO
    assert "를 켰어요" in DECO and "를 껐어요" in DECO


def test_the_folded_summary_updates_too():
    """접힌 채로도 지금 뭘 골랐는지 보여야 한다 (v1.35에서 세운 규칙)."""
    assert "refreshDecoSummaries();" in DECO


# ══ 화면이 여전히 성한가 ═══════════════════════════════════════
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
