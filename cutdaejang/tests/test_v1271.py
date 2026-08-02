"""v1.28.0 — 목록 50번(되돌아가기·초기화) + 51번(4K가 오래 걸리는 걸 미리 알리기).

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
    assert __version__ == "1.28.0"


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


# ── 🐢 51번: 4K 시간 대가 · 남은 시간 ──────────────────────────
# 회원님 확인: 40분 좀 지나 **완성됐다** → 멈춘 게 아니라 느린 것이었다.
# 실측(개발 서버 4코어, 같은 설정): 표준 0.92배속 / 4K 5.30배속 = 5.7배.
def test_ultra_quality_warns_about_time():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert "ULTRA_WARN" in src
    assert "5배 이상 오래 걸려요" in src
    assert "표준(1080p)" in src               # 대안을 같이 알려준다
    body = src[src.index("function markUltraCost"):src.index("function sweepUltraCost")]
    assert "sel.value !== 'ultra'" in body    # 4K일 때만 뜬다
    assert "w.remove()" in body               # 되돌리면 사라진다
    # 고를 때마다 + 화면이 처음 뜰 때(기억된 값) 둘 다 걸린다
    assert "document.addEventListener('change'" in src
    assert "sweepUltraCost();" in src


def test_ultra_warning_survives_easy_mode():
    """🔰 쉬운 모드에서는 화질 줄이 숨는다 — 4K가 기억돼 있으면 왜 오래 걸리는지
    알 길이 없다. 4K인 동안만 그 줄을 도로 보이게 해 고칠 수 있어야 한다."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src[src.index("function markUltraCost"):src.index("function sweepUltraCost")]
    assert "box.classList.contains('easy-hide')" in body
    assert "box.classList.remove('easy-hide')" in body
    assert "box.classList.add('easy-hide')" in body    # 표준으로 되돌리면 다시 숨김


def test_progress_shows_remaining_time():
    """경과만 보이면 «언제 끝나는지»를 알 수 없어 멈춘 줄 안다 (40분 사례)."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert "남은 시간 약 " in src
    seg = src[src.index("let elaTxt = ''"):src.index("let elaTxt = ''") + 900]
    assert "es * (1 - frac) / frac" in seg      # 지금까지 속도로 남은 시간 어림
    assert "frac > 0.05" in seg                 # 진행률이 너무 낮으면 추정이 엉터리
    assert "es >= 30" in seg                    # 너무 이르면 표시 안 함


def test_fmtdur_reads_naturally():
    """초 → 사람이 읽는 말. 초보자용이라 «3900초» 같은 건 안 된다."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src[src.index("function fmtDur"):src.index("function qualityHint")]
    assert "'초'" in body and "'분'" in body and "시간 " in body
    assert "sec < 60" in body and "m < 60" in body


# ── 화면 무결성 ────────────────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert "(v1.28.0)" in HTML


# ══ 53번: 구글이 모델을 퇴역시켜도 안 멈추게 ═══════════════════════
# 회원님 22차 로그:
#   404 "This model models/gemini-2.5-flash is no longer available to new users."
# 이름이 11곳에 박혀 있어 **새로 키를 발급한 회원 전원**이 대본·업로드 키트·요약·
# 자막 다듬기·음성 인식을 통째로 못 썼다 (크레딧과 무관).
def test_no_hardcoded_text_model_left_in_call_sites():
    """글 모델 호출은 전부 자동 선택 입구를 거쳐야 한다."""
    for name in ("script_generator.py", "stt_engine.py"):
        src = (ROOT / "cutdaejang/core" / name).read_text(encoding="utf-8")
        body = src.split("def _post_ai(")[1].split("\n\n\n")[0]
        assert "gemini_models.post_url" in body, f"{name}가 자동 선택을 안 거침"
        # 직접 POST 하던 경로가 남아 있으면 그 자리만 또 퇴역에 걸린다
        assert "urllib.request.urlopen(req" not in src.split("class OpenAISTT")[0] \
            or name != "stt_engine.py"


def test_model_resolver_prefers_available_and_skips_gone():
    from cutdaejang.core import gemini_models as gm

    gm._avail_cache.clear(); gm._resolved.clear(); gm._gone.clear()
    gm._avail_cache["TESTKEY1"] = ["gemini-2.5-flash", "gemini-flash-latest"]
    # 설정에 적힌 게 실제로 있으면 그대로 쓴다
    assert gm.resolve_text("gemini-2.5-flash", "xxTESTKEY1") == "gemini-2.5-flash"
    # 퇴역 표시가 되면 다른 것으로 넘어간다
    gm.mark_gone("gemini-2.5-flash")
    assert gm.resolve_text("gemini-2.5-flash", "xxTESTKEY1") == "gemini-flash-latest"
    gm._avail_cache.clear(); gm._resolved.clear(); gm._gone.clear()


def test_model_resolver_can_pick_a_model_it_has_never_heard_of():
    """🔑 핵심 — 구글이 «gemini-9-flash» 같은 걸 내놔도 재빌드 없이 굴러가야 한다."""
    from cutdaejang.core import gemini_models as gm

    gm._avail_cache.clear(); gm._resolved.clear(); gm._gone.clear()
    gm._avail_cache["TESTKEY2"] = ["gemini-9-pro", "gemini-9-flash-turbo",
                                   "gemini-2.5-flash-preview-tts", "some-image-model"]
    got = gm.resolve_text("gemini-2.5-flash", "xxTESTKEY2")
    assert got == "gemini-9-flash-turbo", got     # flash 우선 + 최신 버전 우선
    gm._avail_cache.clear(); gm._resolved.clear(); gm._gone.clear()


def test_model_gone_is_not_confused_with_credit_problems():
    """선불 크레딧 소진(429)을 모델 문제로 오인하면 엉뚱한 모델로 헤맨다."""
    from cutdaejang.core import gemini_models as gm

    assert gm.is_model_gone("This model models/gemini-2.5-flash is no longer available")
    assert gm.is_model_gone('"code": 404, "status": "NOT_FOUND"')
    assert not gm.is_model_gone("Your prepayment credits are depleted.")
    assert not gm.is_model_gone("You exceeded your current quota")


def test_edit_log_records_quality_so_slow_jobs_are_explainable():
    """🪵 51번 — 화질을 안 남겨 두어 «왜 40분 걸렸나»를 로그로 못 되짚었다."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert '"편집 시작: %s (화질=%s, 비율=%s' in src


def test_resolver_does_not_probe_when_things_are_working():
    """🔴 내가 한 번 깨뜨린 자리 — 호출마다 모델 목록을 물어보게 만들었더니,
    ①호출마다 왕복이 하나씩 늘고 ②대역(테스트)이 통째로 막혀 15건이 깨졌다.
    잘 되고 있을 때는 목록을 보지 않아야 한다 — 실패했을 때만 딱 한 번."""
    from cutdaejang.core import gemini_models as gm

    gm._avail_cache.clear(); gm._resolved.clear(); gm._gone.clear()
    seen = []

    def fake_post(url, payload, headers, **kw):
        seen.append(url)
        return {"ok": True}

    def boom(*a, **k):
        raise AssertionError("잘 되는데도 모델 목록을 물어봤다")

    orig, gm.list_available = gm.list_available, boom
    try:
        gm.post_generate("gemini-2.5-flash", {}, "k", poster=fake_post)
    finally:
        gm.list_available = orig
    assert len(seen) == 1 and "gemini-2.5-flash" in seen[0]


def test_resolver_keeps_the_callers_stub_seam():
    """호출부가 넘긴 poster를 써야 대역 바꿔치기가 살아 있다 (위 15건이 깨진 이유)."""
    src = (ROOT / "cutdaejang/core/script_generator.py").read_text(encoding="utf-8")
    body = src.split("def _post_ai(")[1].split("\n\n\n")[0]
    assert "poster=_http_post_json" in body


def test_resolver_omits_timeout_when_not_given():
    """timeout을 안 준 호출은 예전처럼 인자 없이 — 대역 함수 시그니처를 안 깬다."""
    from cutdaejang.core import gemini_models as gm

    assert gm._kw(None) == {}
    assert gm._kw(45.0) == {"timeout": 45.0}
