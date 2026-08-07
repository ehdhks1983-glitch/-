"""v1.21 — 🛍 쇼핑 카드 3종 (회원님 리포트 28·29 + 1·2 8차).

> "수집은 잘 됐는데 수집 결과 확인에 **다른 제품 정보**가 들어가 있음 — 지우고
>  다시 하니 제대로 들어감. 성우 목소리 **미리듣기가 없음**, 볼륨 조절도 됐으면.
>  초보자가 쓴다고 생각했을 때 **순서도 잘못된 거** 같지 않아?"

① 잔존 글 사고: 결과 칸에 옛 상품 글(20자↑)이 남아 있으면 링크를 무시하고
   그 글로 대본을 만들었다 → 자동 채움·링크 변경을 기억해 링크 수집 우선,
   직접 붙여넣은 글 + 링크 동시일 때만 한 번 확인.
② 성우 미리듣기: 쇼핑 카드 목소리 옆 [🔊 미리듣기] + 🔉 볼륨 슬라이더(전체
   미리듣기 공용, 저장됨). 영상 속 목소리 크기는 기존대로 자동 정규화.
③ 순서: ① 로그인 창 준비 → ② 상품 링크 → ③ 수집 결과 — 화면 순서가 실제
   해야 하는 순서와 같아졌다 (예전엔 링크가 먼저라 로그인 단계를 건너뛰기 쉬움).
"""

from cutdaejang import __version__
from cutdaejang.gui import webui


def test_version():
    assert __version__ == "1.49.0"


def _html() -> str:
    return webui._apply_links(webui._HTML)


# ── ③ 초보자 순서 — 화면 순서 = 실제 순서 ───────────────────────
def test_shop_card_steps_in_beginner_order():
    html = _html()
    i_login = html.index("로그인 창 준비")
    i_link = html.index('id="shopLinkInput"')
    i_result = html.index("수집 결과 확인")
    assert i_login < i_link < i_result
    assert '<span class="stepnum">1</span>쿠팡·네이버 로그인 창 준비' in html
    assert '<span class="stepnum">2</span>상품 링크 붙여넣기' in html
    assert '<span class="stepnum">3</span>수집 결과 확인' in html
    assert "처음 한 번만" in html                   # 로그인은 매번이 아님을 명시


# ── ① 옛 상품 글 잔존 → 링크 수집 우선 ──────────────────────────
def test_stale_text_is_replaced_by_link_collection():
    html = _html()
    for tok in ("_shopAutoText", "_shopLastLink", "changedLink",
                "링크에서 새로 수집할까요?", "새 상품 정보로 교체"):
        assert tok in html, tok
    # 자동 채움 직후 그 값을 기억해, 다음 수집에서 '내가 쓴 글'과 구분한다
    assert "window._shopAutoText = r.text" in html
    assert "window._shopLastLink = link" in html


# ── ② 성우 미리듣기 + 공용 볼륨 ─────────────────────────────────
def test_shop_voice_preview_and_volume():
    html = _html()
    assert "previewNarrVoice(event,'shopVoiceSel')" in html
    assert 'id="vpVol"' in html and "setPreviewVol" in html
    assert "function _playPreview" in html
    # 모든 목소리 미리듣기가 볼륨 적용 공용 재생을 쓴다 (직접 재생 잔존 금지)
    assert "new Audio(data.url).play()" not in html
    assert html.count("_playPreview(data.url)") >= 5
    # 미리듣기 함수가 선택칸을 골라 받는다 — 쇼핑 카드도 같은 목소리 목록 재사용
    assert "async function previewNarrVoice(ev, selId)" in html
    assert "$(selId || 'narrVoiceSel')" in html
