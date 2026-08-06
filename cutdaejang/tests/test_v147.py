"""v1.47 — 목록 94: 💓 자막 «계속» 움직임 (두근·갸웃).

회원님 46차:
> "자막 스타일·자막 등장 효과 그리고 아까 보여준 스샷은 글씨가 30초라고
>  했을 때 30초가 동일한 게 아니고 글씨가 커졌다가 작아졌다가 뭐 이런
>  기능들도 있거든"

등장 효과는 «나타날 때 한 번»이고, 이건 «떠 있는 내내» — 서로 다른 축이라
따로 만들었고 같이 쓸 수 있다. ASS에는 반복 애니메이션이 없어 \\t 구간을
사슬로 잇는다 (30초 두근 ≈ \\t 54개 — libass에 부담 없음).
"""

import re
import tempfile

from cutdaejang import __version__
from cutdaejang.core.orchestrator import build_style
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.gui import webui
from cutdaejang.spec import Canvas, Style, Subtitle, TimelineSpec

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))


def _render(motion, dur_s=6, band=False, anim="none"):
    subs = [Subtitle(text="계속 움직이는 자막 확인", start_us=0, end_us=dur_s * 10**6)]
    spec = TimelineSpec(canvas=Canvas(1080, 1920, 30), hook="제목", subtitles=subs,
                        style=Style(motion=motion, band=band, anim=anim),
                        duration_us=dur_s * 10**6)
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(spec, p)
    return open(p, encoding="utf-8").read()


def _default_events(txt):
    return [l for l in txt.splitlines() if l.startswith("Dialogue") and ",Default," in l]


def test_version():
    assert __version__ == "1.47.0"


# ── 렌더 — \t 사슬 ──────────────────────────────────────────────
def test_pulse_repeats_for_the_whole_duration():
    """🔴 핵심 — «30초가 동일»하지 않게: 커졌다(106) 작아졌다(100)가 끝까지."""
    d = _default_events(_render("pulse", dur_s=6))[0]
    assert d.count("\\t(") >= 8, "6초면 550ms 반박자 사슬이 여덟 개는 넘는다"
    assert "\\fscx106\\fscy106" in d and "\\fscx100\\fscy100" in d
    # 사슬이 자막 끝 근처까지 이어진다 (등장 직후 한 번이 아니라)
    last_start = max(int(m.group(1)) for m in re.finditer(r"\\t\((\d+),", d))
    assert last_start > 4000, f"마지막 사슬 시작 {last_start}ms — 끝까지 이어져야"


def test_pulse_ends_at_neutral():
    """끝 프레임이 106%로 굳으면 다음 자막과 크기가 튄다 — 원위치로 마감."""
    d = _default_events(_render("pulse"))[0]
    last = d.rstrip().split("\\t(")[-1]
    assert "\\fscx100\\fscy100" in last


def test_wiggle_tilts_both_ways_and_returns():
    d = _default_events(_render("wiggle"))[0]
    assert "\\frz1.6" in d and "\\frz-1.6" in d
    assert "\\frz0" in d.rstrip().split("\\t(")[-1], "마지막은 똑바로"


def test_none_adds_nothing():
    d = _default_events(_render("none"))[0]
    assert "\\fscx106" not in d and "\\frz1.6" not in d


def test_band_box_stays_still_while_glyphs_move():
    """띠를 켰을 때 박스까지 두근거리면 흉하다 — 유령 레이어는 태그가 없다."""
    evs = _default_events(_render("pulse", band=True))
    assert len(evs) == 2, "띠 = 유령(박스) + 글자 2층"
    assert sum(1 for e in evs if "\\fscx106" not in e) == 1, "박스는 정지"


def test_too_short_subtitle_skips_motion():
    assert aw._motion_tags(1000, "pulse") == "", "1초는 움직일 새가 없다"
    assert aw._motion_tags(0, "pulse") == ""


def test_motion_starts_after_entrance_pop():
    """팝 등장(0~130ms 크기 전환)과 같은 속성이 겹치면 안 된다 — 400ms부터."""
    d = _default_events(_render("pulse", anim="pop"))[0]
    starts = [int(m.group(1)) for m in re.finditer(r"\\t\((\d+),", d)]
    motion_starts = [t for t in starts if t >= 200]      # 팝의 \t(0,130)은 제외
    assert motion_starts and min(motion_starts) >= 400
    assert "\\fscx86" in d, "팝 등장도 그대로 산다"


def test_motion_composes_with_word_anim():
    """단어별 등장(알파 공개)과 속성이 달라 같이 쓸 수 있다 — 죽지 않는지."""
    d = _default_events(_render("pulse", anim="word"))[0]
    assert "alpha" in d and "\\fscx106" in d


# ── 배선 ────────────────────────────────────────────────────────
def test_build_style_carries_motion_for_all_paths():
    st = build_style({"subtitle": {"font_size": 84, "outline": 3,
                                   "motion": "wiggle"}, "bg": {}})
    assert st.motion == "wiggle"
    st2 = build_style({"subtitle": {"font_size": 84, "outline": 3}, "bg": {}})
    assert st2.motion == "none", "기본은 가만히"


def test_settings_ui_and_persistence():
    sel = HTML.split('id="setSubMotion"')[1].split("</select>")[0]
    for v in ('value="none"', 'value="pulse"', 'value="wiggle"'):
        assert v in sel
    assert "$('setSubMotion').value = s.subtitle.motion || 'none';" in JS
    assert "motion: $('setSubMotion').value," in JS
    assert '"motion") in ("none", "pulse", "wiggle")' in SRC.replace("sub.get(", '"')


def test_deco_clone_copies_from_settings_select():
    seg = JS.split("function _decoEffectRow(")[1].split("\nfunction ")[0]
    assert "qd-motion" in seg
    assert "[...msrc.options].forEach" in seg, "따로 적으면 언젠가 어긋난다"
    mark = JS.split("function markQuickDeco(")[1].split("\nfunction ")[0]
    assert ".qd-motion" in mark, "설정에서 바꿔도 분신이 따라온다"


def test_entrance_vs_motion_labels_are_distinct():
    """둘을 구분 못 하면 «있는데 왜 안 움직여»가 된다 — 라벨이 축을 말해준다."""
    assert "떠 있는 내내" in HTML
    assert "나타날 때» 한 번" in HTML.replace("«", "«")


def test_preview_loops_the_motion():
    assert "@keyframes pvPulse" in HTML and "@keyframes pvWiggle" in HTML
    seg = JS.split("function _pvApplyAnim(")[1].split("\nfunction ")[0]
    assert "infinite" in seg, "계속 움직임은 미리보기도 무한 반복"
    assert ".4s infinite" in seg, "실제 렌더와 같은 400ms 지연 규칙"


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label", "span"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
