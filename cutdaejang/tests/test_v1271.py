"""v1.27.1 — 목록 50번: [처음으로]가 안 보이고 [초기화]가 없다.

회원님 22차(2026-08-02, 블로그 카드 스샷):
> "처음으로 버튼이 너무 눈에 안 들어와 찾기가 힘들어. 초기화 버튼도 안 보이고"

확인된 것 두 가지:
1. `← 처음으로`가 카드 **맨 위 한 곳에만** 있고 `.ghost`(투명 배경 + 어두운 테두리)라
   배경과 거의 구분이 안 됐다. 스크롤을 내리면 아예 화면 밖으로 사라진다.
2. 초기화 버튼이 카드마다 있고 없고가 달랐다 —
   편집·AI생성·쇼핑에는 있고 **블로그·구간에는 아예 없었다**
   (21번 때 쇼핑 카드에만 넣고 이 둘을 빠뜨렸다).
"""

import re
from pathlib import Path

from cutdaejang import __version__
from cutdaejang.gui import webui

ROOT = Path(__file__).resolve().parents[1]
HTML = webui._apply_links(webui._HTML)


def test_version():
    assert __version__ == "1.27.1"


# ── 🏠 따라오는 되돌아가기 바 ──────────────────────────────────
def test_navbar_exists_and_is_sticky():
    assert 'id="navBar"' in HTML
    assert 'id="navTitle"' in HTML
    assert "🏠 처음으로" in HTML
    css = HTML[HTML.index(".navbar {"):HTML.index(".navbar {") + 400]
    assert "position:sticky" in css, "스크롤을 따라오려면 sticky여야 한다"
    assert "top:0" in css


def test_navbar_is_a_direct_child_of_wrap_not_topbar():
    """🔴 실제로 한 번 틀렸던 자리 — sticky는 **부모 상자 안에서만** 붙어 있다.

    처음에 짧은 flex 줄인 `.topbar`(제목 줄) 안에 넣었더니, 70px만 스크롤해도
    바가 화면 밖으로 밀려났다(실측 top=-149px). 부모가 짧으면 sticky가
    그 상자를 벗어나지 못하기 때문. `.wrap`의 직계 자식이어야 끝까지 따라온다.
    """
    start = HTML.index('<div class="topbar">')
    depth, i = 0, start
    # topbar가 닫히는 지점 찾기 (div 깊이 세기)
    for m in re.finditer(r"<div\b|</div>", HTML[start:]):
        depth += 1 if m.group(0).startswith("<div") else -1
        if depth == 0:
            i = start + m.end()
            break
    nav = HTML.index('id="navBar"')
    assert nav > i, "navBar가 .topbar 안에 있으면 스크롤 시 화면 밖으로 사라진다"


def test_back_button_stands_out():
    """예전에는 투명 배경 + 어두운 테두리라 배경과 구분이 안 됐다."""
    css = HTML[HTML.index("button.ghost.back"):HTML.index("button.ghost.back") + 200]
    assert "#4266d5" in css                       # 파란 테두리
    assert "background:#243052" in css            # 배경도 넣어 눈에 띄게
    assert 'class="ghost back"' in HTML


def test_nav_shows_every_card_and_hides_on_home():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    info = src[src.index("const NAV_INFO"):src.index("function updateNav")]
    for key in ("gen", "edit", "photo", "weblink", "sections", "shop"):
        assert f"{key}:" in info, f"{key} 카드가 바 목록에 없음"
    # 첫 화면(home)은 목록에 없어야 바가 숨는다
    assert "home:" not in info
    assert "bar.classList.toggle('hidden', !info)" in src
    # 카드를 열고 닫을 때마다 갱신
    for caller in ("function openMode", "function showHome", "function openVoice"):
        seg = src[src.index(caller):src.index(caller) + 1400]
        assert "updateNav(" in seg, f"{caller}에서 바를 갱신하지 않음"


# ── 🧹 블로그·구간 카드 초기화 (빠져 있던 것) ────────────────────
def _card_segment(card_id: str) -> str:
    ids = ["editCard", "formCard", "weblinkCard", "sectionCard", "shopCard"]
    pos = sorted(HTML.index(f'id="{i}"') for i in ids)
    p = HTML.index(f'id="{card_id}"')
    nxt = next((x for x in pos if x > p), len(HTML))
    return HTML[p:nxt]


def test_every_card_now_has_a_reset_button():
    """수정 전에는 블로그·구간에만 없었다 — 이제 다섯 카드 전부 있다."""
    want = {
        "editCard": "resetEditForm",
        "formCard": "resetGenForm",
        "weblinkCard": "resetWeblinkCard",
        "sectionCard": "resetSectionCard",
        "shopCard": "resetShopCard",
    }
    for card, fn in want.items():
        seg = _card_segment(card)
        assert f"{fn}(" in seg, f"{card}에 초기화 버튼이 없음"


def test_reset_functions_clear_the_right_fields():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    wl = src[src.index("function resetWeblinkCard"):src.index("function resetSectionCard")]
    for field in ("weblinkUrl", "wlScript", "wlHook", "wlPasteText"):
        assert field in wl, f"블로그 초기화가 {field}를 안 비움"
    assert "window._weblink = null" in wl          # 가져온 글·사진도 버린다
    assert "_wlLocalPhotos" in wl
    assert "confirm(" in wl                        # 실수로 지우지 않게 확인 먼저

    sec = src[src.index("function resetSectionCard"):]
    sec = sec[:sec.index("\nfunction ")]
    assert "fillSectionsForm({})" in sec           # 구간 행을 비우고 빈 줄 1개
    assert "secScriptText" in sec
    assert "confirm(" in sec


def test_nav_reset_dispatches_to_the_current_card():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src[src.index("function resetCurrentCard"):src.index("function openMode")]
    assert "NAV_INFO[window._view]" in body
    assert "typeof window[fn] === 'function'" in body   # 없는 함수면 조용히 넘어감


# ── 화면 무결성 ────────────────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert "(v1.27.1)" in HTML
