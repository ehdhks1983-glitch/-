"""v0.96 — 🧩 6개 카드 기본 요소 파리티 (목소리·BGM·훅·꾸미기·화질·비율).

사용자 요청: "카테고리가 6개인데 나레이션·무료음원 같은 기본이 기존 틀과
동일하게 들어가 있는지 체크" — 이 표가 그 답이자 회귀 방지 장치다.
새 카드를 만들면 이 표에 한 줄을 추가할 것.
"""

from cutdaejang.gui import webui

# 카드 → 기본 요소 → 요소 id (편집·사진 카드는 editCard 공유)
PARITY = {
    "gen":  {"목소리": "voiceSel", "BGM": "bgmSel", "훅": "genHook",
             "테마": "genThemeSel", "자막": "genSubStyleSel", "톤": "genToneSel",
             "글씨체": "genSubFontSel", "비율": "genOrient"},
    "edit": {"목소리": "narrVoiceSel", "BGM": "bgmEditSel", "훅": "editHook",
             "테마": "editThemeSel", "자막": "editSubStyleSel", "톤": "editToneSel",
             "글씨체": "editSubFontSel", "화질": "autoQualitySel", "비율": "editLayout"},
    "wl":   {"목소리": "wlVoiceSel", "BGM": "wlBgmSel", "훅": "wlHook",
             "테마": "wlThemeSel", "자막": "wlSubStyleSel", "톤": "wlToneSel",
             "글씨체": "wlSubFontSel", "화질": "wlQualitySel", "비율": "wlOrientSel"},
    "sec":  {"목소리": "secVoiceSel", "BGM": "secBgmSel", "훅": "secHook",
             "테마": "secThemeSel", "자막": "secSubStyleSel", "톤": "secToneSel",
             "글씨체": "secSubFontSel", "화질": "secQualitySel", "비율": "secLayout"},
    "shop": {"목소리": "shopVoiceSel", "BGM": "shopBgmSel", "훅": "shopHook",
             "테마": "shopThemeSel", "자막": "shopSubStyleSel", "톤": "shopToneSel",
             "글씨체": "shopSubFontSel", "화질": "shopQualitySel", "비율": "shopOrientSel"},
}


def test_all_cards_have_basic_elements():
    html = webui._HTML
    missing = []
    for card, feats in PARITY.items():
        for feat, el in feats.items():
            if (f'id="{el}"' not in html and f"name={el}" not in html
                    and f'name="{el}"' not in html):
                missing.append(f"{card}.{feat}({el})")
    assert not missing, missing


def test_payloads_use_card_local_controls():
    """시작 페이로드가 '보이는 그 카드의' 컨트롤 값을 쓴다 (숨은 폼 값 몰래 안 씀)."""
    html = webui._HTML
    # 블로그: BGM을 (숨어 있는) 편집 폼이 아니라 카드 안 셀렉트에서
    assert "($('wlBgmSel')||{}).value" in html
    assert "bgm: ($('bgmEditSel')||{}).value" not in html.split("startWeblink")[1].split("startWeblinkSafe")[0]
    # 블로그·쇼핑: 비율·화질 하드코딩 제거
    assert "($('wlOrientSel')||{}).value" in html and "($('wlQualitySel')||{}).value" in html
    assert "($('shopOrientSel')||{}).value" in html and "($('shopQualitySel')||{}).value" in html
    # 구간: 훅·화질 전달
    assert "($('secHook')||{}).value" in html and "($('secQualitySel')||{}).value" in html


def test_sections_hook_and_fingerprint():
    src = open(webui.__file__, encoding="utf-8").read()
    # 백엔드가 훅을 실제로 렌더에 씀 + 훅이 바뀌면 ♻ 재사용 지문도 달라짐
    assert 'hook=str(params.get("hook") or "")' in src
    assert "params.get('hook') or ''" in src.split("common_fp")[1][:200]


def test_late_list_sync_covers_wl_and_sec():
    """목소리·BGM 목록이 늦게 로드돼도 블로그·구간 카드도 채워진다 (v0.93 확대)."""
    html = webui._HTML
    assert "window._view === 'weblink') initWeblinkCard" in html
    assert "window._view === 'sections') initSectionCard" in html
